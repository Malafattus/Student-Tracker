import csv
import io
import zipfile
from datetime import timedelta

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
    CounsellingSessionForm,
    CommunicationLogForm,
    DocumentRequirementForm,
    FollowUpTaskForm,
    LoginIDAuthenticationForm,
    SessionChangeRequestForm,
    StudentRequestPublicForm,
    StudentRequestStaffForm,
    StudentFilterForm,
    StudentForm,
    StudentNoteForm,
    StudentPortalAccessForm,
    UserManagementForm,
)
from .models import (
    AuditLog,
    CommunicationLog,
    CounsellingSession,
    DocumentRequirement,
    FollowUpTask,
    SessionChangeRequest,
    Student,
    StudentPortalAccess,
    StudentRequest,
)
from .notifications import (
    send_request_confirmation,
    send_session_change_request_notice,
    send_session_confirmation,
    send_session_reminder,
)
from .permissions import can_edit_student, is_admin, is_counsellor, is_student, require_admin


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
        response = super().form_valid(form)
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
        if is_counsellor(self.request.user) and not is_admin(self.request.user):
            queryset = queryset.filter(Q(assigned_to=self.request.user) | Q(student__assigned_counsellor=self.request.user))
        if self.request.GET.get("status"):
            queryset = queryset.filter(status=self.request.GET["status"])
        if self.request.GET.get("request_type"):
            queryset = queryset.filter(request_type=self.request.GET["request_type"])
        return queryset.order_by("status", "-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = StudentRequest.STATUS_CHOICES
        context["type_choices"] = StudentRequest.REQUEST_TYPE_CHOICES
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
        response = super().form_valid(form)
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
