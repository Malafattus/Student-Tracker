import calendar
import csv
import io
import zipfile
from datetime import date, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.models import User
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.base import ContentFile
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from .audit import log_audit
from .forms import (
    PreparedReportForm,
    CounsellingSessionForm,
    CommunicationLogForm,
    DocumentRequirementForm,
    FollowUpTaskForm,
    LoginIDAuthenticationForm,
    RequestTaskForm,
    SessionChangeRequestForm,
    StudentRequestPublicForm,
    StudentRequestResponseForm,
    StudentRequestStaffForm,
    StudentFilterForm,
    StudentForm,
    StudentNoteForm,
    StudentPortalAccessForm,
    StudentTermRecordForm,
    TermCourseEnrollmentForm,
    UserManagementForm,
)
from .models import (
    AcademicTerm,
    AuditLog,
    CommunicationLog,
    CounsellingSession,
    DocumentRequirement,
    FollowUpTask,
    PreparedReport,
    SessionChangeRequest,
    Student,
    StudentPortalAccess,
    StudentRequest,
    StudentRequestAttachment,
    StudentRequestResponse,
    StudentTermRecord,
    TermCourseEnrollment,
)
from .notifications import (
    send_prepared_report,
    send_request_confirmation,
    send_request_response,
    send_session_change_request_notice,
    send_session_confirmation,
    send_session_reminder,
)
from .permissions import can_edit_student, can_view_student, is_admin, is_counsellor, is_student, require_admin


def current_student_for_user(user):
    if not user.is_authenticated or not is_student(user):
        return None
    portal_access = getattr(user, "student_portal", None)
    return portal_access.student if portal_access and portal_access.is_active else None


class RoleAwareLoginView(auth_views.LoginView):
    authentication_form = LoginIDAuthenticationForm
    template_name = "registration/login.html"

    def get_success_url(self):
        student = current_student_for_user(self.request.user)
        if student:
            return reverse("portal_dashboard")
        return super().get_success_url()


def student_queryset_for_user(user):
    qs = Student.objects.select_related("assigned_counsellor")
    student = current_student_for_user(user)
    if student:
        return qs.filter(pk=student.pk)
    if is_admin(user) or user.is_superuser or user.groups.filter(name="Viewer").exists():
        return qs
    if is_counsellor(user):
        # Counsellors can view the wider case list, but editing is still
        # restricted by can_edit_student to records assigned to them.
        return qs
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        students = student_queryset_for_user(self.request.user)
        tasks = FollowUpTask.objects.filter(student__in=students).exclude(status=FollowUpTask.STATUS_DONE)
        documents = DocumentRequirement.objects.filter(student__in=students)

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
                status=CounsellingSession.STATUS_SCHEDULED,
                start_at__date__gte=today,
            ).count(),
        }
        context["recent_students"] = students.order_by("-updated_at")[:8]
        context["recent_requests"] = StudentRequest.objects.select_related("student").order_by("-created_at")[:6]
        context["recent_audit_logs"] = AuditLog.objects.filter(
            Q(model_name="Student") | Q(model_name="FollowUpTask") | Q(model_name="StudentNote")
        )[:8]
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
        context["student"] = student
        context["requests"] = student.requests.order_by("-created_at")
        context["sessions"] = student.sessions.order_by("start_at")
        return context


class StudentListView(LoginRequiredMixin, ListView):
    model = Student
    template_name = "cases/student_list.html"
    context_object_name = "students"
    paginate_by = 25

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

    def get_queryset(self):
        return student_queryset_for_user(self.request.user).prefetch_related(
            "notes", "tasks", "documents", "communications", "requests", "sessions"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["active_tab"] = self.request.GET.get("tab", "overview")
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

    def get_queryset(self):
        tasks = FollowUpTask.objects.select_related("student", "assigned_to", "created_by").filter(
            student__in=student_queryset_for_user(self.request.user)
        )
        if self.request.GET.get("status"):
            tasks = tasks.filter(status=self.request.GET["status"])
        if self.request.GET.get("priority"):
            tasks = tasks.filter(priority=self.request.GET["priority"])
        if self.request.GET.get("assigned_to"):
            tasks = tasks.filter(assigned_to_id=self.request.GET["assigned_to"])
        return tasks.order_by("due_date", "priority")

    def post(self, request, *args, **kwargs):
        task = get_object_or_404(FollowUpTask, pk=request.POST.get("task_id"), student__in=student_queryset_for_user(request.user))
        if not can_edit_student(request.user, task.student):
            messages.error(request, "You do not have permission to update this task.")
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
        context["status_choices"] = FollowUpTask.STATUS_CHOICES
        context["priority_choices"] = FollowUpTask.PRIORITY_CHOICES
        context["counsellors"] = User.objects.filter(groups__name="Counsellor")
        return context


class StudentRequestPublicCreateView(CreateView):
    model = StudentRequest
    form_class = StudentRequestPublicForm
    template_name = "cases/student_request_public.html"

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

    def form_valid(self, form):
        matched_student = current_student_for_user(self.request.user)
        student_identifier = form.cleaned_data.get("student_identifier")
        if not matched_student and student_identifier:
            matched_student = Student.objects.filter(student_id__iexact=student_identifier).first()
        form.instance.student = matched_student
        assign_request_owner(form.instance)
        response = super().form_valid(form)
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

    def get_queryset(self):
        queryset = StudentRequest.objects.select_related("student", "assigned_to")
        if is_student(self.request.user):
            student = current_student_for_user(self.request.user)
            queryset = queryset.filter(student=student)
        if self.request.GET.get("status"):
            queryset = queryset.filter(status=self.request.GET["status"])
        if self.request.GET.get("request_type"):
            queryset = queryset.filter(request_type=self.request.GET["request_type"])
        return queryset.order_by("status", "-created_at")

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
        return redirect("request_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = StudentRequest.STATUS_CHOICES
        context["type_choices"] = StudentRequest.REQUEST_TYPE_CHOICES
        context["request_status_summary"] = {
            "new": StudentRequest.objects.filter(status=StudentRequest.STATUS_NEW).count(),
            "in_review": StudentRequest.objects.filter(status=StudentRequest.STATUS_IN_REVIEW).count(),
            "approved": StudentRequest.objects.filter(status=StudentRequest.STATUS_APPROVED).count(),
            "completed": StudentRequest.objects.filter(status=StudentRequest.STATUS_COMPLETED).count(),
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
        return super().post(request, *args, **kwargs)

    def handle_response(self, request):
        form = StudentRequestResponseForm(request.POST, request.FILES, request_item=self.object)
        if form.is_valid():
            response_item = form.save(commit=False)
            response_item.request = self.object
            response_item.sent_by = request.user
            response_item.send_requested_at = timezone.now()
            response_item.save()
            if response_item.mark_complete and self.object.status != StudentRequest.STATUS_COMPLETED:
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
        response = super().form_valid(form)
        log_audit(self.request.user, "updated", self.object, {"section": "request"})
        messages.success(self.request, "Request updated.")
        return response


class PortalRequestCreateView(LoginRequiredMixin, CreateView):
    model = StudentRequest
    form_class = StudentRequestPublicForm
    template_name = "cases/portal_request_form.html"
    success_url = reverse_lazy("portal_dashboard")

    def dispatch(self, request, *args, **kwargs):
        if not current_student_for_user(request.user):
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        student = current_student_for_user(self.request.user)
        initial.update(
            {
                "submitted_by_name": student.full_name,
                "submitted_by_email": getattr(student.portal_access.user, "email", "") or student.parent_guardian_email,
                "student_identifier": student.student_id,
            }
        )
        return initial

    def form_valid(self, form):
        student = current_student_for_user(self.request.user)
        form.instance.student = student
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

    def get_queryset(self):
        queryset = CounsellingSession.objects.select_related("student", "counsellor", "linked_request")
        queryset = queryset.filter(student__in=student_queryset_for_user(self.request.user))
        if self.request.GET.get("status"):
            queryset = queryset.filter(status=self.request.GET["status"])
        if self.request.GET.get("session_type"):
            queryset = queryset.filter(session_type=self.request.GET["session_type"])
        return queryset.order_by("start_at")

    def post(self, request, *args, **kwargs):
        session = get_object_or_404(CounsellingSession, pk=request.POST.get("session_id"), student__in=student_queryset_for_user(request.user))
        if not can_edit_student(request.user, session.student):
            messages.error(request, "You do not have permission to send reminders for this session.")
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
        month_sessions = CounsellingSession.objects.select_related("student", "counsellor").filter(
            student__in=student_queryset_for_user(self.request.user),
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

    def get_initial(self):
        initial = super().get_initial()
        student_id = self.request.GET.get("student")
        if student_id:
            student = Student.objects.filter(pk=student_id).select_related("assigned_counsellor").first()
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
            linked_request = StudentRequest.objects.filter(pk=request_id).select_related("student").first()
            if linked_request:
                initial.update(
                    {
                        "linked_request": linked_request,
                        "student": linked_request.student,
                        "counsellor": linked_request.assigned_to or getattr(linked_request.student, "assigned_counsellor", None),
                        "confirmation_email": linked_request.submitted_by_email,
                        "status": CounsellingSession.STATUS_SCHEDULED if linked_request.status == StudentRequest.STATUS_APPROVED else CounsellingSession.STATUS_PENDING_APPROVAL,
                    }
                )
        initial.setdefault("start_at", timezone.localtime().strftime("%Y-%m-%dT%H:%M"))
        initial.setdefault("end_at", timezone.localtime(timezone.now() + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M"))
        return initial

    def form_valid(self, form):
        if not form.cleaned_data.get("confirmation_email"):
            form.instance.confirmation_email = (
                form.instance.student.parent_guardian_email or form.instance.linked_request and form.instance.linked_request.submitted_by_email
            )
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


class ReportsView(LoginRequiredMixin, TemplateView):
    template_name = "cases/reports.html"

    def post(self, request, *args, **kwargs):
        if not (is_admin(request.user) or is_counsellor(request.user)):
            messages.error(request, "You do not have permission to prepare reports.")
            return redirect("reports")
        form = PreparedReportForm(request.POST, request.FILES)
        if form.is_valid():
            report = form.save(commit=False)
            report.prepared_by = request.user
            if "send_report" in request.POST and report.recipient_email:
                report.send_requested_at = timezone.now()
            report.save()
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
        context["prepared_reports"] = PreparedReport.objects.select_related("student", "term", "prepared_by")[:12]
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
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not can_edit_student(request.user, self.object.student):
            messages.error(request, "You do not have permission to update this report.")
            return redirect("prepared_report_update", pk=self.object.pk)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        if "send_report" in self.request.POST and form.cleaned_data.get("recipient_email"):
            form.instance.send_requested_at = timezone.now()
            form.instance.sent_at = None
            form.instance.send_error = ""
        response = super().form_valid(form)
        log_audit(self.request.user, "updated", self.object, {"section": "prepared_report"})
        if "send_report" in self.request.POST and self.object.recipient_email:
            messages.success(self.request, "Report updated and queued for email delivery.")
        else:
            messages.success(self.request, "Report updated.")
        return response


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


class AdminToolsView(LoginRequiredMixin, TemplateView):
    template_name = "cases/admin_tools.html"

    def dispatch(self, request, *args, **kwargs):
        require_admin(request.user)
        return super().dispatch(request, *args, **kwargs)


class DatabaseBackupDownloadView(LoginRequiredMixin, View):
    def get(self, request):
        require_admin(request.user)
        db_path = settings.BASE_DIR / "db.sqlite3"
        if not db_path.exists():
            raise Http404("Database file not found.")
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
