from .models import CounsellingSession, PreparedReport, Student, StudentNote, StudentRequest, StudentRequestResponse, StudentTermRecord


AUDITED_FIELDS = {
    Student: ["attendance_concerns", "target_universities", "internal_summary"],
    StudentTermRecord: ["academic_summary", "attendance_summary", "counselling_summary", "agent_notes"],
    StudentNote: ["note"],
    StudentRequest: ["details", "internal_notes"],
    CounsellingSession: ["notes"],
    StudentRequestResponse: ["message"],
    PreparedReport: ["summary", "academic_progress", "attendance_update", "counselling_update", "recommendations"],
}
