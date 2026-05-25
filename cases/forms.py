from django import forms
from django.contrib.auth.models import Group, User

from .models import CommunicationLog, DocumentRequirement, FollowUpTask, Student, StudentNote
from .permissions import ROLE_NAMES, ensure_roles


class DateInput(forms.DateInput):
    input_type = "date"


class DateTimeInput(forms.DateTimeInput):
    input_type = "datetime-local"


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


def apply_bootstrap_classes(form):
    for field in form.fields.values():
        existing = field.widget.attrs.get("class", "")
        css_class = "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else "form-control"
        if isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
            css_class = "form-select"
        field.widget.attrs["class"] = f"{existing} {css_class}".strip()
