import calendar
import csv
import io
import zipfile
from datetime import date, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.models import User
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, FormView, ListView, TemplateView, UpdateView

from .audit import log_audit, log_security_event
from .forms import (
    CommunicationTemplateForm,
    CounsellorAccessRequestForm,
    PreparedReportForm,
    CounsellingSessionForm,
    CommunicationLogForm,
    DocumentRequirementForm,
    FollowUpTaskForm,
    LoginIDAuthenticationForm,
    RequestTaskForm,
    RequiredPasswordChangeForm,
    SecurityPolicyForm,
    SessionChangeRequestForm,
    ParentPortalAccessForm,
    StudentPortalRequestForm,
    StudentRequestPublicForm,
    StudentRequestResponseForm,
    StudentRequestStaffForm,
    StudentFilterForm,
    StudentForm,
    StudentNoteForm,
    StudentPortalAccessForm,
    StudentTermRecordForm,
    TermCourseEnrollmentForm,
    UserSecurityProfileForm,
    UserManagementForm,
)
from .models import (
    AcademicTerm,
    AuditLog,
    CommunicationLog,
    CommunicationTemplate,
    CounsellorAccessRequest,
    CounsellorStudentAccess,
    CounsellingSession,
    DocumentRequirement,
    FollowUpTask,
    ParentPortalAccess,
    PreparedReport,
    SecurityPolicy,
    SessionChangeRequest,
    Student,
    StudentPortalAccess,
    StudentRequest,
    StudentRequestAttachment,
    StudentRequestResponse,
    StudentTermRecord,
    TermCourseEnrollment,
    UserSecurityProfile,
)
from .notifications import (
    send_prepared_report,
    send_request_confirmation,
    send_request_response,
    send_session_change_request_notice,
    send_session_confirmation,
    send_session_reminder,
)
from .permissions import (
    can_edit_student,
    can_view_student,
    counsellor_primary_team,
    get_portal_student,
    get_parent_students,
    has_active_parent_portal,
    has_active_student_portal,
    is_admin,
    is_counsellor,
    is_parent,
    is_student,
    require_admin,
)


def current_student_for_user(user):
    return get_portal_student(user)


def current_parent_students_for_user(user):
    return get_parent_students(user)


def redirect_student_to_portal(request):
    if has_active_student_portal(request.user):
        return redirect("portal_dashboard")
    if is_student(request.user):
        return redirect("portal_unavailable")
    return None


def redirect_parent_to_portal(request):
    if has_active_parent_portal(request.user):
        return redirect("parent_dashboard")
    if is_parent(request.user):
        return redirect("parent_unavailable")
    return None


def redirect_portal_user(request):
    parent_redirect = redirect_parent_to_portal(request)
    if parent_redirect:
        return parent_redirect
    return redirect_student_to_portal(request)


class RoleAwareLoginView(auth_views.LoginView):
    authentication_form = LoginIDAuthenticationForm
    template_name = "registration/login.html"

    def login_identifier(self):
        return (self.request.POST.get("username") or "").strip()

    def lockout_keys(self):
        identifier = self.login_identifier() or "unknown"
        ip_address = client_ip_address(self.request)
        return [
            throttle_cache_key("login-ip", ip_address),
            throttle_cache_key("login-id", identifier),
        ]

    def lockout_active(self):
        for key in self.lockout_keys():
            if (cache.get(key) or 0) >= settings.LOGIN_FAILURE_LIMIT:
                return True
        return False

    def increment_login_failures(self):
        ttl = settings.LOGIN_LOCKOUT_SECONDS
        for key in self.lockout_keys():
            current = cache.get(key) or 0
            cache.set(key, current + 1, ttl)

    def clear_login_failures(self):
        for key in self.lockout_keys():
            cache.delete(key)

    def dispatch(self, request, *args, **kwargs):
        if request.method.lower() == "post" and self.lockout_active():
            log_security_event(
                "login_locked",
                "Blocked login attempt",
                {
                    "section": "login_lockout",
                    "ip_address": client_ip_address(request),
                    "login_identifier": self.login_identifier(),
                },
            )
            messages.error(request, "Too many sign-in attempts were made. Please wait a little and try again.")
            return self.get(request, *args, **kwargs)
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        security_profile = getattr(self.request.user, "security_profile", None)
        if security_profile and security_profile.must_reset_password:
            return reverse("password_change_required")
        student = current_student_for_user(self.request.user)
        if student:
            return reverse("portal_dashboard")
        if has_active_parent_portal(self.request.user):
            return reverse("parent_dashboard")
        if is_parent(self.request.user):
            return reverse("parent_unavailable")
        if is_student(self.request.user):
            return reverse("portal_unavailable")
        return super().get_success_url()

    def form_valid(self, form):
        security_profile = getattr(form.get_user(), "security_profile", None)
        if security_profile and security_profile.manually_locked:
            log_security_event(
                "login_blocked",
                "Blocked login for locked account",
                {
                    "section": "manual_account_lock",
                    "login_identifier": self.login_identifier(),
                    "ip_address": client_ip_address(self.request),
                    "user_id": form.get_user().pk,
                },
                actor=form.get_user(),
            )
            messages.error(self.request, "This account has been locked. Please contact an administrator.")
            return self.get(self.request)
        self.clear_login_failures()
        return super().form_valid(form)

    def form_invalid(self, form):
        self.increment_login_failures()
        log_security_event(
            "login_failed",
            "Failed login attempt",
            {
                "section": "login_failure",
                "ip_address": client_ip_address(self.request),
                "login_identifier": self.login_identifier(),
            },
        )
        return super().form_invalid(form)


def student_queryset_for_user(user):
    qs = Student.objects.select_related("assigned_counsellor")
    student = current_student_for_user(user)
    if student:
        return qs.filter(pk=student.pk)
    parent_students = current_parent_students_for_user(user)
    if parent_students:
        return qs.filter(pk__in=[student.pk for student in parent_students])
    if is_admin(user) or user.is_superuser or user.groups.filter(name="Viewer").exists():
        return qs
    if is_counsellor(user):
        team_name = (counsellor_primary_team(user) or "").strip()
        counsellor_filters = Q(assigned_counsellor=user) | Q(extra_counsellor_access__counsellor=user, extra_counsellor_access__is_active=True)
        if team_name:
            counsellor_filters |= Q(support_team__iexact=team_name)
        return qs.filter(counsellor_filters).distinct()
    return qs.none()


def assign_request_owner(request_item):
    """Route requests toward the student's counsellor when possible."""

    if request_item.assigned_to or not request_item.student or not request_item.student.assigned_counsellor:
        return
    request_item.assigned_to = request_item.student.assigned_counsellor


def save_request_attachments(request_item, uploaded_files, uploaded_by=None):
    for uploaded_file in uploaded_files:
        if not uploaded_file:
            continue
        StudentRequestAttachment.objects.create(
            request=request_item,
            uploaded_by=uploaded_by,
            original_name=uploaded_file.name,
            file=uploaded_file,
        )


def log_queued_request_response(response_item, user, template=None):
    request_item = response_item.request
    CommunicationLog.objects.create(
        student=request_item.student,
        created_by=user,
        direction="outbound",
        method="email",
        category=CommunicationLog.CATEGORY_REQUEST,
        audience=CommunicationLog.AUDIENCE_STUDENT,
        contact_person=request_item.submitted_by_name,
        recipient_email=response_item.recipient_email,
        subject=response_item.subject,
        communicated_at=response_item.send_requested_at or timezone.now(),
        summary=response_item.message,
        status=CommunicationLog.STATUS_QUEUED,
        related_request_response=response_item,
        template=template,
    )


def log_queued_prepared_report(report, user):
    CommunicationLog.objects.create(
        student=report.student,
        created_by=user,
        direction="outbound",
        method="email",
        category=CommunicationLog.CATEGORY_REPORT,
        audience=CommunicationLog.AUDIENCE_PARENT if report.audience == PreparedReport.AUDIENCE_PARENT else CommunicationLog.AUDIENCE_AGENT,
        contact_person=report.recipient_name or report.student.full_name,
        recipient_email=report.recipient_email,
        subject=report.title,
        communicated_at=report.send_requested_at or timezone.now(),
        summary=report.summary or report.title,
        status=CommunicationLog.STATUS_QUEUED,
        related_report=report,
    )


def request_queryset_for_user(user):
    queryset = StudentRequest.objects.select_related("student", "assigned_to", "closed_by").prefetch_related(
        "attachments", "responses"
    )
    if is_student(user):
        student = current_student_for_user(user)
        queryset = queryset.filter(student=student)
    return queryset


def apply_request_filters(queryset, query_dict):
    if query_dict.get("status"):
        queryset = queryset.filter(status=query_dict["status"])
    if query_dict.get("request_type"):
        queryset = queryset.filter(request_type=query_dict["request_type"])
    return queryset


def close_request_item(request_item, user):
    if request_item.status != StudentRequest.STATUS_CLOSED:
        request_item.status_before_close = request_item.status
    request_item.status = StudentRequest.STATUS_CLOSED
    request_item.closed_by = user
    request_item.closed_at = timezone.now()
    request_item.save(update_fields=["status", "status_before_close", "closed_by", "closed_at", "updated_at"])


def reopen_request_item(request_item):
    request_item.status = request_item.status_before_close or StudentRequest.STATUS_IN_REVIEW
    request_item.status_before_close = ""
    request_item.closed_by = None
    request_item.closed_at = None
    request_item.save(update_fields=["status", "status_before_close", "closed_by", "closed_at", "updated_at"])


def report_queryset_for_user(user):
    students = student_queryset_for_user(user)
    return PreparedReport.objects.select_related("student", "term", "prepared_by", "closed_by").filter(student__in=students)


def close_report_item(report, user):
    report.is_closed = True
    report.closed_by = user
    report.closed_at = timezone.now()
    report.save(update_fields=["is_closed", "closed_by", "closed_at", "updated_at"])


def reopen_report_item(report):
    report.is_closed = False
    report.closed_by = None
    report.closed_at = None
    report.save(update_fields=["is_closed", "closed_by", "closed_at", "updated_at"])


def task_queryset_for_user(user):
    return FollowUpTask.objects.select_related("student", "assigned_to", "created_by", "closed_by").filter(
        student__in=student_queryset_for_user(user)
    )


def close_task_item(task, user):
    task.is_closed = True
    task.closed_by = user
    task.closed_at = timezone.now()
    task.save(update_fields=["is_closed", "closed_by", "closed_at", "updated_at"])


def reopen_task_item(task):
    task.is_closed = False
    task.closed_by = None
    task.closed_at = None
    task.save(update_fields=["is_closed", "closed_by", "closed_at", "updated_at"])


def session_queryset_for_user(user):
    return CounsellingSession.objects.select_related("student", "counsellor", "linked_request", "closed_by").filter(
        student__in=student_queryset_for_user(user)
    )


def close_session_item(session, user):
    session.is_closed = True
    session.closed_by = user
    session.closed_at = timezone.now()
    session.save(update_fields=["is_closed", "closed_by", "closed_at", "updated_at"])


def reopen_session_item(session):
    session.is_closed = False
    session.closed_by = None
    session.closed_at = None
    session.save(update_fields=["is_closed", "closed_by", "closed_at", "updated_at"])


def file_response_for_field(file_field, download_name):
    if not file_field:
        raise Http404("File not found.")
    file_field.open("rb")
    return FileResponse(file_field, as_attachment=False, filename=download_name)


def client_ip_address(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def throttle_cache_key(prefix, identifier):
    return f"security:{prefix}:{identifier.casefold() if isinstance(identifier, str) else identifier}"


def build_academic_progress_rows(students):
    checkpoint_rows = []
    student_watch_rows = []
    team_totals = {}

    for student in students:
        team_name = student.support_team or "No team"
        team_totals.setdefault(
            team_name,
            {
                "team": team_name,
                "students": 0,
                "credits": 0,
                "volunteer": 0,
                "literacy": 0,
                "term_actions": 0,
            },
        )
        team_totals[team_name]["students"] += 1

        watch_issues = []
        if student.credits_remaining > 0:
            watch_issues.append(f"{student.credits_remaining} credit{'s' if student.credits_remaining != 1 else ''} remaining")
            team_totals[team_name]["credits"] += 1
        if student.volunteer_hours_remaining > 0:
            watch_issues.append(
                f"{student.volunteer_hours_remaining} volunteer hour{'s' if student.volunteer_hours_remaining != 1 else ''} left"
            )
            team_totals[team_name]["volunteer"] += 1
        if student.osslt_status == Student.OSSLT_PENDING:
            watch_issues.append("OSSLT still pending")
            team_totals[team_name]["literacy"] += 1
        elif student.osslt_status == Student.OSSLT_OLC4O:
            watch_issues.append("OLC4O still needs completion")
            team_totals[team_name]["literacy"] += 1

        if watch_issues:
            student_watch_rows.append(
                {
                    "student": student,
                    "issues": watch_issues,
                    "counsellor": student.assigned_counsellor.get_full_name() if student.assigned_counsellor else "Unassigned",
                }
            )

        for record in student.term_records.all():
            checkpoint_date, checkpoint_type = record.next_report_checkpoint
            status_label = ""
            priority = 0
            detail = ""

            if record.course_load == 0:
                status_label = "Needs setup"
                priority = 4
                detail = "Choose the number of courses or add the exact classes for this term."
            elif checkpoint_type == "final":
                status_label = "Final grades due"
                priority = 3
                detail = "Enter final grades, confirm earned credits, and prepare the final report."
            elif checkpoint_type == "midterm":
                status_label = "Midterm grades due"
                priority = 2
                detail = "Enter midterm grades and prepare the midterm report update."
            elif record.is_completed and record.earned_credit_count < record.course_load:
                status_label = "Credits still pending"
                priority = 1
                detail = "Some planned courses in this completed term have not turned into earned credits yet."

            if status_label:
                checkpoint_rows.append(
                    {
                        "student": student,
                        "record": record,
                        "status_label": status_label,
                        "detail": detail,
                        "checkpoint_date": checkpoint_date,
                        "checkpoint_type": checkpoint_type,
                        "midterm_recorded": record.midterm_recorded_count,
                        "final_recorded": record.final_recorded_count,
                        "priority": priority,
                    }
                )
                team_totals[team_name]["term_actions"] += 1

    checkpoint_rows.sort(
        key=lambda item: (
            -item["priority"],
            item["checkpoint_date"] or date.max,
            item["student"].full_name,
            item["record"].term.display_order,
        )
    )
    student_watch_rows.sort(
        key=lambda item: (
            -len(item["issues"]),
            item["student"].credits_remaining,
            item["student"].full_name,
        )
    )
    team_rows = sorted(
        team_totals.values(),
        key=lambda item: (-item["term_actions"], -item["credits"], item["team"]),
    )
    return checkpoint_rows, student_watch_rows, team_rows


def month_bounds(year, month):
    if month == 12:
        return date(year, month, 1), date(year + 1, 1, 1)
    return date(year, month, 1), date(year, month + 1, 1)


def build_session_calendar(sessions, pending_requests, year, month):
    cal = calendar.Calendar(firstweekday=6)
    sessions_by_day = {}
    for session in sessions:
        sessions_by_day.setdefault(timezone.localtime(session.start_at).date(), []).append(session)
    requests_by_day = {}
    for request_item in pending_requests:
        if request_item.preferred_date:
            requests_by_day.setdefault(request_item.preferred_date, []).append(request_item)
    weeks = []
    for week in cal.monthdatescalendar(year, month):
        days = []
        for day in week:
            days.append(
                {
                    "date": day,
                    "in_month": day.month == month,
                    "sessions": sessions_by_day.get(day, []),
                    "requests": requests_by_day.get(day, []),
                }
            )
        weeks.append(days)
    return weeks


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "cases/dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        portal_redirect = redirect_portal_user(request)
        if portal_redirect:
            return portal_redirect
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        students = student_queryset_for_user(self.request.user)
        tasks = FollowUpTask.objects.filter(student__in=students, is_closed=False).exclude(status=FollowUpTask.STATUS_DONE)
        documents = DocumentRequirement.objects.filter(student__in=students)
        overdue_reviews = students.filter(next_review_date__lt=today).order_by("next_review_date", "full_name")
        student_list = list(students)

        context["stats"] = {
            "active_students": students.filter(is_active=True).count(),
            "follow_up": tasks.filter(due_date__lte=today + timedelta(days=7)).count(),
            "urgent_risk": students.filter(overall_risk_level="urgent").count(),
            "overdue_tasks": tasks.filter(due_date__lt=today).count(),
            "missing_documents": documents.filter(status="missing").count(),
            "payment_issues": students.filter(payment_status__in=["overdue", "plan_needed"]).count(),
            "homestay_issues": students.filter(homestay_status="issue").count(),
            "open_requests": StudentRequest.objects.filter(
                Q(student__in=students) | Q(student__isnull=True),
                status__in=[StudentRequest.STATUS_NEW, StudentRequest.STATUS_IN_REVIEW],
            ).count(),
            "upcoming_sessions": CounsellingSession.objects.filter(
                student__in=students,
                is_closed=False,
                status=CounsellingSession.STATUS_SCHEDULED,
                start_at__date__gte=today,
            ).count(),
            "reviews_this_week": students.filter(next_review_date__gte=today, next_review_date__lte=today + timedelta(days=7)).count(),
        }
        context["case_stage_summary"] = {
            "new": students.filter(case_stage=Student.STAGE_NEW).count(),
            "active": students.filter(case_stage=Student.STAGE_ACTIVE).count(),
            "waiting": students.filter(case_stage__in=[Student.STAGE_WAITING_STUDENT, Student.STAGE_WAITING_PARENT]).count(),
            "application": students.filter(case_stage=Student.STAGE_APPLICATION).count(),
            "resolved": students.filter(case_stage=Student.STAGE_RESOLVED).count(),
        }
        context["team_summary"] = list(
            students.exclude(support_team="")
            .values("support_team")
            .annotate(
                student_total=Count("id"),
                urgent_total=Count("id", filter=Q(overall_risk_level="urgent")),
                open_requests=Count(
                    "requests",
                    filter=Q(
                        requests__status__in=[
                            StudentRequest.STATUS_NEW,
                            StudentRequest.STATUS_IN_REVIEW,
                            StudentRequest.STATUS_APPROVED,
                            StudentRequest.STATUS_SCHEDULED,
                        ]
                    ),
                    distinct=True,
                ),
            )
            .order_by("support_team")
        )
        context["counsellor_workload"] = (
            User.objects.filter(groups__name="Counsellor")
            .annotate(
                student_total=Count(
                    "assigned_students",
                    filter=Q(assigned_students__in=students),
                    distinct=True,
                ),
                due_reviews=Count(
                    "assigned_students",
                    filter=Q(assigned_students__in=overdue_reviews),
                    distinct=True,
                ),
                open_tasks=Count(
                    "tasks",
                    filter=Q(
                        tasks__student__in=students,
                        tasks__is_closed=False,
                        tasks__status__in=[FollowUpTask.STATUS_OPEN, FollowUpTask.STATUS_IN_PROGRESS],
                    ),
                    distinct=True,
                ),
            )
            .order_by("-student_total", "first_name", "last_name")
        )
        context["overdue_reviews"] = overdue_reviews[:8]
        context["recent_students"] = students.order_by("-updated_at")[:8]
        context["recent_requests"] = StudentRequest.objects.select_related("student").filter(
            Q(student__in=students) | Q(student__isnull=True)
        ).order_by("-created_at")[:6]
        context["recent_communications"] = CommunicationLog.objects.filter(student__in=students).select_related("student")[:6]
        context["recent_audit_logs"] = AuditLog.objects.filter(
            Q(model_name="Student") | Q(model_name="FollowUpTask") | Q(model_name="StudentNote")
        )[:8]
        context["academic_watch_counts"] = {
            "credits": sum(1 for student in student_list if student.credits_remaining > 0),
            "volunteer": sum(1 for student in student_list if student.volunteer_hours_remaining > 0),
            "literacy": sum(
                1
                for student in student_list
                if student.osslt_status in [Student.OSSLT_PENDING, Student.OSSLT_OLC4O]
            ),
        }

        academic_watchlist = []
        for student in student_list:
            issues = []
            score = 0
            if student.credits_remaining > 0:
                issues.append(f"{student.credits_remaining} credit{'s' if student.credits_remaining != 1 else ''} remaining")
                score += student.credits_remaining * 3
            if student.volunteer_hours_remaining > 0:
                issues.append(
                    f"{student.volunteer_hours_remaining} volunteer hour{'s' if student.volunteer_hours_remaining != 1 else ''} left"
                )
                score += student.volunteer_hours_remaining
            if student.osslt_status == Student.OSSLT_PENDING:
                issues.append("OSSLT still pending")
                score += 8
            elif student.osslt_status == Student.OSSLT_OLC4O:
                issues.append("OLC4O still needs completion")
                score += 6
            if issues:
                academic_watchlist.append({"student": student, "issues": issues[:3], "score": score})

        context["academic_watchlist"] = sorted(
            academic_watchlist,
            key=lambda item: (-item["score"], item["student"].full_name),
        )[:6]

        access_request_base = CounsellorAccessRequest.objects.select_related("student", "counsellor", "reviewed_by")
        if is_admin(self.request.user):
            context["access_request_summary"] = {
                "title": "Team access requests waiting for review",
                "empty": "No cross-team access requests are waiting right now.",
            }
            context["access_request_items"] = access_request_base.filter(status=CounsellorAccessRequest.STATUS_PENDING)[:6]
        elif is_counsellor(self.request.user):
            context["access_request_summary"] = {
                "title": "My team access requests",
                "empty": "You do not have any team access requests waiting right now.",
            }
            context["access_request_items"] = access_request_base.filter(
                counsellor=self.request.user,
                status=CounsellorAccessRequest.STATUS_PENDING,
            )[:6]
        else:
            context["access_request_summary"] = None
            context["access_request_items"] = access_request_base.none()
        return context


class PortalDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "cases/portal_dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        if not current_student_for_user(request.user):
            messages.error(request, "Student portal access is not enabled for this account.")
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        student = current_student_for_user(self.request.user)
        log_audit(self.request.user, "viewed", student, {"section": "student_portal"})
        requests = student.requests.prefetch_related("attachments", "responses").order_by("-created_at")
        sessions = student.sessions.order_by("start_at")
        next_session = sessions.filter(start_at__gte=timezone.now()).first()
        open_request = requests.exclude(
            status__in=[StudentRequest.STATUS_COMPLETED, StudentRequest.STATUS_CLOSED, StudentRequest.STATUS_DECLINED]
        ).first()
        missing_documents = student.documents.filter(status="missing")
        context["student"] = student
        context["requests"] = requests
        context["sessions"] = sessions
        context["next_session"] = next_session
        context["open_request"] = open_request
        context["term_records"] = student.term_records.prefetch_related("courses", "term").all()
        context["missing_documents"] = missing_documents
        context["student_next_steps"] = [
            {
                "title": "Submit a request",
                "body": "Use the portal to ask for transcripts, counselling sessions, or document support.",
                "done": requests.exists(),
            },
            {
                "title": "Check missing documents",
                "body": "Review any missing items so the school team can keep your case moving forward.",
                "done": not missing_documents.exists(),
            },
            {
                "title": "Watch for school updates",
                "body": "Your portal and email will show replies once staff review your requests.",
                "done": requests.filter(responses__isnull=False).exists(),
            },
        ]
        return context


class PortalUnavailableView(LoginRequiredMixin, TemplateView):
    template_name = "cases/portal_unavailable.html"

    def dispatch(self, request, *args, **kwargs):
        if has_active_student_portal(request.user):
            return redirect("portal_dashboard")
        if not is_student(request.user):
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)


class ParentDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "cases/parent_dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        if not has_active_parent_portal(request.user):
            messages.error(request, "Parent portal access is not enabled for this account.")
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        students = (
            student_queryset_for_user(self.request.user)
            .prefetch_related("documents", "requests__attachments", "requests__responses", "sessions", "term_records__term", "term_records__courses")
            .order_by("full_name")
        )
        log_security_event(
            "viewed",
            "Parent portal dashboard",
            {
                "section": "parent_portal",
                "student_count": students.count(),
            },
            actor=self.request.user,
        )
        family_records = []
        for student in students:
            requests = student.requests.exclude(status=StudentRequest.STATUS_CLOSED).order_by("-created_at")
            sessions = student.sessions.filter(is_closed=False).order_by("start_at")
            family_records.append(
                {
                    "student": student,
                    "requests": requests[:5],
                    "sessions": sessions[:5],
                    "next_session": sessions.filter(start_at__gte=timezone.now()).first(),
                    "missing_documents": student.documents.filter(status="missing"),
                    "term_records": student.term_records.all()[:3],
                    "reports": student.prepared_reports.filter(is_closed=False).order_by("-created_at")[:3],
                    "portal_links": student.parent_access_links.filter(user=self.request.user, is_active=True),
                }
            )
        context["family_records"] = family_records
        context["family_summary"] = {
            "student_total": students.count(),
            "open_requests": StudentRequest.objects.filter(
                student__in=students,
                status__in=[
                    StudentRequest.STATUS_NEW,
                    StudentRequest.STATUS_IN_REVIEW,
                    StudentRequest.STATUS_APPROVED,
                    StudentRequest.STATUS_SCHEDULED,
                ],
            ).count(),
            "upcoming_sessions": CounsellingSession.objects.filter(
                student__in=students,
                is_closed=False,
                status=CounsellingSession.STATUS_SCHEDULED,
                start_at__gte=timezone.now(),
            ).count(),
            "missing_documents": DocumentRequirement.objects.filter(student__in=students, status="missing").count(),
        }
        return context


class ParentUnavailableView(LoginRequiredMixin, TemplateView):
    template_name = "cases/parent_unavailable.html"

    def dispatch(self, request, *args, **kwargs):
        if has_active_parent_portal(request.user):
            return redirect("parent_dashboard")
        if not is_parent(request.user):
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)


class StudentListView(LoginRequiredMixin, ListView):
    model = Student
    template_name = "cases/student_list.html"
    context_object_name = "students"
    paginate_by = 25

    def dispatch(self, request, *args, **kwargs):
        portal_redirect = redirect_portal_user(request)
        if portal_redirect:
            return portal_redirect
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        queryset = student_queryset_for_user(self.request.user).annotate(
            missing_docs_count=Count("documents", filter=Q(documents__status="missing"), distinct=True)
        )
        self.filter_form = StudentFilterForm(self.request.GET or None)
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data.get("assigned_counsellor"):
                queryset = queryset.filter(assigned_counsellor=data["assigned_counsellor"])
            if data.get("grade"):
                queryset = queryset.filter(grade__icontains=data["grade"])
            if data.get("support_team"):
                queryset = queryset.filter(support_team__icontains=data["support_team"])
            if data.get("case_stage"):
                queryset = queryset.filter(case_stage=data["case_stage"])
            if data.get("risk_level"):
                queryset = queryset.filter(overall_risk_level=data["risk_level"])
            if data.get("payment_status"):
                queryset = queryset.filter(payment_status=data["payment_status"])
            if data.get("homestay_status"):
                queryset = queryset.filter(homestay_status=data["homestay_status"])
            if data.get("university_application_status"):
                queryset = queryset.filter(university_application_status=data["university_application_status"])
            if data.get("missing_documents"):
                queryset = queryset.filter(documents__status="missing").distinct()
        return queryset.order_by("full_name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        return context


class AcademicProgressView(LoginRequiredMixin, TemplateView):
    template_name = "cases/academic_progress.html"

    def dispatch(self, request, *args, **kwargs):
        portal_redirect = redirect_portal_user(request)
        if portal_redirect:
            return portal_redirect
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        students = (
            student_queryset_for_user(self.request.user)
            .select_related("assigned_counsellor")
            .prefetch_related("term_records__term", "term_records__courses")
        )
        selected_team = (self.request.GET.get("team") or "").strip()
        selected_year = (self.request.GET.get("year") or "").strip()

        if selected_team:
            students = students.filter(support_team__iexact=selected_team)
        if selected_year:
            students = students.filter(term_records__term__school_year=selected_year).distinct()

        student_list = list(students)
        checkpoint_rows, watch_rows, team_rows = build_academic_progress_rows(student_list)

        if selected_year:
            checkpoint_rows = [
                item for item in checkpoint_rows if item["record"].term.school_year == selected_year
            ]

        context["selected_team"] = selected_team
        context["selected_year"] = selected_year
        context["team_choices"] = [
            team
            for team in student_queryset_for_user(self.request.user)
            .exclude(support_team="")
            .order_by("support_team")
            .values_list("support_team", flat=True)
            .distinct()
        ]
        context["school_year_choices"] = list(
            AcademicTerm.objects.order_by("school_year")
            .values_list("school_year", flat=True)
            .distinct()
        )
        context["stats"] = {
            "students": len(student_list),
            "setup": sum(1 for item in checkpoint_rows if item["status_label"] == "Needs setup"),
            "midterms": sum(1 for item in checkpoint_rows if item["status_label"] == "Midterm grades due"),
            "finals": sum(1 for item in checkpoint_rows if item["status_label"] == "Final grades due"),
            "credit_gaps": sum(1 for item in checkpoint_rows if item["status_label"] == "Credits still pending"),
            "watchlist": len(watch_rows),
        }
        context["checkpoint_rows"] = checkpoint_rows
        context["watch_rows"] = watch_rows[:12]
        context["team_rows"] = team_rows
        return context


class StudentCreateView(LoginRequiredMixin, CreateView):
    model = Student
    form_class = StudentForm
    template_name = "cases/student_form.html"

    def dispatch(self, request, *args, **kwargs):
        if not (is_admin(request.user) or is_counsellor(request.user)):
            messages.error(request, "You do not have permission to add students.")
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        if is_counsellor(self.request.user) and not form.cleaned_data.get("assigned_counsellor"):
            form.instance.assigned_counsellor = self.request.user
        if is_counsellor(self.request.user) and not form.cleaned_data.get("support_team"):
            form.instance.support_team = counsellor_primary_team(self.request.user)
        response = super().form_valid(form)
        log_audit(self.request.user, "created", self.object, {"section": "student"})
        messages.success(self.request, "Student record created successfully.")
        return response


class StudentUpdateView(LoginRequiredMixin, UpdateView):
    model = Student
    form_class = StudentForm
    template_name = "cases/student_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not can_edit_student(request.user, self.object):
            messages.error(request, "You do not have permission to edit this student.")
            return redirect(self.object.get_absolute_url())
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        log_audit(self.request.user, "updated", self.object, {"section": "student"})
        messages.success(self.request, "Student record updated.")
        return response


class StudentDetailView(LoginRequiredMixin, DetailView):
    model = Student
    template_name = "cases/student_detail.html"
    context_object_name = "student"

    def dispatch(self, request, *args, **kwargs):
        portal_redirect = redirect_portal_user(request)
        if portal_redirect:
            return portal_redirect
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return student_queryset_for_user(self.request.user).prefetch_related(
            "notes",
            "tasks",
            "documents",
            "communications",
            "requests",
            "sessions",
            "term_records__term",
            "term_records__courses",
            "parent_access_links__user",
            "prepared_reports",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        log_audit(self.request.user, "viewed", self.object, {"section": "student_record"})
        active_requests = self.object.requests.exclude(status=StudentRequest.STATUS_CLOSED)
        closed_requests = self.object.requests.filter(status=StudentRequest.STATUS_CLOSED)
        active_tasks = self.object.tasks.filter(is_closed=False)
        closed_tasks = self.object.tasks.filter(is_closed=True)
        active_sessions = self.object.sessions.filter(is_closed=False)
        closed_sessions = self.object.sessions.filter(is_closed=True)
        active_reports = self.object.prepared_reports.filter(is_closed=False)
        closed_reports = self.object.prepared_reports.filter(is_closed=True)
        open_request = active_requests.exclude(
            status__in=[StudentRequest.STATUS_COMPLETED, StudentRequest.STATUS_DECLINED]
        ).first()
        upcoming_session = active_sessions.filter(start_at__gte=timezone.now()).order_by("start_at").first()
        urgent_tasks = active_tasks.filter(status__in=[FollowUpTask.STATUS_OPEN, FollowUpTask.STATUS_IN_PROGRESS]).order_by("due_date")[:3]
        missing_documents = self.object.documents.filter(status="missing")
        term_records = self.object.term_records.select_related("term").prefetch_related("courses").all()
        today = timezone.localdate()
        context["active_tab"] = self.request.GET.get("tab", "overview")
        context["can_manage_student"] = can_edit_student(self.request.user, self.object)
        context["note_form"] = StudentNoteForm()
        context["task_form"] = FollowUpTaskForm()
        context["document_form"] = DocumentRequirementForm()
        context["communication_form"] = CommunicationLogForm(
            initial={"communicated_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M")}
        )
        context["request_form"] = StudentRequestStaffForm(initial={"student": self.object})
        context["session_form"] = CounsellingSessionForm(
            initial={
                "student": self.object,
                "counsellor": self.object.assigned_counsellor,
                "confirmation_email": self.object.parent_guardian_email,
                "start_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
                "end_at": timezone.localtime(timezone.now() + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M"),
            }
        )
        context["term_form"] = StudentTermRecordForm(student=self.object)
        context["course_form"] = TermCourseEnrollmentForm()
        context["report_form"] = PreparedReportForm(
            student=self.object,
            initial={
                "student": self.object,
                "title": f"{self.object.full_name} progress report",
                "recipient_name": self.object.parent_guardian_name or self.object.agency,
                "recipient_email": self.object.parent_guardian_email,
                "summary": self.object.internal_summary,
                "academic_progress": f"Academic status: {self.object.get_academic_status_display()}",
                "attendance_update": self.object.attendance_concerns,
                "counselling_update": f"Counselling status: {self.object.get_counselling_status_display()}",
            },
        )
        context["active_requests"] = active_requests
        context["closed_requests"] = closed_requests
        context["active_tasks"] = active_tasks
        context["closed_tasks"] = closed_tasks
        context["active_sessions"] = active_sessions
        context["closed_sessions"] = closed_sessions
        context["active_reports"] = active_reports
        context["closed_reports"] = closed_reports
        context["open_request"] = open_request
        context["upcoming_session"] = upcoming_session
        context["urgent_tasks"] = urgent_tasks
        context["missing_documents"] = missing_documents
        context["parent_access_links"] = self.object.parent_access_links.select_related("user")
        context["pending_access_requests"] = self.object.access_requests.filter(status=CounsellorAccessRequest.STATUS_PENDING)
        context["term_progress_rows"] = []
        for record in term_records:
            checkpoint_date, checkpoint_type = record.next_report_checkpoint
            status_label = "On track"
            badge_class = "text-bg-success"
            detail = "No immediate academic action is needed for this term."
            if record.course_load == 0:
                status_label = "Needs setup"
                badge_class = "text-bg-warning"
                detail = "Set the number of courses or add the exact classes for this term."
            elif checkpoint_type == "midterm":
                status_label = "Midterm grades due"
                badge_class = "text-bg-warning"
                detail = "Enter midterm grades and prepare the midterm report update."
            elif checkpoint_type == "final":
                status_label = "Final grades due"
                badge_class = "text-bg-danger"
                detail = "Enter final grades, confirm earned credits, and prepare the final report."
            elif record.is_completed and record.earned_credit_count < record.course_load:
                status_label = "Credits still pending"
                badge_class = "text-bg-danger"
                detail = "Some courses in this completed term did not yet earn credit."
            context["term_progress_rows"].append(
                {
                    "record": record,
                    "status_label": status_label,
                    "badge_class": badge_class,
                    "detail": detail,
                    "checkpoint_date": checkpoint_date,
                    "checkpoint_type": checkpoint_type,
                    "midterm_recorded": record.midterm_recorded_count,
                    "final_recorded": record.final_recorded_count,
                }
            )
        context["student_actions"] = [
            {
                "title": "Log a request",
                "body": "Capture a new transcript, counselling, or support request without leaving the student record.",
                "href": "?tab=requests",
                "cta": "Open requests",
            },
            {
                "title": "Book the next session",
                "body": "Move straight into scheduling when a counselling conversation needs a confirmed slot.",
                "href": f"{reverse('session_create')}?student={self.object.pk}",
                "cta": "Book session",
            },
            {
                "title": "Prepare a report",
                "body": "Create a polished parent or agent update using the student information already on file.",
                "href": "?tab=reports",
                "cta": "Open reports",
            },
        ]
        context["student_workflow_flags"] = [
            {
                "label": "Case stage",
                "value": self.object.get_case_stage_display(),
                "detail": f"Next review {self.object.next_review_date:%b %d, %Y}" if self.object.next_review_date else "No review date set yet",
            },
            {
                "label": "Support team",
                "value": self.object.support_team or "Not set",
                "detail": "Used to keep counsellor access focused and manageable.",
            },
            {
                "label": "Open requests",
                "value": active_requests.exclude(status__in=[StudentRequest.STATUS_COMPLETED, StudentRequest.STATUS_DECLINED]).count(),
                "detail": "Still waiting on staff review or follow-up",
            },
            {
                "label": "Missing documents",
                "value": missing_documents.count(),
                "detail": "Items still blocking progress",
            },
            {
                "label": "Credits left",
                "value": self.object.credits_remaining,
                "detail": f"{self.object.earned_credits} completed so far",
            },
        ]
        return context


class AddStudentNoteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        student = get_object_or_404(student_queryset_for_user(request.user), pk=pk)
        if not can_edit_student(request.user, student):
            messages.error(request, "You do not have permission to add notes to this student.")
            return redirect(student.get_absolute_url())
        form = StudentNoteForm(request.POST)
        if form.is_valid():
            note = form.save(commit=False)
            note.student = student
            note.author = request.user
            note.save()
            log_audit(request.user, "created", note, {"section": "note", "student_id": student.pk})
            messages.success(request, "Note added.")
        else:
            messages.error(request, "Please correct the note form and try again.")
        return redirect(f"{student.get_absolute_url()}?tab=notes")


class AddStudentTaskView(LoginRequiredMixin, View):
    def post(self, request, pk):
        student = get_object_or_404(student_queryset_for_user(request.user), pk=pk)
        if not can_edit_student(request.user, student):
            messages.error(request, "You do not have permission to add tasks to this student.")
            return redirect(student.get_absolute_url())
        form = FollowUpTaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.student = student
            task.created_by = request.user
            task.save()
            log_audit(request.user, "created", task, {"section": "task", "student_id": student.pk})
            messages.success(request, "Task created.")
        else:
            messages.error(request, "Please correct the task form and try again.")
        return redirect(f"{student.get_absolute_url()}?tab=tasks")


class AddStudentDocumentView(LoginRequiredMixin, View):
    def post(self, request, pk):
        student = get_object_or_404(student_queryset_for_user(request.user), pk=pk)
        if not can_edit_student(request.user, student):
            messages.error(request, "You do not have permission to update documents for this student.")
            return redirect(student.get_absolute_url())
        form = DocumentRequirementForm(request.POST)
        if form.is_valid():
            document = form.save(commit=False)
            document.student = student
            document.save()
            log_audit(request.user, "created", document, {"section": "document", "student_id": student.pk})
            messages.success(request, "Document requirement saved.")
        else:
            messages.error(request, "Please correct the document form and try again.")
        return redirect(f"{student.get_absolute_url()}?tab=documents")


class AddStudentCommunicationView(LoginRequiredMixin, View):
    def post(self, request, pk):
        student = get_object_or_404(student_queryset_for_user(request.user), pk=pk)
        if not can_edit_student(request.user, student):
            messages.error(request, "You do not have permission to add communication logs for this student.")
            return redirect(student.get_absolute_url())
        form = CommunicationLogForm(request.POST)
        if form.is_valid():
            communication = form.save(commit=False)
            communication.student = student
            communication.created_by = request.user
            communication.save()
            log_audit(
                request.user,
                "created",
                communication,
                {"section": "communication", "student_id": student.pk},
            )
            messages.success(request, "Communication log added.")
        else:
            messages.error(request, "Please correct the communication form and try again.")
        return redirect(f"{student.get_absolute_url()}?tab=communication")


class TaskListView(LoginRequiredMixin, ListView):
    template_name = "cases/task_list.html"
    context_object_name = "tasks"
    paginate_by = 30

    def dispatch(self, request, *args, **kwargs):
        portal_redirect = redirect_portal_user(request)
        if portal_redirect:
            return portal_redirect
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        self.current_scope = self.request.GET.get("scope", "active")
        tasks = task_queryset_for_user(self.request.user)
        if self.request.GET.get("status"):
            tasks = tasks.filter(status=self.request.GET["status"])
        if self.request.GET.get("priority"):
            tasks = tasks.filter(priority=self.request.GET["priority"])
        if self.request.GET.get("assigned_to"):
            tasks = tasks.filter(assigned_to_id=self.request.GET["assigned_to"])
        self.filtered_tasks = tasks
        if self.current_scope == "history":
            return tasks.filter(is_closed=True).order_by("-closed_at", "-updated_at")
        return tasks.filter(is_closed=False).order_by("due_date", "priority")

    def post(self, request, *args, **kwargs):
        task = get_object_or_404(task_queryset_for_user(request.user), pk=request.POST.get("task_id"))
        if not can_edit_student(request.user, task.student):
            messages.error(request, "You do not have permission to update this task.")
            return redirect("task_list")
        action = request.POST.get("action")
        if action == "close":
            close_task_item(task, request.user)
            log_audit(request.user, "updated", task, {"section": "task_closed"})
            messages.success(request, "Task moved to history.")
            return redirect("task_list")
        if action == "reopen":
            reopen_task_item(task)
            log_audit(request.user, "updated", task, {"section": "task_reopened"})
            messages.success(request, "Task returned to the active queue.")
            return redirect("task_list")
        task.status = request.POST.get("status", task.status)
        if task.status == FollowUpTask.STATUS_DONE:
            task.completed_at = timezone.now()
        task.save(update_fields=["status", "completed_at", "updated_at"])
        log_audit(request.user, "updated", task, {"section": "task_status"})
        messages.success(request, "Task status updated.")
        return redirect("task_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filtered_tasks = getattr(self, "filtered_tasks", task_queryset_for_user(self.request.user))
        context["status_choices"] = FollowUpTask.STATUS_CHOICES
        context["priority_choices"] = FollowUpTask.PRIORITY_CHOICES
        context["counsellors"] = User.objects.filter(groups__name="Counsellor")
        context["current_scope"] = getattr(self, "current_scope", "active")
        context["active_task_count"] = filtered_tasks.filter(is_closed=False).count()
        context["closed_task_count"] = filtered_tasks.filter(is_closed=True).count()
        return context


class StudentRequestPublicCreateView(CreateView):
    model = StudentRequest
    form_class = StudentRequestPublicForm
    template_name = "cases/student_request_public.html"
    throttle_limit = 5
    throttle_window_seconds = 900

    def get_initial(self):
        initial = super().get_initial()
        student = current_student_for_user(self.request.user)
        if student:
            initial.update(
                {
                    "submitted_by_name": student.full_name,
                    "submitted_by_email": getattr(student.portal_access.user, "email", "") or student.parent_guardian_email,
                    "student_identifier": student.student_id,
                }
            )
        return initial

    def is_throttled(self, email):
        ip_address = client_ip_address(self.request)
        identifiers = [
            throttle_cache_key("public-request-ip", ip_address),
            throttle_cache_key("public-request-email", email or "unknown"),
        ]
        for key in identifiers:
            if (cache.get(key) or 0) >= self.throttle_limit:
                return True
        return False

    def record_submission(self, email):
        ip_address = client_ip_address(self.request)
        identifiers = [
            throttle_cache_key("public-request-ip", ip_address),
            throttle_cache_key("public-request-email", email or "unknown"),
        ]
        for key in identifiers:
            current = cache.get(key) or 0
            cache.set(key, current + 1, self.throttle_window_seconds)

    def form_valid(self, form):
        submitter_email = form.cleaned_data.get("submitted_by_email", "")
        if self.is_throttled(submitter_email):
            log_security_event(
                "throttled",
                "Public student request form",
                {
                    "section": "public_request_throttle",
                    "ip_address": client_ip_address(self.request),
                    "email": submitter_email,
                },
                actor=self.request.user,
            )
            form.add_error(None, "Too many requests were submitted in a short period. Please wait a little and try again.")
            return self.form_invalid(form)
        matched_student = current_student_for_user(self.request.user)
        student_identifier = form.cleaned_data.get("student_identifier")
        if not matched_student and student_identifier:
            matched_student = Student.objects.filter(student_id__iexact=student_identifier).first()
        form.instance.student = matched_student
        assign_request_owner(form.instance)
        response = super().form_valid(form)
        self.record_submission(submitter_email)
        save_request_attachments(self.object, self.request.FILES.getlist("attachments"), self.request.user if self.request.user.is_authenticated else None)
        send_request_confirmation(self.object)
        log_audit(self.request.user, "created", self.object, {"section": "public_request"})
        return response

    def get_success_url(self):
        return reverse("student_request_success")


class StudentRequestSuccessView(TemplateView):
    template_name = "cases/student_request_success.html"


class StudentRequestListView(LoginRequiredMixin, ListView):
    template_name = "cases/request_list.html"
    context_object_name = "requests"
    paginate_by = 30

    def dispatch(self, request, *args, **kwargs):
        portal_redirect = redirect_portal_user(request)
        if portal_redirect:
            return portal_redirect
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        self.current_scope = self.request.GET.get("scope", "active")
        queryset = apply_request_filters(request_queryset_for_user(self.request.user), self.request.GET)
        self.filtered_queryset = queryset
        if self.current_scope == "history":
            return queryset.filter(status=StudentRequest.STATUS_CLOSED).order_by("-closed_at", "-updated_at")
        return queryset.exclude(status=StudentRequest.STATUS_CLOSED).order_by("status", "-created_at")

    def post(self, request, *args, **kwargs):
        if not (is_admin(request.user) or is_counsellor(request.user)):
            messages.error(request, "You do not have permission to update requests.")
            return redirect("request_list")
        request_item = get_object_or_404(StudentRequest, pk=request.POST.get("request_id"))
        action = request.POST.get("action")
        if action == "approve":
            request_item.status = StudentRequest.STATUS_APPROVED
            request_item.save(update_fields=["status", "updated_at"])
            log_audit(request.user, "updated", request_item, {"section": "request_approved_quick"})
            messages.success(request, "Request approved.")
        elif action == "decline":
            request_item.status = StudentRequest.STATUS_DECLINED
            request_item.save(update_fields=["status", "updated_at"])
            log_audit(request.user, "updated", request_item, {"section": "request_declined_quick"})
            messages.success(request, "Request declined.")
        elif action == "complete":
            request_item.status = StudentRequest.STATUS_COMPLETED
            request_item.save(update_fields=["status", "updated_at"])
            log_audit(request.user, "updated", request_item, {"section": "request_completed_quick"})
            messages.success(request, "Request marked completed.")
        elif action == "close":
            close_request_item(request_item, request.user)
            log_audit(request.user, "updated", request_item, {"section": "request_closed_quick"})
            messages.success(request, "Request moved to history.")
        elif action == "reopen":
            reopen_request_item(request_item)
            log_audit(request.user, "updated", request_item, {"section": "request_reopened_quick"})
            messages.success(request, "Request returned to the active queue.")
        return redirect("request_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filtered_queryset = getattr(self, "filtered_queryset", apply_request_filters(request_queryset_for_user(self.request.user), self.request.GET))
        context["status_choices"] = StudentRequest.STATUS_CHOICES
        context["type_choices"] = StudentRequest.REQUEST_TYPE_CHOICES
        context["current_scope"] = getattr(self, "current_scope", "active")
        context["active_request_count"] = filtered_queryset.exclude(status=StudentRequest.STATUS_CLOSED).count()
        context["closed_request_count"] = filtered_queryset.filter(status=StudentRequest.STATUS_CLOSED).count()
        context["request_status_summary"] = {
            "new": filtered_queryset.filter(status=StudentRequest.STATUS_NEW).count(),
            "in_review": filtered_queryset.filter(status=StudentRequest.STATUS_IN_REVIEW).count(),
            "approved": filtered_queryset.filter(status=StudentRequest.STATUS_APPROVED).count(),
            "completed": filtered_queryset.filter(status=StudentRequest.STATUS_COMPLETED).count(),
            "closed": filtered_queryset.filter(status=StudentRequest.STATUS_CLOSED).count(),
        }
        return context


class StudentRequestUpdateView(LoginRequiredMixin, UpdateView):
    model = StudentRequest
    form_class = StudentRequestStaffForm
    template_name = "cases/request_form.html"
    success_url = reverse_lazy("request_list")

    def dispatch(self, request, *args, **kwargs):
        if not (is_admin(request.user) or is_counsellor(request.user)):
            messages.error(request, "You do not have permission to manage student requests.")
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["response_form"] = kwargs.get("response_form") or StudentRequestResponseForm(request_item=self.object)
        context["task_form"] = kwargs.get("task_form") or RequestTaskForm(
            initial={
                "title": f"Follow up: {self.object.title}",
                "description": self.object.details,
                "assigned_to": self.object.assigned_to or getattr(self.object.student, "assigned_counsellor", None),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if "send_response" in request.POST:
            return self.handle_response(request)
        if "create_task" in request.POST:
            return self.handle_task(request)
        if "approve_request" in request.POST:
            self.object.status = StudentRequest.STATUS_APPROVED
            self.object.save(update_fields=["status", "updated_at"])
            log_audit(request.user, "updated", self.object, {"section": "request_approved"})
            messages.success(request, "Request approved.")
            return redirect("request_update", pk=self.object.pk)
        if "decline_request" in request.POST:
            self.object.status = StudentRequest.STATUS_DECLINED
            self.object.save(update_fields=["status", "updated_at"])
            log_audit(request.user, "updated", self.object, {"section": "request_declined"})
            messages.success(request, "Request declined.")
            return redirect("request_update", pk=self.object.pk)
        if "mark_completed" in request.POST:
            self.object.status = StudentRequest.STATUS_COMPLETED
            self.object.save(update_fields=["status", "updated_at"])
            log_audit(request.user, "updated", self.object, {"section": "request_completed"})
            messages.success(request, "Request marked completed.")
            return redirect("request_update", pk=self.object.pk)
        if "close_request" in request.POST:
            close_request_item(self.object, request.user)
            log_audit(request.user, "updated", self.object, {"section": "request_closed"})
            messages.success(request, "Request moved to history.")
            return redirect("request_update", pk=self.object.pk)
        if "reopen_request" in request.POST:
            reopen_request_item(self.object)
            log_audit(request.user, "updated", self.object, {"section": "request_reopened"})
            messages.success(request, "Request returned to the active queue.")
            return redirect("request_update", pk=self.object.pk)
        return super().post(request, *args, **kwargs)

    def handle_response(self, request):
        form = StudentRequestResponseForm(request.POST, request.FILES, request_item=self.object)
        if form.is_valid():
            selected_template = form.cleaned_data.get("template")
            response_item = form.save(commit=False)
            response_item.request = self.object
            response_item.sent_by = request.user
            response_item.send_requested_at = timezone.now()
            response_item.save()
            log_queued_request_response(response_item, request.user, selected_template)
            if response_item.mark_complete and self.object.status not in [StudentRequest.STATUS_COMPLETED, StudentRequest.STATUS_CLOSED]:
                self.object.status = StudentRequest.STATUS_COMPLETED
                self.object.save(update_fields=["status", "updated_at"])
            log_audit(request.user, "created", response_item, {"section": "request_response"})
            messages.success(request, "Response saved and queued for email delivery.")
            return redirect("request_update", pk=self.object.pk)
        messages.error(request, "Please correct the response form.")
        return self.render_to_response(self.get_context_data(response_form=form))

    def handle_task(self, request):
        form = RequestTaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.student = self.object.student
            task.created_by = request.user
            task.status = FollowUpTask.STATUS_OPEN
            task.save()
            log_audit(request.user, "created", task, {"section": "request_task", "request_id": self.object.pk})
            messages.success(request, "Follow-up task created.")
            return redirect("request_update", pk=self.object.pk)
        messages.error(request, "Please correct the task form.")
        return self.render_to_response(self.get_context_data(task_form=form))

    def form_valid(self, form):
        if form.instance.status == StudentRequest.STATUS_CLOSED:
            if self.object.status != StudentRequest.STATUS_CLOSED:
                form.instance.status_before_close = self.object.status
            form.instance.closed_at = self.object.closed_at or timezone.now()
            form.instance.closed_by = self.object.closed_by or self.request.user
        elif self.object.status == StudentRequest.STATUS_CLOSED:
            form.instance.status_before_close = ""
            form.instance.closed_at = None
            form.instance.closed_by = None
        response = super().form_valid(form)
        log_audit(self.request.user, "updated", self.object, {"section": "request"})
        messages.success(self.request, "Request updated.")
        return response


class PortalRequestCreateView(LoginRequiredMixin, CreateView):
    model = StudentRequest
    form_class = StudentPortalRequestForm
    template_name = "cases/portal_request_form.html"
    success_url = reverse_lazy("portal_dashboard")

    def dispatch(self, request, *args, **kwargs):
        if not current_student_for_user(request.user):
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        student = current_student_for_user(self.request.user)
        form.instance.student = student
        form.instance.submitted_by_name = student.full_name
        form.instance.submitted_by_email = getattr(student.portal_access.user, "email", "") or student.parent_guardian_email
        form.instance.student_identifier = student.student_id
        assign_request_owner(form.instance)
        response = super().form_valid(form)
        save_request_attachments(self.object, self.request.FILES.getlist("attachments"), self.request.user)
        send_request_confirmation(self.object)
        log_audit(self.request.user, "created", self.object, {"section": "portal_request"})
        messages.success(self.request, "Your request has been submitted.")
        return response


class AddStudentRequestView(LoginRequiredMixin, View):
    def post(self, request, pk):
        student = get_object_or_404(student_queryset_for_user(request.user), pk=pk)
        if not can_edit_student(request.user, student):
            messages.error(request, "You do not have permission to log requests for this student.")
            return redirect(student.get_absolute_url())
        form = StudentRequestStaffForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.student = student
            item.submitted_by_name = student.full_name
            item.submitted_by_email = student.parent_guardian_email or request.user.email or settings.DEFAULT_FROM_EMAIL
            item.student_identifier = student.student_id
            assign_request_owner(item)
            item.save()
            log_audit(request.user, "created", item, {"section": "request", "student_id": student.pk})
            messages.success(request, "Student request logged.")
        else:
            messages.error(request, "Please correct the request form and try again.")
        return redirect(f"{student.get_absolute_url()}?tab=requests")


class SessionListView(LoginRequiredMixin, ListView):
    template_name = "cases/session_list.html"
    context_object_name = "sessions"
    paginate_by = 40

    def dispatch(self, request, *args, **kwargs):
        portal_redirect = redirect_portal_user(request)
        if portal_redirect:
            return portal_redirect
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        self.current_scope = self.request.GET.get("scope", "active")
        queryset = session_queryset_for_user(self.request.user)
        if self.request.GET.get("status"):
            queryset = queryset.filter(status=self.request.GET["status"])
        if self.request.GET.get("session_type"):
            queryset = queryset.filter(session_type=self.request.GET["session_type"])
        self.filtered_sessions = queryset
        if self.current_scope == "history":
            return queryset.filter(is_closed=True).order_by("-closed_at", "-start_at")
        return queryset.filter(is_closed=False).order_by("start_at")

    def post(self, request, *args, **kwargs):
        if request.POST.get("request_id"):
            request_item = get_object_or_404(
                StudentRequest.objects.select_related("student"),
                pk=request.POST.get("request_id"),
                request_type=StudentRequest.REQUEST_COUNSELLING,
            )
            if not request_item.student or not can_edit_student(request.user, request_item.student):
                messages.error(request, "You do not have permission to manage this counselling request.")
                return redirect("session_list")
            request_action = request.POST.get("request_action")
            if request_action == "approve":
                request_item.status = StudentRequest.STATUS_APPROVED
                request_item.save(update_fields=["status", "updated_at"])
                log_audit(request.user, "updated", request_item, {"section": "session_request_approved"})
                messages.success(request, "Counselling request approved. You can now book a slot.")
                return redirect("session_list")
            if request_action == "decline":
                request_item.status = StudentRequest.STATUS_DECLINED
                request_item.save(update_fields=["status", "updated_at"])
                log_audit(request.user, "updated", request_item, {"section": "session_request_declined"})
                messages.success(request, "Counselling request declined.")
                return redirect("session_list")
        session = get_object_or_404(session_queryset_for_user(request.user), pk=request.POST.get("session_id"))
        if not can_edit_student(request.user, session.student):
            messages.error(request, "You do not have permission to send reminders for this session.")
            return redirect("session_list")
        action = request.POST.get("action")
        if action == "close":
            close_session_item(session, request.user)
            log_audit(request.user, "updated", session, {"section": "session_closed"})
            messages.success(request, "Session moved to history.")
            return redirect("session_list")
        if action == "reopen":
            reopen_session_item(session)
            log_audit(request.user, "updated", session, {"section": "session_reopened"})
            messages.success(request, "Session returned to the active timetable.")
            return redirect("session_list")
        send_session_reminder(session)
        messages.success(request, "Reminder email sent if a recipient address was available.")
        return redirect("session_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = CounsellingSession.STATUS_CHOICES
        context["type_choices"] = CounsellingSession.SESSION_TYPE_CHOICES
        today = timezone.localdate()
        month = int(self.request.GET.get("month", today.month))
        year = int(self.request.GET.get("year", today.year))
        month_start, month_end = month_bounds(year, month)
        month_sessions = session_queryset_for_user(self.request.user).filter(
            is_closed=False,
            start_at__date__gte=month_start,
            start_at__date__lt=month_end,
        )
        pending_requests = StudentRequest.objects.filter(
            student__in=student_queryset_for_user(self.request.user),
            request_type=StudentRequest.REQUEST_COUNSELLING,
            status__in=[
                StudentRequest.STATUS_NEW,
                StudentRequest.STATUS_IN_REVIEW,
                StudentRequest.STATUS_APPROVED,
            ],
        )
        context["calendar_weeks"] = build_session_calendar(month_sessions, pending_requests, year, month)
        context["calendar_month"] = date(year, month, 1)
        context["prev_month"] = (year - 1, 12) if month == 1 else (year, month - 1)
        context["next_month"] = (year + 1, 1) if month == 12 else (year, month + 1)
        context["pending_counselling_requests"] = pending_requests.order_by("preferred_date", "-created_at")[:12]
        filtered_sessions = getattr(self, "filtered_sessions", session_queryset_for_user(self.request.user))
        context["current_scope"] = getattr(self, "current_scope", "active")
        context["active_session_count"] = filtered_sessions.filter(is_closed=False).count()
        context["closed_session_count"] = filtered_sessions.filter(is_closed=True).count()
        return context


class SessionRescheduleRequestView(CreateView):
    model = SessionChangeRequest
    form_class = SessionChangeRequestForm
    template_name = "cases/session_reschedule_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.session = get_object_or_404(CounsellingSession.objects.select_related("student", "counsellor"), reschedule_token=kwargs["token"])
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        initial.update(
            {
                "requester_name": self.session.student.full_name,
                "requester_email": getattr(getattr(self.session.student, "portal_access", None), "user", None) and self.session.student.portal_access.user.email or self.session.confirmation_email or self.session.student.parent_guardian_email,
                "requested_start": timezone.localtime(self.session.start_at).strftime("%Y-%m-%dT%H:%M"),
                "requested_end": timezone.localtime(self.session.end_at).strftime("%Y-%m-%dT%H:%M"),
            }
        )
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["session"] = self.session
        return context

    def form_valid(self, form):
        form.instance.session = self.session
        response = super().form_valid(form)
        send_session_change_request_notice(self.object)
        log_audit(self.request.user, "created", self.object, {"section": "session_change_request"})
        messages.success(self.request, "Your reschedule request has been sent to the counselling team.")
        return response

    def get_success_url(self):
        return reverse("session_reschedule_success")


class SessionRescheduleSuccessView(TemplateView):
    template_name = "cases/session_reschedule_success.html"


class SessionCreateView(LoginRequiredMixin, CreateView):
    model = CounsellingSession
    form_class = CounsellingSessionForm
    template_name = "cases/session_form.html"
    success_url = reverse_lazy("session_list")

    def dispatch(self, request, *args, **kwargs):
        if not (is_admin(request.user) or is_counsellor(request.user)):
            messages.error(request, "You do not have permission to book sessions.")
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        allowed_students = student_queryset_for_user(self.request.user)
        student_id = self.request.GET.get("student")
        if student_id:
            student = allowed_students.filter(pk=student_id).select_related("assigned_counsellor").first()
            if student:
                initial.update(
                    {
                        "student": student,
                        "counsellor": student.assigned_counsellor,
                        "confirmation_email": student.parent_guardian_email,
                    }
                )
        request_id = self.request.GET.get("request")
        if request_id:
            linked_request = (
                StudentRequest.objects.filter(pk=request_id)
                .select_related("student", "assigned_to", "student__assigned_counsellor")
                .filter(Q(student__in=allowed_students) | Q(student__isnull=True, assigned_to=self.request.user))
                .first()
            )
            if linked_request:
                linked_student = linked_request.student
                initial.update(
                    {
                        "linked_request": linked_request,
                        "student": linked_student,
                        "counsellor": linked_request.assigned_to or getattr(linked_student, "assigned_counsellor", None),
                        "confirmation_email": linked_request.submitted_by_email,
                        "status": CounsellingSession.STATUS_SCHEDULED
                        if linked_request.status == StudentRequest.STATUS_APPROVED
                        else CounsellingSession.STATUS_PENDING_APPROVAL,
                    }
                )
        initial.setdefault("start_at", timezone.localtime().strftime("%Y-%m-%dT%H:%M"))
        initial.setdefault("end_at", timezone.localtime(timezone.now() + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M"))
        return initial

    def form_valid(self, form):
        if not form.cleaned_data.get("confirmation_email"):
            linked_request_email = form.instance.linked_request.submitted_by_email if form.instance.linked_request else ""
            student_email = form.instance.student.parent_guardian_email if form.instance.student else ""
            form.instance.confirmation_email = student_email or linked_request_email
        response = super().form_valid(form)
        if self.object.linked_request:
            self.object.linked_request.status = StudentRequest.STATUS_SCHEDULED
            self.object.linked_request.save(update_fields=["status", "updated_at"])
        send_session_confirmation(self.object)
        log_audit(self.request.user, "created", self.object, {"section": "session"})
        messages.success(self.request, "Session booked and confirmation email sent where possible.")
        return response


class StudentPortalAccessUpdateView(LoginRequiredMixin, View):
    template_name = "cases/portal_access_form.html"

    def get(self, request, pk):
        student = get_object_or_404(Student, pk=pk)
        if not (is_admin(request.user) or is_counsellor(request.user)):
            return redirect(student.get_absolute_url())
        form = StudentPortalAccessForm(student=student)
        return render(request, self.template_name, {"form": form, "student": student})

    def post(self, request, pk):
        student = get_object_or_404(Student, pk=pk)
        if not (is_admin(request.user) or is_counsellor(request.user)):
            return redirect(student.get_absolute_url())
        form = StudentPortalAccessForm(request.POST, student=student)
        if form.is_valid():
            access = form.save()
            log_audit(request.user, "updated", access, {"section": "portal_access", "student_id": student.pk})
            messages.success(request, "Student portal access saved.")
            return redirect(student.get_absolute_url())
        return render(request, self.template_name, {"form": form, "student": student})


class ParentPortalAccessUpdateView(LoginRequiredMixin, View):
    template_name = "cases/parent_access_form.html"

    def get(self, request, pk):
        student = get_object_or_404(student_queryset_for_user(request.user), pk=pk)
        if not can_edit_student(request.user, student):
            messages.error(request, "You do not have permission to manage parent access for this student.")
            return redirect(student.get_absolute_url())
        form = ParentPortalAccessForm(student=student)
        links = student.parent_access_links.select_related("user").order_by("user__username")
        return render(request, self.template_name, {"form": form, "student": student, "links": links})

    def post(self, request, pk):
        student = get_object_or_404(student_queryset_for_user(request.user), pk=pk)
        if not can_edit_student(request.user, student):
            messages.error(request, "You do not have permission to manage parent access for this student.")
            return redirect(student.get_absolute_url())
        form = ParentPortalAccessForm(request.POST, student=student)
        links = student.parent_access_links.select_related("user").order_by("user__username")
        if form.is_valid():
            access = form.save()
            log_audit(request.user, "updated", access, {"section": "parent_portal_access", "student_id": student.pk})
            messages.success(request, "Parent portal access saved.")
            return redirect(student.get_absolute_url())
        return render(request, self.template_name, {"form": form, "student": student, "links": links})


class TeamAccessRequestsView(LoginRequiredMixin, TemplateView):
    template_name = "cases/team_access_requests.html"

    def dispatch(self, request, *args, **kwargs):
        portal_redirect = redirect_portal_user(request)
        if portal_redirect:
            return portal_redirect
        if not (is_admin(request.user) or is_counsellor(request.user)):
            messages.error(request, "You do not have permission to access team requests.")
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if is_admin(request.user) and request.POST.get("access_request_id"):
            access_request = get_object_or_404(CounsellorAccessRequest, pk=request.POST["access_request_id"])
            decision = request.POST.get("decision")
            access_request.reviewed_by = request.user
            access_request.reviewed_at = timezone.now()
            access_request.review_note = request.POST.get("review_note", "")
            if decision == "approve":
                access_request.status = CounsellorAccessRequest.STATUS_APPROVED
                access_request.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])
                CounsellorStudentAccess.objects.update_or_create(
                    counsellor=access_request.counsellor,
                    student=access_request.student,
                    defaults={
                        "granted_by": request.user,
                        "reason": access_request.reason,
                        "is_active": True,
                    },
                )
                log_audit(request.user, "updated", access_request, {"section": "team_access_approved"})
                messages.success(request, "Extra student access approved.")
            elif decision == "decline":
                access_request.status = CounsellorAccessRequest.STATUS_DECLINED
                access_request.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])
                log_audit(request.user, "updated", access_request, {"section": "team_access_declined"})
                messages.success(request, "Access request declined.")
            return redirect("team_access_requests")

        if not is_counsellor(request.user):
            messages.error(request, "Only counsellors can submit access requests.")
            return redirect("team_access_requests")
        form = CounsellorAccessRequestForm(request.POST, counsellor=request.user)
        if form.is_valid():
            access_request = form.save(commit=False)
            access_request.counsellor = request.user
            access_request.save()
            log_audit(request.user, "created", access_request, {"section": "team_access_request"})
            messages.success(request, "Access request sent to admin.")
            return redirect("team_access_requests")
        context = self.get_context_data(form=form)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or CounsellorAccessRequestForm(counsellor=self.request.user)
        if is_admin(self.request.user):
            context["pending_requests"] = CounsellorAccessRequest.objects.select_related("counsellor", "student", "reviewed_by").filter(
                status=CounsellorAccessRequest.STATUS_PENDING
            )
            context["recent_requests"] = CounsellorAccessRequest.objects.select_related("counsellor", "student", "reviewed_by")[:20]
        else:
            context["pending_requests"] = CounsellorAccessRequest.objects.none()
            context["recent_requests"] = CounsellorAccessRequest.objects.select_related("student", "reviewed_by").filter(
                counsellor=self.request.user
            )[:20]
        return context


class ReportsView(LoginRequiredMixin, TemplateView):
    template_name = "cases/reports.html"

    def dispatch(self, request, *args, **kwargs):
        portal_redirect = redirect_portal_user(request)
        if portal_redirect:
            return portal_redirect
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if not (is_admin(request.user) or is_counsellor(request.user)):
            messages.error(request, "You do not have permission to prepare reports.")
            return redirect("reports")
        if request.POST.get("report_action"):
            report = get_object_or_404(report_queryset_for_user(request.user), pk=request.POST.get("report_id"))
            if request.POST["report_action"] == "close":
                close_report_item(report, request.user)
                log_audit(request.user, "updated", report, {"section": "prepared_report_closed"})
                messages.success(request, "Report moved to history.")
            elif request.POST["report_action"] == "reopen":
                reopen_report_item(report)
                log_audit(request.user, "updated", report, {"section": "prepared_report_reopened"})
                messages.success(request, "Report returned to the active workspace.")
            return redirect("reports")
        form = PreparedReportForm(request.POST, request.FILES)
        if form.is_valid():
            report = form.save(commit=False)
            report.prepared_by = request.user
            if "send_report" in request.POST and report.recipient_email:
                report.send_requested_at = timezone.now()
            report.save()
            if "send_report" in request.POST and report.recipient_email:
                log_queued_prepared_report(report, request.user)
            success_url = reverse("prepared_report_update", args=[report.pk])
            if "send_report" in request.POST and report.recipient_email:
                messages.success(request, "Report saved and queued for email delivery.")
            else:
                messages.success(request, "Report saved.")
            log_audit(request.user, "created", report, {"section": "prepared_report"})
            return redirect(success_url)
        context = self.get_context_data(report_form=form)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        week_ago = today - timedelta(days=7)
        students = student_queryset_for_user(self.request.user)
        tasks = FollowUpTask.objects.filter(student__in=students)
        self.current_scope = self.request.GET.get("scope", "active")
        reports_queryset = report_queryset_for_user(self.request.user)

        context["weekly_summary"] = {
            "new_students": students.filter(created_at__date__gte=week_ago).count(),
            "updated_students": students.filter(updated_at__date__gte=week_ago).count(),
            "completed_tasks": tasks.filter(completed_at__date__gte=week_ago).count(),
            "urgent_students": students.filter(overall_risk_level="urgent").count(),
        }
        context["counsellor_activity"] = User.objects.filter(groups__name="Counsellor").annotate(
            student_total=Count("assigned_students", distinct=True),
            open_tasks=Count("tasks", filter=Q(tasks__status__in=["open", "in_progress"]), distinct=True),
        )
        context["student_case_summary"] = students.order_by("-updated_at")[:10]
        context["overdue_tasks"] = tasks.filter(
            due_date__lt=today, status__in=[FollowUpTask.STATUS_OPEN, FollowUpTask.STATUS_IN_PROGRESS]
        ).order_by("due_date")[:20]
        context["report_form"] = kwargs.get("report_form") or PreparedReportForm()
        context["current_scope"] = self.current_scope
        context["active_report_count"] = reports_queryset.filter(is_closed=False).count()
        context["closed_report_count"] = reports_queryset.filter(is_closed=True).count()
        if self.current_scope == "history":
            context["prepared_reports"] = reports_queryset.filter(is_closed=True).order_by("-closed_at", "-updated_at")[:20]
        else:
            context["prepared_reports"] = reports_queryset.filter(is_closed=False).order_by("-created_at")[:20]
        return context


class AddStudentTermRecordView(LoginRequiredMixin, View):
    def post(self, request, pk):
        student = get_object_or_404(student_queryset_for_user(request.user), pk=pk)
        if not can_edit_student(request.user, student):
            messages.error(request, "You do not have permission to manage term history for this student.")
            return redirect(f"{student.get_absolute_url()}?tab=terms")
        form = StudentTermRecordForm(request.POST, student=student)
        if form.is_valid():
            term_record = form.save(commit=False)
            term_record.student = student
            term_record.save()
            log_audit(request.user, "created", term_record, {"section": "term_record", "student_id": student.pk})
            messages.success(request, "Term record added.")
        else:
            messages.error(request, "Please correct the term form and try again.")
        return redirect(f"{student.get_absolute_url()}?tab=terms")


class AddTermCourseView(LoginRequiredMixin, View):
    def post(self, request, pk, term_record_id):
        student = get_object_or_404(student_queryset_for_user(request.user), pk=pk)
        term_record = get_object_or_404(StudentTermRecord, pk=term_record_id, student=student)
        if not can_edit_student(request.user, student):
            messages.error(request, "You do not have permission to add courses for this student.")
            return redirect(f"{student.get_absolute_url()}?tab=terms")
        form = TermCourseEnrollmentForm(request.POST)
        if form.is_valid():
            course = form.save(commit=False)
            course.term_record = term_record
            course.save()
            log_audit(request.user, "created", course, {"section": "term_course", "student_id": student.pk})
            messages.success(request, "Course added to term history.")
        else:
            messages.error(request, "Please correct the course form and try again.")
        return redirect(f"{student.get_absolute_url()}?tab=terms")


class AddPreparedReportView(LoginRequiredMixin, View):
    def post(self, request, pk):
        student = get_object_or_404(student_queryset_for_user(request.user), pk=pk)
        if not can_edit_student(request.user, student):
            messages.error(request, "You do not have permission to prepare reports for this student.")
            return redirect(f"{student.get_absolute_url()}?tab=reports")
        form = PreparedReportForm(request.POST, request.FILES, student=student)
        if form.is_valid():
            report = form.save(commit=False)
            report.student = student
            report.prepared_by = request.user
            if "send_report" in request.POST and report.recipient_email:
                report.send_requested_at = timezone.now()
            report.save()
            if "send_report" in request.POST and report.recipient_email:
                log_queued_prepared_report(report, request.user)
            success_url = reverse("prepared_report_update", args=[report.pk])
            if "send_report" in request.POST and report.recipient_email:
                messages.success(request, "Report saved and queued for email delivery.")
            else:
                messages.success(request, "Report saved.")
            log_audit(request.user, "created", report, {"section": "prepared_report", "student_id": student.pk})
        else:
            messages.error(request, "Please correct the report form and try again.")
            success_url = f"{student.get_absolute_url()}?tab=reports"
        return redirect(success_url)


class PreparedReportUpdateView(LoginRequiredMixin, UpdateView):
    model = PreparedReport
    form_class = PreparedReportForm
    template_name = "cases/prepared_report_form.html"

    def dispatch(self, request, *args, **kwargs):
        portal_redirect = redirect_portal_user(request)
        if portal_redirect:
            return portal_redirect
        self.object = self.get_object()
        if not can_view_student(request.user, self.object.student):
            messages.error(request, "You do not have permission to access this report.")
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["student"] = self.object.student
        return kwargs

    def get_success_url(self):
        return reverse("prepared_report_update", args=[self.object.pk])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["student"] = self.object.student
        log_audit(self.request.user, "viewed", self.object, {"section": "prepared_report"})
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not can_edit_student(request.user, self.object.student):
            messages.error(request, "You do not have permission to update this report.")
            return redirect("prepared_report_update", pk=self.object.pk)
        if "close_report" in request.POST:
            close_report_item(self.object, request.user)
            log_audit(request.user, "updated", self.object, {"section": "prepared_report_closed"})
            messages.success(request, "Report moved to history.")
            return redirect("prepared_report_update", pk=self.object.pk)
        if "reopen_report" in request.POST:
            reopen_report_item(self.object)
            log_audit(request.user, "updated", self.object, {"section": "prepared_report_reopened"})
            messages.success(request, "Report returned to the active workspace.")
            return redirect("prepared_report_update", pk=self.object.pk)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        if "send_report" in self.request.POST and form.cleaned_data.get("recipient_email"):
            form.instance.send_requested_at = timezone.now()
            form.instance.sent_at = None
            form.instance.send_error = ""
        response = super().form_valid(form)
        if "send_report" in self.request.POST and self.object.recipient_email:
            self.object.communication_logs.filter(status=CommunicationLog.STATUS_QUEUED).delete()
            log_queued_prepared_report(self.object, self.request.user)
        log_audit(self.request.user, "updated", self.object, {"section": "prepared_report"})
        if "send_report" in self.request.POST and self.object.recipient_email:
            messages.success(self.request, "Report updated and queued for email delivery.")
        else:
            messages.success(self.request, "Report updated.")
        return response


class RequestAttachmentDownloadView(LoginRequiredMixin, View):
    def get(self, request, pk):
        attachment = get_object_or_404(
            StudentRequestAttachment.objects.select_related("request__student"),
            pk=pk,
        )
        student = attachment.request.student
        if not student or not can_view_student(request.user, student):
            messages.error(request, "You do not have permission to access this file.")
            return redirect("dashboard")
        log_audit(
            request.user,
            "downloaded",
            attachment,
            {"section": "request_attachment", "student_id": student.pk, "request_id": attachment.request_id},
        )
        return file_response_for_field(attachment.file, attachment.original_name or attachment.file.name.rsplit("/", 1)[-1])


class RequestResponseAttachmentDownloadView(LoginRequiredMixin, View):
    def get(self, request, pk):
        response_item = get_object_or_404(
            StudentRequestResponse.objects.select_related("request__student"),
            pk=pk,
        )
        student = response_item.request.student
        if not student or not can_view_student(request.user, student):
            messages.error(request, "You do not have permission to access this file.")
            return redirect("dashboard")
        if not response_item.attachment:
            raise Http404("File not found.")
        log_audit(
            request.user,
            "downloaded",
            response_item,
            {"section": "request_response_attachment", "student_id": student.pk, "request_id": response_item.request_id},
        )
        return file_response_for_field(
            response_item.attachment,
            response_item.attachment.name.rsplit("/", 1)[-1],
        )


class PreparedReportAttachmentDownloadView(LoginRequiredMixin, View):
    def get(self, request, pk):
        report = get_object_or_404(
            PreparedReport.objects.select_related("student"),
            pk=pk,
        )
        if not can_view_student(request.user, report.student):
            messages.error(request, "You do not have permission to access this file.")
            return redirect("dashboard")
        if not report.attachment:
            raise Http404("File not found.")
        log_audit(
            request.user,
            "downloaded",
            report,
            {"section": "prepared_report_attachment", "student_id": report.student_id},
        )
        return file_response_for_field(
            report.attachment,
            report.attachment.name.rsplit("/", 1)[-1],
        )


class CommunicationCenterView(LoginRequiredMixin, TemplateView):
    template_name = "cases/communication_center.html"

    def dispatch(self, request, *args, **kwargs):
        portal_redirect = redirect_portal_user(request)
        if portal_redirect:
            return portal_redirect
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if not (is_admin(request.user) or is_counsellor(request.user)):
            messages.error(request, "You do not have permission to manage communication templates.")
            return redirect("communication_center")
        template_form = CommunicationTemplateForm(request.POST)
        if template_form.is_valid():
            template = template_form.save()
            log_audit(request.user, "created", template, {"section": "communication_template"})
            messages.success(request, "Communication template saved.")
            return redirect("communication_center")
        context = self.get_context_data(template_form=template_form)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        students = student_queryset_for_user(self.request.user)
        communications = CommunicationLog.objects.filter(student__in=students).select_related(
            "student", "created_by", "template"
        )
        current_scope = self.request.GET.get("scope", "recent")
        if current_scope == "queued":
            communications = communications.filter(status=CommunicationLog.STATUS_QUEUED)
        elif current_scope == "sent":
            communications = communications.filter(status=CommunicationLog.STATUS_SENT)
        elif current_scope == "failed":
            communications = communications.filter(status=CommunicationLog.STATUS_FAILED)
        context["current_scope"] = current_scope
        context["communication_stats"] = {
            "queued": CommunicationLog.objects.filter(student__in=students, status=CommunicationLog.STATUS_QUEUED).count(),
            "sent": CommunicationLog.objects.filter(student__in=students, status=CommunicationLog.STATUS_SENT).count(),
            "failed": CommunicationLog.objects.filter(student__in=students, status=CommunicationLog.STATUS_FAILED).count(),
            "templates": CommunicationTemplate.objects.filter(is_active=True).count(),
        }
        context["communications"] = communications.order_by("-communicated_at")[:30]
        context["templates"] = CommunicationTemplate.objects.order_by("template_type", "name")
        context["template_form"] = kwargs.get("template_form") or CommunicationTemplateForm()
        return context


class UserManagementView(LoginRequiredMixin, View):
    template_name = "cases/user_management.html"

    def get(self, request):
        require_admin(request.user)
        form = UserManagementForm()
        users = User.objects.all().order_by("username")
        return render(request, self.template_name, {"form": form, "users": users})

    def post(self, request):
        require_admin(request.user)
        form = UserManagementForm(request.POST)
        users = User.objects.all().order_by("username")
        if form.is_valid():
            user = form.save()
            log_audit(request.user, "created", user, {"section": "user"})
            messages.success(request, "User created successfully.")
            return redirect("user_management")
        return render(request, self.template_name, {"form": form, "users": users})


class UserUpdateView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = UserManagementForm
    template_name = "cases/user_form.html"
    success_url = reverse_lazy("user_management")

    def dispatch(self, request, *args, **kwargs):
        require_admin(request.user)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        log_audit(self.request.user, "updated", self.object, {"section": "user"})
        messages.success(self.request, "User updated successfully.")
        return response


class SecurityCenterView(LoginRequiredMixin, TemplateView):
    template_name = "cases/security_center.html"

    def dispatch(self, request, *args, **kwargs):
        require_admin(request.user)
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        policy = SecurityPolicy.get_solo()
        action = request.POST.get("action")

        if action == "save_policy":
            policy_form = SecurityPolicyForm(request.POST, instance=policy)
            if policy_form.is_valid():
                policy_form.save()
                log_audit(request.user, "updated", policy, {"section": "security_policy"})
                messages.success(request, "Security policy updated.")
                return redirect("security_center")
            return self.render_to_response(self.get_context_data(policy_form=policy_form))

        user = get_object_or_404(User.objects.all(), pk=request.POST.get("user_id"))
        security_profile, _ = UserSecurityProfile.objects.get_or_create(user=user)
        profile_form = UserSecurityProfileForm(request.POST, instance=security_profile)

        if action in {"lock_user", "unlock_user", "force_reset", "clear_reset", "save_note"}:
            if action == "lock_user":
                security_profile.manually_locked = True
                message = "Account locked."
            elif action == "unlock_user":
                security_profile.manually_locked = False
                message = "Account unlocked."
            elif action == "force_reset":
                security_profile.must_reset_password = True
                message = "Password reset required on next sign-in."
            elif action == "clear_reset":
                security_profile.must_reset_password = False
                message = "Forced password reset cleared."
            else:
                if profile_form.is_valid():
                    security_profile.security_note = profile_form.cleaned_data["security_note"]
                    message = "Security note updated."
                else:
                    return self.render_to_response(self.get_context_data(policy_form=SecurityPolicyForm(instance=policy)))
            security_profile.save()
            log_audit(
                request.user,
                "updated",
                user,
                {"section": "security_center", "security_action": action},
            )
            messages.success(request, message)
            return redirect("security_center")

        messages.error(request, "That security action could not be completed.")
        return redirect("security_center")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        policy = SecurityPolicy.get_solo()
        users = list(
            User.objects.select_related("security_profile", "counsellor_profile")
            .prefetch_related("groups")
            .order_by("username")
        )
        for user in users:
            UserSecurityProfile.objects.get_or_create(user=user)
        context["policy_form"] = kwargs.get("policy_form") or SecurityPolicyForm(instance=policy)
        context["security_users"] = users
        context["policy"] = policy
        return context


class RequiredPasswordChangeView(LoginRequiredMixin, FormView):
    template_name = "registration/password_change_required.html"
    form_class = RequiredPasswordChangeForm
    success_url = reverse_lazy("dashboard")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def dispatch(self, request, *args, **kwargs):
        if not getattr(request.user, "is_authenticated", False):
            return redirect(settings.LOGIN_URL)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.save()
        security_profile, _ = UserSecurityProfile.objects.get_or_create(user=self.request.user)
        security_profile.must_reset_password = False
        security_profile.password_changed_at = timezone.now()
        security_profile.save()
        update_session_auth_hash(self.request, self.request.user)
        log_audit(self.request.user, "updated", self.request.user, {"section": "required_password_change"})
        messages.success(self.request, "Password updated successfully.")
        return super().form_valid(form)


class AdminToolsView(LoginRequiredMixin, TemplateView):
    template_name = "cases/admin_tools.html"

    def dispatch(self, request, *args, **kwargs):
        require_admin(request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        security_logs = AuditLog.objects.filter(
            Q(action="downloaded")
            | Q(model_name="SecurityEvent")
            | Q(action="viewed")
        ).select_related("actor")[:20]
        context["security_summary"] = {
            "downloads": AuditLog.objects.filter(action="downloaded").count(),
            "throttled": AuditLog.objects.filter(model_name="SecurityEvent", action="throttled").count(),
            "record_views": AuditLog.objects.filter(action="viewed").count(),
        }
        context["security_logs"] = security_logs
        return context


class DatabaseBackupDownloadView(LoginRequiredMixin, View):
    def get(self, request):
        require_admin(request.user)
        db_path = settings.BASE_DIR / "db.sqlite3"
        if not db_path.exists():
            raise Http404("Database file not found.")
        log_audit(request.user, "downloaded", request.user, {"section": "database_backup"})
        return FileResponse(open(db_path, "rb"), as_attachment=True, filename=f"uis-student-record-system-backup-{timezone.now():%Y%m%d-%H%M}.sqlite3")


class CsvExportDownloadView(LoginRequiredMixin, View):
    def get(self, request):
        require_admin(request.user)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            self._write_students_csv(archive)
            self._write_requests_csv(archive)
            self._write_sessions_csv(archive)
            self._write_tasks_csv(archive)
        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="uis-student-record-system-exports-{timezone.now():%Y%m%d-%H%M}.zip"'
        log_audit(request.user, "downloaded", request.user, {"section": "csv_export"})
        return response

    def _write_students_csv(self, archive):
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(["Student ID", "Full Name", "Grade", "Counsellor", "Risk Level", "Application Status"])
        for student in Student.objects.select_related("assigned_counsellor").order_by("full_name"):
            writer.writerow([
                student.student_id,
                student.full_name,
                student.grade,
                student.assigned_counsellor.get_full_name() if student.assigned_counsellor else "",
                student.get_overall_risk_level_display(),
                student.get_university_application_status_display(),
            ])
        archive.writestr("students.csv", csv_buffer.getvalue())

    def _write_requests_csv(self, archive):
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(["Student", "Submitted By", "Type", "Title", "Status", "Preferred Date"])
        for item in StudentRequest.objects.select_related("student").order_by("-created_at"):
            writer.writerow([
                item.student.full_name if item.student else item.student_identifier,
                item.submitted_by_name,
                item.get_request_type_display(),
                item.title,
                item.get_status_display(),
                item.preferred_date or "",
            ])
        archive.writestr("student_requests.csv", csv_buffer.getvalue())

    def _write_sessions_csv(self, archive):
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(["Student", "Counsellor", "Type", "Start", "End", "Status", "Location"])
        for session in CounsellingSession.objects.select_related("student", "counsellor").order_by("start_at"):
            writer.writerow([
                session.student.full_name,
                session.counsellor.get_full_name() if session.counsellor else "",
                session.get_session_type_display(),
                timezone.localtime(session.start_at).isoformat(),
                timezone.localtime(session.end_at).isoformat(),
                session.get_status_display(),
                session.location,
            ])
        archive.writestr("sessions.csv", csv_buffer.getvalue())

    def _write_tasks_csv(self, archive):
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(["Student", "Task", "Due Date", "Priority", "Status"])
        for task in FollowUpTask.objects.select_related("student").order_by("due_date"):
            writer.writerow([
                task.student.full_name,
                task.title,
                task.due_date.isoformat(),
                task.get_priority_display(),
                task.get_status_display(),
            ])
        archive.writestr("tasks.csv", csv_buffer.getvalue())
