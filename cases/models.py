from django.conf import settings
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

    full_name = models.CharField(max_length=255)
    student_id = models.CharField(max_length=50, unique=True)
    grade = models.CharField(max_length=20)
    nationality = models.CharField(max_length=100)
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
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return f"{self.full_name} ({self.student_id})"

    def get_absolute_url(self):
        return reverse("student_detail", args=[self.pk])


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
    DIRECTION_CHOICES = [("outbound", "Outbound"), ("inbound", "Inbound")]
    METHOD_CHOICES = [
        ("email", "Email"),
        ("phone", "Phone"),
        ("meeting", "Meeting"),
        ("wechat", "WeChat"),
        ("whatsapp", "WhatsApp"),
        ("other", "Other"),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="communications")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    direction = models.CharField(max_length=20, choices=DIRECTION_CHOICES, default="outbound")
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default="email")
    contact_person = models.CharField(max_length=255)
    communicated_at = models.DateTimeField()
    summary = models.TextField()

    class Meta:
        ordering = ["-communicated_at"]

    def __str__(self):
        return f"{self.get_method_display()} with {self.contact_person}"


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
