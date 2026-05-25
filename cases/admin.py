from django.contrib import admin

from .models import AuditLog, CommunicationLog, DocumentRequirement, FollowUpTask, Student, StudentNote


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("full_name", "student_id", "grade", "assigned_counsellor", "overall_risk_level", "payment_status")
    list_filter = ("grade", "overall_risk_level", "payment_status", "homestay_status")
    search_fields = ("full_name", "student_id", "parent_guardian_email")


admin.site.register(StudentNote)
admin.site.register(FollowUpTask)
admin.site.register(DocumentRequirement)
admin.site.register(CommunicationLog)
admin.site.register(AuditLog)
