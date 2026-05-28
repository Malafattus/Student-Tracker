from django.contrib import admin

from .models import (
    AcademicTerm,
    AuditLog,
    CommunicationLog,
    CommunicationTemplate,
    CounsellorAccessRequest,
    CounsellorProfile,
    CounsellorStudentAccess,
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
    StudentRequestAttachment,
    StudentRequestResponse,
    StudentTermRecord,
    TermCourseEnrollment,
    UserSecurityProfile,
)


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("full_name", "student_id", "grade", "support_team", "assigned_counsellor", "overall_risk_level", "payment_status")
    list_filter = ("grade", "support_team", "overall_risk_level", "payment_status", "homestay_status")
    search_fields = ("full_name", "student_id", "parent_guardian_email")


admin.site.register(StudentNote)
admin.site.register(FollowUpTask)
admin.site.register(DocumentRequirement)
admin.site.register(CommunicationLog)
admin.site.register(CommunicationTemplate)
admin.site.register(AuditLog)
admin.site.register(AcademicTerm)
admin.site.register(StudentRequest)
admin.site.register(StudentRequestAttachment)
admin.site.register(StudentRequestResponse)
admin.site.register(CounsellingSession)
admin.site.register(SessionChangeRequest)
admin.site.register(StudentPortalAccess)
admin.site.register(StudentTermRecord)
admin.site.register(TermCourseEnrollment)
admin.site.register(PreparedReport)
admin.site.register(SecurityPolicy)
admin.site.register(CounsellorProfile)
admin.site.register(ParentPortalAccess)
admin.site.register(CounsellorStudentAccess)
admin.site.register(CounsellorAccessRequest)
admin.site.register(UserSecurityProfile)
