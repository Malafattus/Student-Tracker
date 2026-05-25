from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from .audit import log_audit
from .forms import (
    CommunicationLogForm,
    DocumentRequirementForm,
    FollowUpTaskForm,
    StudentFilterForm,
    StudentForm,
    StudentNoteForm,
    UserManagementForm,
)
from .models import AuditLog, CommunicationLog, DocumentRequirement, FollowUpTask, Student
from .permissions import can_edit_student, ensure_roles, is_admin, is_counsellor, require_admin


def student_queryset_for_user(user):
    qs = Student.objects.select_related("assigned_counsellor")
    if is_admin(user) or user.is_superuser or user.groups.filter(name="Viewer").exists():
        return qs
    if is_counsellor(user):
        return qs.filter(assigned_counsellor=user)
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
        }
        context["recent_students"] = students.order_by("-updated_at")[:8]
        context["recent_audit_logs"] = AuditLog.objects.filter(
            Q(model_name="Student") | Q(model_name="FollowUpTask") | Q(model_name="StudentNote")
        )[:8]
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
            "notes", "tasks", "documents", "communications"
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
