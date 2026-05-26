import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse


class TimeStampedModel(models.Model):
    """Shared timestamps for the main operational records."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Student(TimeStampedModel):
    STATUS_GOOD = "good"
    STATUS_MONITOR = "monitor"
    STATUS_CONCERN = "concern"
    STATUS_AT_RISK = "at_risk"
    STATUS_COMPLETE = "complete"
    STATUS_PENDING = "pending"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_ACTIVE = "active"
    STATUS_CLOSED = "closed"
    OSSLT_PENDING = "pending"
    OSSLT_PASSED = "passed"
    OSSLT_OLC4O = "olc4o"
    OSSLT_OLC4O_COMPLETED = "olc4o_completed"
    OSSLT_EXEMPT = "exempt"
    STAGE_NEW = "new"
    STAGE_ACTIVE = "active"
    STAGE_WAITING_STUDENT = "waiting_student"
    STAGE_WAITING_PARENT = "waiting_parent"
    STAGE_APPLICATION = "application_in_progress"
    STAGE_RESOLVED = "resolved"

    YES_NO_CHOICES = [
        ("ok", "OK"),
        ("attention", "Needs Attention"),
        ("issue", "Issue"),
    ]
    ACADEMIC_STATUS_CHOICES = [
        (STATUS_GOOD, "Good Standing"),
        (STATUS_MONITOR, "Monitor"),
        (STATUS_CONCERN, "Concern"),
        (STATUS_AT_RISK, "At Risk"),
    ]
    PROGRESS_CHOICES = [
        (STATUS_ON_TRACK := "on_track", "On Track"),
        (STATUS_BEHIND := "behind", "Behind"),
        (STATUS_COMPLETE, "Complete"),
    ]
    GRADUATION_STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_IN_PROGRESS, "In Progress"),
        (STATUS_COMPLETE, "Complete"),
    ]
    COUNSELLING_STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        ("application_support", "Application Support"),
        ("waiting_family", "Waiting on Family"),
        (STATUS_CLOSED, "Closed"),
    ]
    APPLICATION_STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        ("researching", "Researching"),
        ("applying", "Applying"),
        ("submitted", "Submitted"),
        ("offer_received", "Offer Received"),
        ("accepted", "Accepted"),
    ]
    RISK_LEVEL_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("urgent", "Urgent"),
    ]
    PAYMENT_STATUS_CHOICES = [
        ("clear", "Clear"),
        ("pending", "Pending"),
        ("overdue", "Overdue"),
        ("plan_needed", "Plan Needed"),
    ]
    HOMESTAY_STATUS_CHOICES = [
        ("not_needed", "Not Needed"),
        ("searching", "Searching"),
        ("confirmed", "Confirmed"),
        ("issue", "Issue"),
    ]
    DOCUMENT_STATUS_CHOICES = [
        ("complete", "Complete"),
        ("pending", "Pending"),
        ("missing", "Missing"),
    ]
    CASE_STAGE_CHOICES = [
        (STAGE_NEW, "New"),
        (STAGE_ACTIVE, "Active"),
        (STAGE_WAITING_STUDENT, "Waiting on Student"),
        (STAGE_WAITING_PARENT, "Waiting on Parent/Agent"),
        (STAGE_APPLICATION, "Application in Progress"),
        (STAGE_RESOLVED, "Resolved"),
    ]
    OSSLT_STATUS_CHOICES = [
        (OSSLT_PENDING, "Pending"),
        (OSSLT_PASSED, "Passed OSSLT"),
        (OSSLT_OLC4O, "Needs OLC4O"),
        (OSSLT_OLC4O_COMPLETED, "Completed OLC4O"),
        (OSSLT_EXEMPT, "Exempt"),
    ]

    full_name = models.CharField(max_length=255)
    student_id = models.CharField(max_length=50, unique=True)
    grade = models.CharField(max_length=20)
    date_of_birth = models.DateField(blank=True, null=True)
    nationality = models.CharField(max_length=100)
    support_team = models.CharField(max_length=100, blank=True)
    preferred_language = models.CharField(max_length=100, blank=True)
    assigned_counsellor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="assigned_students",
    )
    agency = models.CharField(max_length=255, blank=True)
    parent_guardian_name = models.CharField(max_length=255, blank=True)
    parent_guardian_email = models.EmailField(blank=True)
    parent_guardian_phone = models.CharField(max_length=50, blank=True)
    academic_status = models.CharField(max_length=30, choices=ACADEMIC_STATUS_CHOICES, default=STATUS_GOOD)
    attendance_concerns = models.TextField(blank=True)
    ossd_credit_progress = models.CharField(max_length=30, choices=PROGRESS_CHOICES, default=STATUS_ON_TRACK)
    graduation_status = models.CharField(max_length=30, choices=GRADUATION_STATUS_CHOICES, default=STATUS_PENDING)
    counselling_status = models.CharField(max_length=30, choices=COUNSELLING_STATUS_CHOICES, default=STATUS_ACTIVE)
    homestay_status = models.CharField(max_length=30, choices=HOMESTAY_STATUS_CHOICES, default="not_needed")
    payment_status = models.CharField(max_length=30, choices=PAYMENT_STATUS_CHOICES, default="clear")
    insurance_status = models.CharField(max_length=20, choices=DOCUMENT_STATUS_CHOICES, default="pending")
    target_country = models.CharField(max_length=100, blank=True)
    target_program = models.CharField(max_length=255, blank=True)
    target_universities = models.TextField(blank=True)
    ielts_english_status = models.CharField(max_length=255, blank=True)
    university_application_status = models.CharField(
        max_length=30, choices=APPLICATION_STATUS_CHOICES, default=STATUS_PENDING
    )
    overall_risk_level = models.CharField(max_length=20, choices=RISK_LEVEL_CHOICES, default="low")
    internal_summary = models.TextField(blank=True)
    case_stage = models.CharField(max_length=30, choices=CASE_STAGE_CHOICES, default=STAGE_ACTIVE)
    next_review_date = models.DateField(blank=True, null=True)
    required_credits = models.PositiveSmallIntegerField(default=30)
    credits_remaining_manual = models.PositiveSmallIntegerField(blank=True, null=True)
    volunteer_hours_required = models.PositiveSmallIntegerField(default=40)
    volunteer_hours_completed = models.PositiveSmallIntegerField(default=0)
    volunteer_hours_remaining_manual = models.PositiveSmallIntegerField(blank=True, null=True)
    osslt_status = models.CharField(max_length=30, choices=OSSLT_STATUS_CHOICES, default=OSSLT_PENDING)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return f"{self.full_name} ({self.student_id})"

    def get_absolute_url(self):
        return reverse("student_detail", args=[self.pk])

    def contact_emails(self):
        emails = []
        if self.parent_guardian_email:
            emails.append(self.parent_guardian_email)
        if hasattr(self, "portal_access") and self.portal_access.user.email:
            emails.append(self.portal_access.user.email)
        for parent_access in self.parent_access_links.select_related("user").filter(is_active=True):
            if parent_access.user.email:
                emails.append(parent_access.user.email)
        return emails

    @property
    def term_earned_credits(self):
        return sum(record.earned_credit_count for record in self.term_records.all())

    @property
    def earned_credits(self):
        if self.credits_remaining_manual is not None:
            return max(self.required_credits - self.credits_remaining_manual, 0)
        return self.term_earned_credits

    @property
    def credits_remaining(self):
        if self.credits_remaining_manual is not None:
            return min(max(self.credits_remaining_manual, 0), self.required_credits)
        return max(self.required_credits - self.term_earned_credits, 0)

    @property
    def volunteer_hours_completed_total(self):
        if self.volunteer_hours_remaining_manual is not None:
            return max(self.volunteer_hours_required - self.volunteer_hours_remaining_manual, 0)
        return min(self.volunteer_hours_completed, self.volunteer_hours_required)

    @property
    def volunteer_hours_remaining(self):
        if self.volunteer_hours_remaining_manual is not None:
            return min(max(self.volunteer_hours_remaining_manual, 0), self.volunteer_hours_required)
        return max(self.volunteer_hours_required - self.volunteer_hours_completed, 0)


class CounsellorProfile(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="counsellor_profile")
    primary_team = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["user__first_name", "user__last_name", "user__username"]

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class AcademicTerm(TimeStampedModel):
    school_year = models.CharField(max_length=20)
    name = models.CharField(max_length=100)
    display_order = models.PositiveIntegerField(default=1)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["school_year", "display_order"]
        unique_together = ["school_year", "name"]

    def __str__(self):
        return f"{self.school_year} {self.name}"

    @property
    def duration_days(self):
        if not self.start_date or not self.end_date:
            return None
        return (self.end_date - self.start_date).days

    @property
    def is_standard_length_term(self):
        duration_days = self.duration_days
        return duration_days is not None and duration_days >= 56

    @property
    def midterm_checkpoint_date(self):
        if not self.start_date or not self.end_date:
            return None
        if self.is_standard_length_term:
            return self.start_date + timedelta(weeks=5)
        duration = self.end_date - self.start_date
        return self.start_date + duration / 2

    @property
    def final_checkpoint_date(self):
        if not self.start_date or not self.end_date:
            return None
        if self.is_standard_length_term:
            ten_week_mark = self.start_date + timedelta(weeks=10)
            return ten_week_mark if ten_week_mark <= self.end_date else self.end_date
        return self.end_date


class StudentTermRecord(TimeStampedModel):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="term_records")
    term = models.ForeignKey(AcademicTerm, on_delete=models.CASCADE, related_name="student_records")
    planned_course_count = models.PositiveSmallIntegerField(default=0)
    is_completed = models.BooleanField(default=False)
    midterm_reminder_sent_at = models.DateTimeField(blank=True, null=True)
    final_reminder_sent_at = models.DateTimeField(blank=True, null=True)
    academic_summary = models.TextField(blank=True)
    attendance_summary = models.TextField(blank=True)
    counselling_summary = models.TextField(blank=True)
    agent_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["term__school_year", "term__display_order"]
        unique_together = ["student", "term"]

    def __str__(self):
        return f"{self.student.full_name} - {self.term}"

    @property
    def course_load(self):
        actual_courses = self.courses.count()
        return actual_courses or self.planned_course_count

    @property
    def passed_course_count(self):
        actual_courses = self.courses.count()
        if actual_courses:
            return self.courses.filter(final_grade__gte=50).count()
        return self.planned_course_count if self.is_completed else 0

    @property
    def earned_credit_count(self):
        return self.passed_course_count

    @property
    def midterm_recorded_count(self):
        return self.courses.exclude(midterm_grade__isnull=True).count()

    @property
    def final_recorded_count(self):
        return self.courses.exclude(final_grade__isnull=True).count()

    @property
    def needs_midterm_grades(self):
        actual_courses = self.courses.count()
        if not actual_courses:
            return False
        return self.midterm_recorded_count < actual_courses

    @property
    def needs_final_grades(self):
        actual_courses = self.courses.count()
        if not actual_courses:
            return False
        return self.final_recorded_count < actual_courses

    @property
    def next_report_checkpoint(self):
        if self.term.final_checkpoint_date and self.needs_final_grades:
            return self.term.final_checkpoint_date, "final"
        if self.term.midterm_checkpoint_date and self.needs_midterm_grades:
            return self.term.midterm_checkpoint_date, "midterm"
        return None, None


class TermCourseEnrollment(TimeStampedModel):
    term_record = models.ForeignKey(StudentTermRecord, on_delete=models.CASCADE, related_name="courses")
    course_name = models.CharField(max_length=255)
    course_code = models.CharField(max_length=50, blank=True)
    teacher_name = models.CharField(max_length=255, blank=True)
    current_mark = models.CharField(max_length=20, blank=True)
    midterm_grade = models.PositiveSmallIntegerField(blank=True, null=True)
    final_grade = models.PositiveSmallIntegerField(blank=True, null=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["course_name"]

    def __str__(self):
        return self.course_name

    @property
    def credit_earned(self):
        return self.final_grade is not None and self.final_grade >= 50

    @property
    def mark_display(self):
        if self.final_grade is not None:
            return f"Final {self.final_grade}%"
        if self.midterm_grade is not None:
            return f"Midterm {self.midterm_grade}%"
        return self.current_mark or "-"


def request_attachment_upload_to(instance, filename):
    return f"request_attachments/{instance.request_id}/{filename}"


def request_response_upload_to(instance, filename):
    return f"request_responses/{instance.request_id}/{filename}"


def prepared_report_upload_to(instance, filename):
    return f"prepared_reports/{instance.student_id}/{filename}"


class StudentNote(TimeStampedModel):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    note = models.TextField()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Note for {self.student}"


class FollowUpTask(TimeStampedModel):
    STATUS_OPEN = "open"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_DONE = "done"
    STATUS_CANCELLED = "cancelled"

    PRIORITY_LOW = "low"
    PRIORITY_MEDIUM = "medium"
    PRIORITY_HIGH = "high"
    PRIORITY_URGENT = "urgent"

    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_IN_PROGRESS, "In Progress"),
        (STATUS_DONE, "Done"),
        (STATUS_CANCELLED, "Cancelled"),
    ]
    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "Low"),
        (PRIORITY_MEDIUM, "Medium"),
        (PRIORITY_HIGH, "High"),
        (PRIORITY_URGENT, "Urgent"),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="tasks")
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_tasks"
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM)
    completed_at = models.DateTimeField(blank=True, null=True)
    is_closed = models.BooleanField(default=False)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="closed_follow_up_tasks",
    )
    closed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["due_date", "-created_at"]

    def __str__(self):
        return self.title


class DocumentRequirement(TimeStampedModel):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="documents")
    document_name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Student.DOCUMENT_STATUS_CHOICES, default="pending")
    due_date = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["document_name"]

    def __str__(self):
        return f"{self.document_name} - {self.student}"


class CommunicationLog(TimeStampedModel):
    CATEGORY_GENERAL = "general"
    CATEGORY_REQUEST = "request"
    CATEGORY_REPORT = "report"
    CATEGORY_SESSION = "session"
    STATUS_LOGGED = "logged"
    STATUS_QUEUED = "queued"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    AUDIENCE_STUDENT = "student"
    AUDIENCE_PARENT = "parent"
    AUDIENCE_AGENT = "agent"
    AUDIENCE_STAFF = "staff"
    AUDIENCE_OTHER = "other"
    DIRECTION_CHOICES = [("outbound", "Outbound"), ("inbound", "Inbound")]
    METHOD_CHOICES = [
        ("email", "Email"),
        ("phone", "Phone"),
        ("meeting", "Meeting"),
        ("wechat", "WeChat"),
        ("whatsapp", "WhatsApp"),
        ("other", "Other"),
    ]
    CATEGORY_CHOICES = [
        (CATEGORY_GENERAL, "General"),
        (CATEGORY_REQUEST, "Request Response"),
        (CATEGORY_REPORT, "Report Delivery"),
        (CATEGORY_SESSION, "Session Communication"),
    ]
    STATUS_CHOICES = [
        (STATUS_LOGGED, "Logged"),
        (STATUS_QUEUED, "Queued"),
        (STATUS_SENT, "Sent"),
        (STATUS_FAILED, "Failed"),
    ]
    AUDIENCE_CHOICES = [
        (AUDIENCE_STUDENT, "Student"),
        (AUDIENCE_PARENT, "Parent/Guardian"),
        (AUDIENCE_AGENT, "Agent"),
        (AUDIENCE_STAFF, "Staff"),
        (AUDIENCE_OTHER, "Other"),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="communications")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    direction = models.CharField(max_length=20, choices=DIRECTION_CHOICES, default="outbound")
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default="email")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default=CATEGORY_GENERAL)
    audience = models.CharField(max_length=20, choices=AUDIENCE_CHOICES, default=AUDIENCE_OTHER)
    contact_person = models.CharField(max_length=255)
    recipient_email = models.EmailField(blank=True)
    subject = models.CharField(max_length=255, blank=True)
    communicated_at = models.DateTimeField()
    summary = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_LOGGED)
    send_error = models.TextField(blank=True)
    related_request_response = models.ForeignKey(
        "StudentRequestResponse",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="communication_logs",
    )
    related_report = models.ForeignKey(
        "PreparedReport",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="communication_logs",
    )
    template = models.ForeignKey(
        "CommunicationTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="communication_logs",
    )

    class Meta:
        ordering = ["-communicated_at"]

    def __str__(self):
        return f"{self.get_method_display()} with {self.contact_person}"


class StudentRequest(TimeStampedModel):
    REQUEST_TRANSCRIPT = "transcript"
    REQUEST_COUNSELLING = "counselling"
    REQUEST_DOCUMENT = "document"
    REQUEST_OTHER = "other"

    STATUS_NEW = "new"
    STATUS_IN_REVIEW = "in_review"
    STATUS_APPROVED = "approved"
    STATUS_DECLINED = "declined"
    STATUS_SCHEDULED = "scheduled"
    STATUS_COMPLETED = "completed"
    STATUS_CLOSED = "closed"

    REQUEST_TYPE_CHOICES = [
        (REQUEST_TRANSCRIPT, "Transcript Request"),
        (REQUEST_COUNSELLING, "Counselling Session Request"),
        (REQUEST_DOCUMENT, "Document Support Request"),
        (REQUEST_OTHER, "Other Request"),
    ]
    STATUS_CHOICES = [
        (STATUS_NEW, "New"),
        (STATUS_IN_REVIEW, "In Review"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_DECLINED, "Declined"),
        (STATUS_SCHEDULED, "Scheduled"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CLOSED, "Closed"),
    ]

    student = models.ForeignKey(Student, on_delete=models.SET_NULL, null=True, blank=True, related_name="requests")
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_requests",
    )
    submitted_by_name = models.CharField(max_length=255)
    submitted_by_email = models.EmailField()
    student_identifier = models.CharField(max_length=50, blank=True)
    request_type = models.CharField(max_length=30, choices=REQUEST_TYPE_CHOICES)
    title = models.CharField(max_length=255)
    details = models.TextField()
    preferred_date = models.DateField(blank=True, null=True)
    preferred_time = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)
    status_before_close = models.CharField(max_length=20, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="closed_student_requests",
    )
    closed_at = models.DateTimeField(blank=True, null=True)
    internal_notes = models.TextField(blank=True)
    confirmation_sent_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["status", "-created_at"]

    def __str__(self):
        return f"{self.get_request_type_display()} - {self.submitted_by_name}"


class CounsellingSession(TimeStampedModel):
    TYPE_COUNSELLING = "counselling"
    TYPE_TRANSCRIPT = "transcript"
    TYPE_PARENT = "parent"
    TYPE_OTHER = "other"

    STATUS_SCHEDULED = "scheduled"
    STATUS_PENDING_APPROVAL = "pending_approval"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"
    STATUS_NO_SHOW = "no_show"

    SESSION_TYPE_CHOICES = [
        (TYPE_COUNSELLING, "Counselling Session"),
        (TYPE_TRANSCRIPT, "Transcript Meeting"),
        (TYPE_PARENT, "Parent Meeting"),
        (TYPE_OTHER, "Other"),
    ]
    STATUS_CHOICES = [
        (STATUS_PENDING_APPROVAL, "Pending Approval"),
        (STATUS_SCHEDULED, "Scheduled"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_NO_SHOW, "No Show"),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="sessions")
    linked_request = models.ForeignKey(
        StudentRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
    )
    counsellor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="counselling_sessions",
    )
    session_type = models.CharField(max_length=30, choices=SESSION_TYPE_CHOICES, default=TYPE_COUNSELLING)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    location = models.CharField(max_length=255, blank=True)
    meeting_link = models.URLField(blank=True)
    confirmation_email = models.EmailField(blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SCHEDULED)
    confirmation_sent_at = models.DateTimeField(blank=True, null=True)
    reminder_sent_at = models.DateTimeField(blank=True, null=True)
    reschedule_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    is_closed = models.BooleanField(default=False)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="closed_counselling_sessions",
    )
    closed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["start_at"]

    def __str__(self):
        return f"{self.student.full_name} - {self.start_at:%Y-%m-%d %H:%M}"

    def clean(self):
        if self.end_at and self.start_at and self.end_at <= self.start_at:
            raise ValidationError("Session end time must be after the start time.")


class SessionChangeRequest(TimeStampedModel):
    STATUS_NEW = "new"
    STATUS_REVIEWED = "reviewed"
    STATUS_SCHEDULED = "scheduled"

    STATUS_CHOICES = [
        (STATUS_NEW, "New"),
        (STATUS_REVIEWED, "Reviewed"),
        (STATUS_SCHEDULED, "Rescheduled"),
    ]

    session = models.ForeignKey(CounsellingSession, on_delete=models.CASCADE, related_name="change_requests")
    requester_name = models.CharField(max_length=255)
    requester_email = models.EmailField()
    requested_start = models.DateTimeField()
    requested_end = models.DateTimeField()
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Reschedule request for {self.session}"


class StudentRequestAttachment(TimeStampedModel):
    request = models.ForeignKey(StudentRequest, on_delete=models.CASCADE, related_name="attachments")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    original_name = models.CharField(max_length=255)
    file = models.FileField(upload_to=request_attachment_upload_to)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.original_name


class StudentRequestResponse(TimeStampedModel):
    request = models.ForeignKey(StudentRequest, on_delete=models.CASCADE, related_name="responses")
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    subject = models.CharField(max_length=255)
    message = models.TextField()
    recipient_email = models.EmailField()
    attachment = models.FileField(upload_to=request_response_upload_to, blank=True)
    mark_complete = models.BooleanField(default=True)
    send_requested_at = models.DateTimeField(blank=True, null=True)
    sent_at = models.DateTimeField(blank=True, null=True)
    send_error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Response to {self.request}"


class CommunicationTemplate(TimeStampedModel):
    TYPE_REQUEST = "request"
    TYPE_GENERAL = "general"

    TEMPLATE_TYPE_CHOICES = [
        (TYPE_REQUEST, "Request Response"),
        (TYPE_GENERAL, "General Update"),
    ]

    name = models.CharField(max_length=120, unique=True)
    template_type = models.CharField(max_length=20, choices=TEMPLATE_TYPE_CHOICES, default=TYPE_GENERAL)
    audience = models.CharField(
        max_length=20,
        choices=CommunicationLog.AUDIENCE_CHOICES,
        default=CommunicationLog.AUDIENCE_PARENT,
    )
    subject_template = models.CharField(max_length=255)
    body_template = models.TextField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["template_type", "name"]

    def __str__(self):
        return self.name


class PreparedReport(TimeStampedModel):
    AUDIENCE_PARENT = "parent"
    AUDIENCE_AGENT = "agent"
    AUDIENCE_CHOICES = [
        (AUDIENCE_PARENT, "Parent/Guardian"),
        (AUDIENCE_AGENT, "Agent/Agency"),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="prepared_reports")
    term = models.ForeignKey(AcademicTerm, on_delete=models.SET_NULL, null=True, blank=True, related_name="reports")
    prepared_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    audience = models.CharField(max_length=20, choices=AUDIENCE_CHOICES, default=AUDIENCE_PARENT)
    title = models.CharField(max_length=255)
    recipient_name = models.CharField(max_length=255, blank=True)
    recipient_email = models.EmailField(blank=True)
    summary = models.TextField(blank=True)
    academic_progress = models.TextField(blank=True)
    attendance_update = models.TextField(blank=True)
    counselling_update = models.TextField(blank=True)
    recommendations = models.TextField(blank=True)
    attachment = models.FileField(upload_to=prepared_report_upload_to, blank=True)
    send_requested_at = models.DateTimeField(blank=True, null=True)
    sent_at = models.DateTimeField(blank=True, null=True)
    send_error = models.TextField(blank=True)
    is_closed = models.BooleanField(default=False)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="closed_prepared_reports",
    )
    closed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class StudentPortalAccess(TimeStampedModel):
    student = models.OneToOneField(Student, on_delete=models.CASCADE, related_name="portal_access")
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="student_portal")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Student portal access"
        verbose_name_plural = "Student portal access"

    def __str__(self):
        return f"{self.student.full_name} portal access"


class ParentPortalAccess(TimeStampedModel):
    RELATIONSHIP_PARENT = "parent"
    RELATIONSHIP_GUARDIAN = "guardian"
    RELATIONSHIP_AGENT = "agent"
    RELATIONSHIP_OTHER = "other"
    RELATIONSHIP_CHOICES = [
        (RELATIONSHIP_PARENT, "Parent"),
        (RELATIONSHIP_GUARDIAN, "Guardian"),
        (RELATIONSHIP_AGENT, "Agent"),
        (RELATIONSHIP_OTHER, "Other"),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="parent_access_links")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="parent_portal_links")
    relationship_label = models.CharField(max_length=20, choices=RELATIONSHIP_CHOICES, default=RELATIONSHIP_PARENT)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["student__full_name", "user__username"]
        unique_together = ["student", "user"]
        verbose_name = "Parent portal access"
        verbose_name_plural = "Parent portal access"

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} -> {self.student.full_name}"


class CounsellorStudentAccess(TimeStampedModel):
    counsellor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="granted_student_access",
    )
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="extra_counsellor_access")
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_counsellor_student_access",
    )
    reason = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["student__full_name"]
        unique_together = ["counsellor", "student"]
        verbose_name = "Counsellor extra access"
        verbose_name_plural = "Counsellor extra access"

    def __str__(self):
        return f"{self.counsellor} -> {self.student}"


class CounsellorAccessRequest(TimeStampedModel):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_DECLINED = "declined"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_DECLINED, "Declined"),
    ]

    counsellor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="requested_student_access",
    )
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="access_requests")
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_counsellor_access_requests",
    )
    reviewed_at = models.DateTimeField(blank=True, null=True)
    review_note = models.TextField(blank=True)

    class Meta:
        ordering = ["status", "-created_at"]
        unique_together = ["counsellor", "student", "status"]
        verbose_name = "Counsellor access request"
        verbose_name_plural = "Counsellor access requests"

    def __str__(self):
        return f"{self.counsellor} requesting {self.student}"


class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=100)
    model_name = models.CharField(max_length=100)
    object_id = models.PositiveBigIntegerField(blank=True, null=True)
    object_repr = models.CharField(max_length=255)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} on {self.model_name}"
