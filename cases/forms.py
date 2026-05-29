from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from django.contrib.auth.models import Group, User
from django.db.models import Q
from django.utils import timezone

from .file_security import validate_uploaded_file
from .models import (
    AcademicTerm,
    CommunicationLog,
    CommunicationTemplate,
    CounsellorAccessRequest,
    CounsellingSession,
    DocumentRequirement,
    FollowUpTask,
    ParentPortalAccess,
    PreparedReport,
    SecurityPolicy,
    SessionChangeRequest,
    Student,
    StudentNote,
    StudentPortalAccess,
    StudentRequest,
    StudentRequestResponse,
    StudentTermRecord,
    TermCourseEnrollment,
    CounsellorProfile,
    UserSecurityProfile,
)
from .permissions import ROLE_NAMES, ensure_roles


class DateInput(forms.DateInput):
    input_type = "date"


class DateTimeInput(forms.DateTimeInput):
    input_type = "datetime-local"


class MultiFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultiFileField(forms.FileField):
    widget = MultiFileInput

    def clean(self, data, initial=None):
        single_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_clean(item, initial) for item in data if item]
        if not data:
            return []
        return [single_clean(data, initial)]


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
            "date_of_birth",
            "nationality",
            "support_team",
            "preferred_language",
            "assigned_counsellor",
            "agency",
            "parent_guardian_name",
            "parent_guardian_email",
            "parent_guardian_phone",
            "academic_status",
            "case_stage",
            "next_review_date",
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
            "required_credits",
            "credits_remaining_manual",
            "volunteer_hours_required",
            "volunteer_hours_remaining_manual",
            "osslt_status",
            "overall_risk_level",
            "internal_summary",
            "is_active",
        ]
        widgets = {
            "date_of_birth": DateInput(),
            "next_review_date": DateInput(),
            "attendance_concerns": forms.Textarea(attrs={"rows": 3}),
            "target_universities": forms.Textarea(attrs={"rows": 3}),
            "internal_summary": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_counsellor"].queryset = User.objects.filter(groups__name="Counsellor").distinct()
        self.fields["required_credits"].label = "Total credits required"
        self.fields["credits_remaining_manual"].label = "Credits remaining"
        self.fields["credits_remaining_manual"].help_text = "Enter how many credits the student still needs."
        self.fields["volunteer_hours_required"].label = "Total volunteer hours required"
        self.fields["volunteer_hours_remaining_manual"].label = "Volunteer hours remaining"
        self.fields["volunteer_hours_remaining_manual"].help_text = "Enter how many volunteer hours the student still needs."
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
        fields = [
            "direction",
            "method",
            "category",
            "audience",
            "contact_person",
            "recipient_email",
            "subject",
            "communicated_at",
            "summary",
        ]
        widgets = {"communicated_at": DateTimeInput(), "summary": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bootstrap_classes(self)


class StudentFilterForm(forms.Form):
    assigned_counsellor = forms.ModelChoiceField(queryset=User.objects.none(), required=False)
    grade = forms.CharField(required=False)
    support_team = forms.CharField(required=False)
    case_stage = forms.ChoiceField(required=False, choices=[("", "All")] + Student.CASE_STAGE_CHOICES)
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
    primary_team = forms.CharField(
        required=False,
        help_text="Used for counsellor visibility. Example: Korean Team.",
    )
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=True),
        help_text="Leave blank when editing to keep the current password.",
    )
    must_reset_password = forms.BooleanField(
        required=False,
        help_text="Force this user to set a fresh password the next time they sign in.",
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
            profile = getattr(self.instance, "counsellor_profile", None)
            if profile:
                self.fields["primary_team"].initial = profile.primary_team
            security_profile = getattr(self.instance, "security_profile", None)
            if security_profile:
                self.fields["must_reset_password"].initial = security_profile.must_reset_password
        apply_bootstrap_classes(self)

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if not self.instance.pk and not password:
            raise forms.ValidationError("A password is required when creating a new user.")
        if password:
            minimum_length = SecurityPolicy.get_solo().minimum_password_length
            if len(password) < minimum_length:
                raise forms.ValidationError(f"Passwords must be at least {minimum_length} characters long.")
        return password

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        role = self.cleaned_data.get("role") or ROLE_NAMES[2]
        policy = SecurityPolicy.get_solo()
        if (
            email
            and policy.require_staff_domain_match
            and role in {"Admin", "Counsellor", "Viewer"}
        ):
            domain = email.split("@")[-1].lower() if "@" in email else ""
            if domain not in policy.allowed_staff_domains:
                raise forms.ValidationError("This email domain is not allowed for staff accounts.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)
        if commit:
            user.save()
            user.groups.clear()
            user.groups.add(Group.objects.get(name=self.cleaned_data["role"]))
            profile = getattr(user, "counsellor_profile", None)
            if self.cleaned_data["role"] == "Counsellor":
                if profile:
                    profile.primary_team = self.cleaned_data.get("primary_team", "")
                    profile.save(update_fields=["primary_team", "updated_at"])
                else:
                    CounsellorProfile.objects.create(user=user, primary_team=self.cleaned_data.get("primary_team", ""))
            elif profile and profile.primary_team:
                profile.primary_team = ""
                profile.save(update_fields=["primary_team", "updated_at"])
            security_profile, _ = UserSecurityProfile.objects.get_or_create(user=user)
            security_profile.must_reset_password = self.cleaned_data.get("must_reset_password", False)
            if password:
                security_profile.password_changed_at = timezone.now()
            security_profile.save()
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
        security_profile, _ = UserSecurityProfile.objects.get_or_create(user=user)
        security_profile.password_changed_at = timezone.now()
        if not access and SecurityPolicy.get_solo().require_password_reset_for_new_accounts:
            security_profile.must_reset_password = True
        security_profile.save()
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


class ParentPortalAccessForm(forms.Form):
    existing_parent_account = forms.ModelChoiceField(queryset=User.objects.none(), required=False)
    username = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=False)
    password = forms.CharField(required=False, widget=forms.PasswordInput(render_value=True))
    relationship_label = forms.ChoiceField(choices=ParentPortalAccess.RELATIONSHIP_CHOICES)
    is_active = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, student=None, **kwargs):
        self.student = student
        super().__init__(*args, **kwargs)
        self.fields["existing_parent_account"].queryset = User.objects.filter(groups__name="Parent").distinct().order_by(
            "username"
        )
        apply_bootstrap_classes(self)

    def clean(self):
        cleaned_data = super().clean()
        existing_account = cleaned_data.get("existing_parent_account")
        if existing_account:
            return cleaned_data
        if not cleaned_data.get("username"):
            self.add_error("username", "Enter a username or choose an existing parent account.")
        if not cleaned_data.get("email"):
            self.add_error("email", "Enter an email address or choose an existing parent account.")
        if not cleaned_data.get("password"):
            self.add_error("password", "Enter a password for the new parent login.")
        return cleaned_data

    def clean_username(self):
        username = self.cleaned_data.get("username")
        if not username:
            return username
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("That username is already in use.")
        return username

    def save(self):
        existing_account = self.cleaned_data.get("existing_parent_account")
        if existing_account:
            user = existing_account
            user.groups.add(Group.objects.get(name="Parent"))
        else:
            user = User.objects.create_user(
                username=self.cleaned_data["username"],
                email=self.cleaned_data["email"],
                password=self.cleaned_data["password"],
                first_name=self.student.parent_guardian_name.split(" ")[0] if self.student.parent_guardian_name else "",
                last_name=" ".join(self.student.parent_guardian_name.split(" ")[1:]) if self.student.parent_guardian_name else "",
                is_active=self.cleaned_data.get("is_active", True),
            )
            user.groups.add(Group.objects.get(name="Parent"))
        security_profile, _ = UserSecurityProfile.objects.get_or_create(user=user)
        if not existing_account:
            security_profile.password_changed_at = timezone.now()
            if SecurityPolicy.get_solo().require_password_reset_for_new_accounts:
                security_profile.must_reset_password = True
        security_profile.save()
        access, _ = ParentPortalAccess.objects.update_or_create(
            student=self.student,
            user=user,
            defaults={
                "relationship_label": self.cleaned_data["relationship_label"],
                "is_active": self.cleaned_data.get("is_active", True),
            },
        )
        return access


class CounsellorAccessRequestForm(forms.ModelForm):
    class Meta:
        model = CounsellorAccessRequest
        fields = ["student", "reason"]
        widgets = {"reason": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, counsellor=None, **kwargs):
        self.counsellor = counsellor
        super().__init__(*args, **kwargs)
        queryset = Student.objects.all().order_by("full_name")
        if counsellor is not None:
            counsellor_team = getattr(getattr(counsellor, "counsellor_profile", None), "primary_team", "")
            queryset = queryset.exclude(assigned_counsellor=counsellor).exclude(
                extra_counsellor_access__counsellor=counsellor,
                extra_counsellor_access__is_active=True,
            )
            if counsellor_team:
                queryset = queryset.exclude(support_team__iexact=counsellor_team)
        self.fields["student"].queryset = queryset.distinct()
        apply_bootstrap_classes(self)


class StudentRequestPublicForm(forms.ModelForm):
    attachments = MultiFileField(
        required=False,
        help_text="Optional: upload transcript samples, screenshots, or supporting documents.",
    )

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

    def clean_attachments(self):
        attachments = self.cleaned_data.get("attachments") or []
        for attachment in attachments:
            validate_uploaded_file(attachment)
        return attachments


class StudentPortalRequestForm(forms.ModelForm):
    attachments = MultiFileField(
        required=False,
        help_text="Optional: upload transcript samples, screenshots, or supporting documents.",
    )

    class Meta:
        model = StudentRequest
        fields = [
            "request_type",
            "title",
            "details",
            "preferred_date",
            "preferred_time",
        ]
        widgets = {
            "details": forms.Textarea(attrs={"rows": 5}),
            "preferred_date": DateInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bootstrap_classes(self)

    def clean_attachments(self):
        attachments = self.cleaned_data.get("attachments") or []
        for attachment in attachments:
            validate_uploaded_file(attachment)
        return attachments


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
    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["counsellor"].queryset = User.objects.filter(groups__name__in=["Admin", "Counsellor"]).distinct()
        linked_request_queryset = StudentRequest.objects.exclude(status=StudentRequest.STATUS_CLOSED)
        if user is not None:
            from .permissions import is_admin, is_counsellor

            if is_admin(user):
                self.fields["student"].queryset = Student.objects.select_related("assigned_counsellor").all()
            elif is_counsellor(user):
                team_name = getattr(getattr(user, "counsellor_profile", None), "primary_team", "")
                counsellor_filters = Q(assigned_counsellor=user) | Q(
                    extra_counsellor_access__counsellor=user,
                    extra_counsellor_access__is_active=True,
                )
                if team_name:
                    counsellor_filters |= Q(support_team__iexact=team_name)
                self.fields["student"].queryset = Student.objects.select_related("assigned_counsellor").filter(
                    counsellor_filters
                ).distinct()
                linked_request_queryset = linked_request_queryset.filter(
                    Q(student__in=self.fields["student"].queryset) | Q(student__isnull=True, assigned_to=user)
                )
        self.fields["linked_request"].queryset = linked_request_queryset.distinct()
        apply_bootstrap_classes(self)

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

    def clean(self):
        cleaned = super().clean()
        start_at = cleaned.get("start_at")
        end_at = cleaned.get("end_at")
        if start_at and end_at and end_at <= start_at:
            self.add_error("end_at", "End time must be after the start time.")
        linked_request = cleaned.get("linked_request")
        student = cleaned.get("student")
        if linked_request and student and linked_request.student and linked_request.student_id != student.id:
            self.add_error("linked_request", "This request belongs to a different student.")
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


class StudentRequestResponseForm(forms.ModelForm):
    template = forms.ModelChoiceField(queryset=CommunicationTemplate.objects.none(), required=False)

    class Meta:
        model = StudentRequestResponse
        fields = ["subject", "recipient_email", "message", "attachment", "mark_complete"]
        widgets = {
            "message": forms.Textarea(attrs={"rows": 6}),
        }

    def __init__(self, *args, request_item=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["template"].queryset = CommunicationTemplate.objects.filter(
            is_active=True, template_type=CommunicationTemplate.TYPE_REQUEST
        )
        self.fields["subject"].required = False
        self.fields["message"].required = False
        if request_item:
            self.fields["subject"].initial = f"Update on your request: {request_item.title}"
            self.fields["recipient_email"].initial = request_item.submitted_by_email
            self.fields["message"].initial = (
                f"Hello {request_item.submitted_by_name},\n\n"
                f"We have reviewed your request: {request_item.title}.\n\n"
                "Update:\n"
            )
        apply_bootstrap_classes(self)

    def apply_selected_template(self):
        template = self.cleaned_data.get("template")
        if not template:
            return
        if not self.cleaned_data.get("subject"):
            self.cleaned_data["subject"] = template.subject_template
        if not self.cleaned_data.get("message"):
            self.cleaned_data["message"] = template.body_template

    def clean_attachment(self):
        attachment = self.cleaned_data.get("attachment")
        if attachment:
            validate_uploaded_file(attachment)
        return attachment

    def clean(self):
        cleaned = super().clean()
        template = cleaned.get("template")
        if template:
            if not cleaned.get("subject"):
                cleaned["subject"] = template.subject_template
                self.cleaned_data["subject"] = template.subject_template
            if not cleaned.get("message"):
                cleaned["message"] = template.body_template
                self.cleaned_data["message"] = template.body_template
        if not cleaned.get("subject"):
            self.add_error("subject", "Add a subject or choose a template.")
        if not cleaned.get("message"):
            self.add_error("message", "Add a message or choose a template.")
        return cleaned


class RequestTaskForm(forms.ModelForm):
    class Meta:
        model = FollowUpTask
        fields = ["title", "description", "assigned_to", "due_date", "priority"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "due_date": DateInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = User.objects.filter(groups__name__in=["Admin", "Counsellor"]).distinct()
        apply_bootstrap_classes(self)


class StudentTermRecordForm(forms.ModelForm):
    class Meta:
        model = StudentTermRecord
        fields = [
            "term",
            "planned_course_count",
            "is_completed",
            "academic_summary",
            "attendance_summary",
            "counselling_summary",
            "agent_notes",
        ]
        widgets = {
            "academic_summary": forms.Textarea(attrs={"rows": 3}),
            "attendance_summary": forms.Textarea(attrs={"rows": 3}),
            "counselling_summary": forms.Textarea(attrs={"rows": 3}),
            "agent_notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        student = kwargs.pop("student", None)
        super().__init__(*args, **kwargs)
        if student:
            used_terms = student.term_records.values_list("term_id", flat=True)
            if self.instance.pk:
                self.fields["term"].queryset = AcademicTerm.objects.filter(is_active=True) | AcademicTerm.objects.filter(
                    pk=self.instance.term_id
                )
            else:
                self.fields["term"].queryset = AcademicTerm.objects.filter(is_active=True).exclude(pk__in=used_terms)
        apply_bootstrap_classes(self)


class TermCourseEnrollmentForm(forms.ModelForm):
    class Meta:
        model = TermCourseEnrollment
        fields = ["course_name", "course_code", "teacher_name", "midterm_grade", "final_grade", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["midterm_grade"].widget.attrs["min"] = 0
        self.fields["midterm_grade"].widget.attrs["max"] = 100
        self.fields["final_grade"].widget.attrs["min"] = 0
        self.fields["final_grade"].widget.attrs["max"] = 100
        apply_bootstrap_classes(self)

    def clean(self):
        cleaned = super().clean()
        for field_name in ["midterm_grade", "final_grade"]:
            grade = cleaned.get(field_name)
            if grade is not None and not 0 <= grade <= 100:
                self.add_error(field_name, "Grades must be between 0 and 100.")
        return cleaned


class PreparedReportForm(forms.ModelForm):
    class Meta:
        model = PreparedReport
        fields = [
            "student",
            "term",
            "audience",
            "title",
            "recipient_name",
            "recipient_email",
            "summary",
            "academic_progress",
            "attendance_update",
            "counselling_update",
            "recommendations",
            "attachment",
        ]
        widgets = {
            "summary": forms.Textarea(attrs={"rows": 3}),
            "academic_progress": forms.Textarea(attrs={"rows": 4}),
            "attendance_update": forms.Textarea(attrs={"rows": 3}),
            "counselling_update": forms.Textarea(attrs={"rows": 3}),
            "recommendations": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        student = kwargs.pop("student", None)
        super().__init__(*args, **kwargs)
        self.fields["term"].queryset = AcademicTerm.objects.filter(is_active=True)
        if student:
            self.fields["student"].initial = student
        apply_bootstrap_classes(self)

    def clean_attachment(self):
        attachment = self.cleaned_data.get("attachment")
        if attachment:
            validate_uploaded_file(attachment)
        return attachment


class CommunicationTemplateForm(forms.ModelForm):
    class Meta:
        model = CommunicationTemplate
        fields = ["name", "template_type", "audience", "subject_template", "body_template", "is_active"]
        widgets = {
            "body_template": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bootstrap_classes(self)


class SecurityPolicyForm(forms.ModelForm):
    class Meta:
        model = SecurityPolicy
        fields = [
            "require_staff_domain_match",
            "allowed_staff_email_domains",
            "block_noncompliant_staff_signins",
            "restrict_staff_to_allowed_ip_ranges",
            "allowed_staff_ip_ranges",
            "require_school_managed_auth_for_staff",
            "break_glass_usernames",
            "require_password_reset_for_new_accounts",
            "require_mfa_for_staff",
            "require_mfa_for_all_accounts",
            "minimum_password_length",
            "password_rotation_days",
            "dormant_account_review_days",
            "approved_hosting_environment",
            "privacy_owner_name",
            "privacy_owner_email",
            "security_owner_name",
            "security_owner_email",
            "operations_owner_name",
            "operations_owner_email",
            "last_privacy_review_at",
            "last_security_test_at",
            "last_operations_review_at",
        ]
        widgets = {
            "allowed_staff_email_domains": forms.Textarea(attrs={"rows": 3}),
            "allowed_staff_ip_ranges": forms.Textarea(attrs={"rows": 3}),
            "break_glass_usernames": forms.Textarea(attrs={"rows": 2}),
            "last_privacy_review_at": forms.DateInput(attrs={"type": "date"}),
            "last_security_test_at": forms.DateInput(attrs={"type": "date"}),
            "last_operations_review_at": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["allowed_staff_email_domains"].help_text = "Separate multiple allowed domains with commas."
        self.fields["minimum_password_length"].help_text = "Applies to passwords created or changed inside this app."
        self.fields["block_noncompliant_staff_signins"].help_text = "If turned on, staff who do not match the allowed email rules will be blocked from signing in."
        self.fields["restrict_staff_to_allowed_ip_ranges"].help_text = "Limit staff-style access to approved school or VPN IP ranges."
        self.fields["allowed_staff_ip_ranges"].help_text = "Enter approved IP addresses or CIDR ranges, separated with commas. Example: 203.0.113.10, 203.0.113.0/24"
        self.fields["require_school_managed_auth_for_staff"].help_text = "Turn this on when staff must sign in through the school's identity system instead of local passwords."
        self.fields["break_glass_usernames"].help_text = "Optional emergency local staff accounts that may still sign in directly. Separate multiple usernames with commas."
        self.fields["require_mfa_for_staff"].help_text = "Require staff-style accounts to complete a verification code step at sign-in."
        self.fields["require_mfa_for_all_accounts"].help_text = "Require MFA for students, parents, viewers, counsellors, and admins."
        self.fields["password_rotation_days"].help_text = "After this many days, staff will be asked to set a fresh password."
        self.fields["dormant_account_review_days"].help_text = "Accounts that have not signed in within this many days will be highlighted for review."
        self.fields["approved_hosting_environment"].help_text = "Record the approved production host, such as a managed cloud or school IT platform."
        self.fields["last_privacy_review_at"].help_text = "Date of the most recent privacy review for this system."
        self.fields["last_security_test_at"].help_text = "Date of the most recent formal security test or review."
        self.fields["last_operations_review_at"].help_text = "Date of the most recent operations or ownership review."
        apply_bootstrap_classes(self)


class UserSecurityProfileForm(forms.ModelForm):
    class Meta:
        model = UserSecurityProfile
        fields = ["must_reset_password", "manually_locked", "mfa_enabled", "security_note"]
        widgets = {
            "security_note": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bootstrap_classes(self)


class RequiredPasswordChangeForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bootstrap_classes(self)

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("new_password2")
        if not password:
            return cleaned_data
        minimum_length = SecurityPolicy.get_solo().minimum_password_length
        if len(password) < minimum_length:
            raise forms.ValidationError(f"Passwords must be at least {minimum_length} characters long.")
        return cleaned_data


class MfaCodeForm(forms.Form):
    code = forms.CharField(
        max_length=6,
        min_length=6,
        label="Verification code",
        help_text="Enter the 6-digit code from your authenticator app.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bootstrap_classes(self)

    def clean_code(self):
        code = "".join((self.cleaned_data.get("code") or "").split())
        if not code.isdigit() or len(code) != 6:
            raise forms.ValidationError("Enter the 6-digit verification code.")
        return code


class SensitiveActionVerificationForm(forms.Form):
    password = forms.CharField(
        widget=forms.PasswordInput(render_value=True),
        help_text="Enter your current password to continue.",
    )
    code = forms.CharField(
        max_length=6,
        min_length=6,
        required=False,
        label="Verification code",
        help_text="If your account uses multi-factor verification, enter the current 6-digit code.",
    )
    export_passphrase = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=True),
        label="Export password",
        help_text="Create a password for this encrypted download.",
    )
    export_passphrase_confirm = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=True),
        label="Confirm export password",
        help_text="Re-enter the export password to avoid locking yourself out of the file.",
    )

    def __init__(self, *args, user=None, require_mfa=False, require_export_passphrase=False, **kwargs):
        self.user = user
        self.require_mfa = require_mfa
        self.require_export_passphrase = require_export_passphrase
        super().__init__(*args, **kwargs)
        if not require_mfa:
            self.fields["code"].widget = forms.HiddenInput()
            self.fields["code"].required = False
            self.fields["code"].help_text = ""
        if not require_export_passphrase:
            self.fields["export_passphrase"].widget = forms.HiddenInput()
            self.fields["export_passphrase"].required = False
            self.fields["export_passphrase"].help_text = ""
            self.fields["export_passphrase_confirm"].widget = forms.HiddenInput()
            self.fields["export_passphrase_confirm"].required = False
            self.fields["export_passphrase_confirm"].help_text = ""
        apply_bootstrap_classes(self)

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if not self.user or not self.user.check_password(password):
            raise forms.ValidationError("That password did not match your account.")
        return password

    def clean_code(self):
        code = "".join((self.cleaned_data.get("code") or "").split())
        if self.require_mfa:
            if not code.isdigit() or len(code) != 6:
                raise forms.ValidationError("Enter the 6-digit verification code.")
        return code

    def clean(self):
        cleaned_data = super().clean()
        if not self.require_export_passphrase:
            return cleaned_data
        passphrase = cleaned_data.get("export_passphrase") or ""
        confirmation = cleaned_data.get("export_passphrase_confirm") or ""
        if len(passphrase) < 12:
            self.add_error("export_passphrase", "Use at least 12 characters for the export password.")
        if passphrase != confirmation:
            self.add_error("export_passphrase_confirm", "The export passwords did not match.")
        return cleaned_data


def apply_bootstrap_classes(form):
    for field in form.fields.values():
        existing = field.widget.attrs.get("class", "")
        css_class = "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else "form-control"
        if isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
            css_class = "form-select"
        field.widget.attrs["class"] = f"{existing} {css_class}".strip()
