from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group, User

from .models import (
    CommunicationLog,
    CounsellingSession,
    DocumentRequirement,
    FollowUpTask,
    SessionChangeRequest,
    Student,
    StudentNote,
    StudentPortalAccess,
    StudentRequest,
)
from .permissions import ROLE_NAMES, ensure_roles


class DateInput(forms.DateInput):
    input_type = "date"


class DateTimeInput(forms.DateTimeInput):
    input_type = "datetime-local"


class LoginIDAuthenticationForm(AuthenticationForm):
    username = forms.CharField(label="Login ID")

    def clean(self):
        login_id = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")
        if login_id and password:
            resolved_username = login_id
            matched_user = User.objects.filter(email__iexact=login_id).first()
            if matched_user:
                resolved_username = matched_user.username
                self.cleaned_data["username"] = resolved_username
            self.user_cache = authenticate(
                self.request,
                username=resolved_username,
                password=password,
            )
            if self.user_cache is None:
                raise self.get_invalid_login_error()
            self.confirm_login_allowed(self.user_cache)
        return self.cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bootstrap_classes(self)


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = [
            "full_name",
            "student_id",
            "grade",
            "nationality",
            "preferred_language",
            "assigned_counsellor",
            "agency",
            "parent_guardian_name",
            "parent_guardian_email",
            "parent_guardian_phone",
            "academic_status",
            "attendance_concerns",
            "ossd_credit_progress",
            "graduation_status",
            "counselling_status",
            "homestay_status",
            "payment_status",
            "insurance_status",
            "target_country",
            "target_program",
            "target_universities",
            "ielts_english_status",
            "university_application_status",
            "overall_risk_level",
            "internal_summary",
            "is_active",
        ]
        widgets = {
            "attendance_concerns": forms.Textarea(attrs={"rows": 3}),
            "target_universities": forms.Textarea(attrs={"rows": 3}),
            "internal_summary": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_counsellor"].queryset = User.objects.filter(groups__name="Counsellor").distinct()
        apply_bootstrap_classes(self)


class StudentNoteForm(forms.ModelForm):
    class Meta:
        model = StudentNote
        fields = ["note"]
        widgets = {"note": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bootstrap_classes(self)


class FollowUpTaskForm(forms.ModelForm):
    class Meta:
        model = FollowUpTask
        fields = ["title", "description", "assigned_to", "due_date", "priority", "status"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3}), "due_date": DateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = User.objects.filter(groups__name__in=["Admin", "Counsellor"]).distinct()
        apply_bootstrap_classes(self)


class DocumentRequirementForm(forms.ModelForm):
    class Meta:
        model = DocumentRequirement
        fields = ["document_name", "status", "due_date", "notes"]
        widgets = {"due_date": DateInput(), "notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bootstrap_classes(self)


class CommunicationLogForm(forms.ModelForm):
    class Meta:
        model = CommunicationLog
        fields = ["direction", "method", "contact_person", "communicated_at", "summary"]
        widgets = {"communicated_at": DateTimeInput(), "summary": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bootstrap_classes(self)


class StudentFilterForm(forms.Form):
    assigned_counsellor = forms.ModelChoiceField(queryset=User.objects.none(), required=False)
    grade = forms.CharField(required=False)
    risk_level = forms.ChoiceField(required=False, choices=[("", "All")] + Student.RISK_LEVEL_CHOICES)
    payment_status = forms.ChoiceField(required=False, choices=[("", "All")] + Student.PAYMENT_STATUS_CHOICES)
    homestay_status = forms.ChoiceField(required=False, choices=[("", "All")] + Student.HOMESTAY_STATUS_CHOICES)
    university_application_status = forms.ChoiceField(
        required=False, choices=[("", "All")] + Student.APPLICATION_STATUS_CHOICES
    )
    missing_documents = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_counsellor"].queryset = User.objects.filter(groups__name="Counsellor").distinct()
        apply_bootstrap_classes(self)


class UserManagementForm(forms.ModelForm):
    role = forms.ChoiceField(choices=[(name, name) for name in ROLE_NAMES])
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=True),
        help_text="Leave blank when editing to keep the current password.",
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "username", "email", "is_active"]

    def __init__(self, *args, **kwargs):
        ensure_roles()
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            group = self.instance.groups.first()
            self.fields["role"].initial = group.name if group else ROLE_NAMES[2]
        apply_bootstrap_classes(self)

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if not self.instance.pk and not password:
            raise forms.ValidationError("A password is required when creating a new user.")
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)
        if commit:
            user.save()
            user.groups.clear()
            user.groups.add(Group.objects.get(name=self.cleaned_data["role"]))
        return user


class StudentPortalAccessForm(forms.Form):
    username = forms.CharField(max_length=150)
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput(render_value=True))
    is_active = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, student=None, **kwargs):
        self.student = student
        super().__init__(*args, **kwargs)
        if student and hasattr(student, "portal_access"):
            access = student.portal_access
            self.fields["username"].initial = access.user.username
            self.fields["email"].initial = access.user.email
            self.fields["is_active"].initial = access.is_active
        apply_bootstrap_classes(self)

    def clean_username(self):
        username = self.cleaned_data["username"]
        query = User.objects.filter(username__iexact=username)
        if self.student and hasattr(self.student, "portal_access"):
            query = query.exclude(pk=self.student.portal_access.user_id)
        if query.exists():
            raise forms.ValidationError("That username is already in use.")
        return username

    def save(self):
        access = getattr(self.student, "portal_access", None)
        if access:
            user = access.user
        else:
            user = User()
        user.username = self.cleaned_data["username"]
        user.email = self.cleaned_data["email"]
        user.first_name = self.student.full_name.split(" ")[0]
        user.last_name = " ".join(self.student.full_name.split(" ")[1:])
        user.is_active = self.cleaned_data["is_active"]
        user.set_password(self.cleaned_data["password"])
        user.save()
        user.groups.clear()
        user.groups.add(Group.objects.get(name="Student"))
        if access:
            access.is_active = self.cleaned_data["is_active"]
            access.save(update_fields=["is_active", "updated_at"])
        else:
            access = StudentPortalAccess.objects.create(
                student=self.student,
                user=user,
                is_active=self.cleaned_data["is_active"],
            )
        return access


class StudentRequestPublicForm(forms.ModelForm):
    class Meta:
        model = StudentRequest
        fields = [
            "submitted_by_name",
            "submitted_by_email",
            "student_identifier",
            "request_type",
            "title",
            "details",
            "preferred_date",
            "preferred_time",
        ]
        widgets = {
            "details": forms.Textarea(attrs={"rows": 4}),
            "preferred_date": DateInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bootstrap_classes(self)


class StudentRequestStaffForm(forms.ModelForm):
    class Meta:
        model = StudentRequest
        fields = [
            "student",
            "assigned_to",
            "request_type",
            "title",
            "details",
            "preferred_date",
            "preferred_time",
            "status",
            "internal_notes",
        ]
        widgets = {
            "details": forms.Textarea(attrs={"rows": 3}),
            "internal_notes": forms.Textarea(attrs={"rows": 3}),
            "preferred_date": DateInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = User.objects.filter(groups__name__in=["Admin", "Counsellor"]).distinct()
        apply_bootstrap_classes(self)


class CounsellingSessionForm(forms.ModelForm):
    class Meta:
        model = CounsellingSession
        fields = [
            "student",
            "linked_request",
            "counsellor",
            "session_type",
            "start_at",
            "end_at",
            "location",
            "meeting_link",
            "confirmation_email",
            "notes",
            "status",
        ]
        widgets = {
            "start_at": DateTimeInput(),
            "end_at": DateTimeInput(),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["counsellor"].queryset = User.objects.filter(groups__name__in=["Admin", "Counsellor"]).distinct()
        self.fields["linked_request"].queryset = StudentRequest.objects.exclude(status=StudentRequest.STATUS_CLOSED)
        apply_bootstrap_classes(self)

    def clean(self):
        cleaned = super().clean()
        start_at = cleaned.get("start_at")
        end_at = cleaned.get("end_at")
        if start_at and end_at and end_at <= start_at:
            self.add_error("end_at", "End time must be after the start time.")
        return cleaned


class SessionChangeRequestForm(forms.ModelForm):
    class Meta:
        model = SessionChangeRequest
        fields = ["requester_name", "requester_email", "requested_start", "requested_end", "reason"]
        widgets = {
            "requested_start": DateTimeInput(),
            "requested_end": DateTimeInput(),
            "reason": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bootstrap_classes(self)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("requested_start") and cleaned.get("requested_end"):
            if cleaned["requested_end"] <= cleaned["requested_start"]:
                self.add_error("requested_end", "End time must be after the start time.")
        return cleaned


def apply_bootstrap_classes(form):
    for field in form.fields.values():
        existing = field.widget.attrs.get("class", "")
        css_class = "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else "form-control"
        if isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
            css_class = "form-select"
        field.widget.attrs["class"] = f"{existing} {css_class}".strip()
