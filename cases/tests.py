from datetime import date, timedelta

from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    AcademicTerm,
    AuditLog,
    CommunicationLog,
    CommunicationTemplate,
    CounsellorAccessRequest,
    CounsellorProfile,
    CounsellorStudentAccess,
    CounsellingSession,
    FollowUpTask,
    ParentPortalAccess,
    PreparedReport,
    SecurityPolicy,
    SessionChangeRequest,
    Student,
    StudentPortalAccess,
    StudentRequest,
    StudentTermRecord,
    TermCourseEnrollment,
    UserSecurityProfile,
)
from .permissions import ROLE_ADMIN, ROLE_COUNSELLOR, ROLE_PARENT, ROLE_STUDENT, ensure_roles


class CaseTrackerSmokeTests(TestCase):
    def setUp(self):
        cache.clear()
        ensure_roles()
        self.admin_user = User.objects.create_user("admin", password="pass12345")
        self.admin_user.groups.add(Group.objects.get(name=ROLE_ADMIN))
        self.counsellor = User.objects.create_user("counsellor", email="counsellor@example.com", password="pass12345")
        self.counsellor.groups.add(Group.objects.get(name=ROLE_COUNSELLOR))
        CounsellorProfile.objects.create(user=self.counsellor, primary_team="Korean Team")
        self.student = Student.objects.create(
            full_name="Test Student",
            student_id="S9999",
            grade="12",
            nationality="Canada",
            support_team="Korean Team",
            assigned_counsellor=self.counsellor,
            case_stage=Student.STAGE_ACTIVE,
        )

    def test_admin_can_load_dashboard(self):
        client = Client()
        client.login(username="admin", password="pass12345")
        response = client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Academic watchlist")
        self.assertIn("no-store", response["Cache-Control"])

    def test_dashboard_shows_academic_watchlist_and_pending_access_request(self):
        self.student.required_credits = 30
        self.student.volunteer_hours_completed = 6
        self.student.osslt_status = Student.OSSLT_PENDING
        self.student.save()
        other_student = Student.objects.create(
            full_name="Other Team Student",
            student_id="S7777",
            grade="11",
            nationality="Japan",
            support_team="Japanese Team",
            case_stage=Student.STAGE_ACTIVE,
        )
        CounsellorAccessRequest.objects.create(
            counsellor=self.counsellor,
            student=other_student,
            reason="Need to help with transition planning.",
        )
        client = Client()
        client.login(username="counsellor", password="pass12345")
        response = client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Academic watchlist")
        self.assertContains(response, "Test Student")
        self.assertContains(response, "My team access requests")

    def test_counsellor_can_view_assigned_student(self):
        client = Client()
        client.login(username="counsellor", password="pass12345")
        response = client.get(reverse("student_detail", args=[self.student.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Case stage and next steps")
        self.assertTrue(
            AuditLog.objects.filter(action="viewed", model_name="Student", details__section="student_record").exists()
        )

    def test_student_detail_shows_checkpoint_tracker(self):
        term = AcademicTerm.objects.create(
            school_year="2026-2027",
            name="Term 1",
            display_order=1,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 11, 17),
            is_active=True,
        )
        record = StudentTermRecord.objects.create(student=self.student, term=term, planned_course_count=3)
        TermCourseEnrollment.objects.create(term_record=record, course_name="ENG4U", midterm_grade=74)
        client = Client()
        client.login(username="counsellor", password="pass12345")
        response = client.get(reverse("student_detail", args=[self.student.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Checkpoint tracker")
        self.assertContains(response, "Midterms recorded: 1 / 1")

    def test_counsellor_can_open_communication_center(self):
        client = Client()
        client.login(username="counsellor", password="pass12345")
        response = client.get(reverse("communication_center"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Communication Center")

    def test_counsellor_can_open_academic_progress_workspace(self):
        term = AcademicTerm.objects.create(
            school_year="2026-2027",
            name="Term 1",
            display_order=1,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 11, 17),
            is_active=True,
        )
        StudentTermRecord.objects.create(student=self.student, term=term, planned_course_count=3)
        client = Client()
        client.login(username="counsellor", password="pass12345")
        response = client.get(reverse("academic_progress"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Track grades, credits, and graduation progress.")
        self.assertContains(response, "Test Student")

    def test_academic_progress_workspace_filters_by_team(self):
        Student.objects.create(
            full_name="Other Team Student",
            student_id="S7171",
            grade="11",
            nationality="Japan",
            support_team="Japanese Team",
            case_stage=Student.STAGE_ACTIVE,
            credits_remaining_manual=6,
        )
        client = Client()
        client.login(username="admin", password="pass12345")
        response = client.get(reverse("academic_progress"), {"team": "Japanese Team"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Other Team Student")
        self.assertNotContains(response, "Test Student")

    def test_student_list_can_filter_by_case_stage(self):
        Student.objects.create(
            full_name="Waiting Student",
            student_id="S8888",
            grade="11",
            nationality="Canada",
            support_team="Korean Team",
            assigned_counsellor=self.counsellor,
            case_stage=Student.STAGE_WAITING_STUDENT,
        )
        client = Client()
        client.login(username="counsellor", password="pass12345")
        response = client.get(reverse("student_list"), {"case_stage": Student.STAGE_WAITING_STUDENT})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Waiting Student")
        self.assertNotContains(response, "Test Student")

    def test_counsellor_only_sees_own_team_students_by_default(self):
        Student.objects.create(
            full_name="Other Team Student",
            student_id="S7777",
            grade="11",
            nationality="Japan",
            support_team="Japanese Team",
            case_stage=Student.STAGE_ACTIVE,
        )
        client = Client()
        client.login(username="counsellor", password="pass12345")
        response = client.get(reverse("student_list"))
        self.assertContains(response, "Test Student")
        self.assertNotContains(response, "Other Team Student")

    def test_granted_cross_team_access_makes_student_visible_to_counsellor(self):
        other_student = Student.objects.create(
            full_name="Cross Team Student",
            student_id="S6666",
            grade="10",
            nationality="Japan",
            support_team="Japanese Team",
            case_stage=Student.STAGE_ACTIVE,
        )
        CounsellorStudentAccess.objects.create(
            counsellor=self.counsellor,
            student=other_student,
            granted_by=self.admin_user,
            is_active=True,
        )
        client = Client()
        client.login(username="counsellor", password="pass12345")
        response = client.get(reverse("student_detail", args=[other_student.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cross Team Student")

    def test_public_student_request_creates_record(self):
        response = self.client.post(
            reverse("student_request_public"),
            {
                "submitted_by_name": "Jamie Student",
                "submitted_by_email": "jamie@example.com",
                "student_identifier": "S9999",
                "request_type": StudentRequest.REQUEST_TRANSCRIPT,
                "title": "Need official transcript",
                "details": "Please prepare a transcript for university application.",
                "preferred_time": "After school",
            },
        )
        self.assertRedirects(response, reverse("student_request_success"))
        self.assertEqual(StudentRequest.objects.count(), 1)
        request_item = StudentRequest.objects.get()
        self.assertEqual(request_item.student, self.student)
        self.assertEqual(request_item.assigned_to, self.counsellor)

    def test_public_request_form_throttles_repeated_submissions(self):
        payload = {
            "submitted_by_name": "Jamie Student",
            "submitted_by_email": "jamie@example.com",
            "student_identifier": "S9999",
            "request_type": StudentRequest.REQUEST_TRANSCRIPT,
            "title": "Need official transcript",
            "details": "Please prepare a transcript for university application.",
            "preferred_time": "After school",
        }
        for _ in range(5):
            response = self.client.post(reverse("student_request_public"), payload)
            self.assertEqual(response.status_code, 302)
        blocked_response = self.client.post(reverse("student_request_public"), payload)
        self.assertEqual(blocked_response.status_code, 200)
        self.assertContains(blocked_response, "Too many requests were submitted in a short period")
        self.assertTrue(
            AuditLog.objects.filter(model_name="SecurityEvent", action="throttled").exists()
        )

    def test_counsellor_can_see_public_student_requests_in_queue(self):
        StudentRequest.objects.create(
            student=self.student,
            assigned_to=self.counsellor,
            submitted_by_name="Jamie Student",
            submitted_by_email="jamie@example.com",
            student_identifier=self.student.student_id,
            request_type=StudentRequest.REQUEST_TRANSCRIPT,
            title="Need transcript",
            details="Please help with an official transcript.",
        )
        client = Client()
        client.login(username="counsellor", password="pass12345")
        response = client.get(reverse("request_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Need transcript")

    def test_counsellor_can_quick_approve_request_from_queue(self):
        request_item = StudentRequest.objects.create(
            student=self.student,
            assigned_to=self.counsellor,
            submitted_by_name="Jamie Student",
            submitted_by_email="jamie@example.com",
            student_identifier=self.student.student_id,
            request_type=StudentRequest.REQUEST_COUNSELLING,
            title="Need counselling",
            details="Please book a support session.",
        )
        client = Client()
        client.login(username="counsellor", password="pass12345")
        response = client.post(reverse("request_list"), {"request_id": request_item.pk, "action": "approve"})
        self.assertRedirects(response, reverse("request_list"))
        request_item.refresh_from_db()
        self.assertEqual(request_item.status, StudentRequest.STATUS_APPROVED)

    def test_counsellor_can_close_and_reopen_request(self):
        request_item = StudentRequest.objects.create(
            student=self.student,
            assigned_to=self.counsellor,
            submitted_by_name="Jamie Student",
            submitted_by_email="jamie@example.com",
            student_identifier=self.student.student_id,
            request_type=StudentRequest.REQUEST_TRANSCRIPT,
            title="Archive this request",
            details="This should move into history.",
            status=StudentRequest.STATUS_COMPLETED,
        )
        client = Client()
        client.login(username="counsellor", password="pass12345")
        close_response = client.post(reverse("request_list"), {"request_id": request_item.pk, "action": "close"})
        self.assertRedirects(close_response, reverse("request_list"))
        request_item.refresh_from_db()
        self.assertEqual(request_item.status, StudentRequest.STATUS_CLOSED)
        self.assertIsNotNone(request_item.closed_at)

        reopen_response = client.post(reverse("request_list"), {"request_id": request_item.pk, "action": "reopen"})
        self.assertRedirects(reopen_response, reverse("request_list"))
        request_item.refresh_from_db()
        self.assertEqual(request_item.status, StudentRequest.STATUS_COMPLETED)
        self.assertIsNone(request_item.closed_at)

    def test_queueing_request_response_creates_communication_log(self):
        request_item = StudentRequest.objects.create(
            student=self.student,
            assigned_to=self.counsellor,
            submitted_by_name="Jamie Student",
            submitted_by_email="jamie@example.com",
            student_identifier=self.student.student_id,
            request_type=StudentRequest.REQUEST_TRANSCRIPT,
            title="Need transcript update",
            details="Please send an update.",
        )
        template = CommunicationTemplate.objects.create(
            name="Transcript update",
            template_type=CommunicationTemplate.TYPE_REQUEST,
            audience=CommunicationLog.AUDIENCE_STUDENT,
            subject_template="Transcript update",
            body_template="Your transcript request is being reviewed.",
        )
        client = Client()
        client.login(username="counsellor", password="pass12345")
        response = client.post(
            reverse("request_update", args=[request_item.pk]),
            {
                "send_response": "1",
                "template": template.pk,
                "subject": "",
                "recipient_email": "jamie@example.com",
                "message": "",
                "mark_complete": "on",
            },
        )
        self.assertRedirects(response, reverse("request_update", args=[request_item.pk]))
        communication = CommunicationLog.objects.get(related_request_response__isnull=False)
        self.assertEqual(communication.status, CommunicationLog.STATUS_QUEUED)
        self.assertEqual(communication.template, template)
        self.assertEqual(communication.subject, "Transcript update")

    def test_login_with_email_identifier(self):
        self.admin_user.email = "admin@example.com"
        self.admin_user.save()
        response = self.client.post(reverse("login"), {"username": "admin@example.com", "password": "pass12345"})
        self.assertEqual(response.status_code, 302)

    def test_manually_locked_user_cannot_sign_in(self):
        locked_user = User.objects.create_user("locked-user", email="locked@example.com", password="pass12345")
        locked_user.groups.add(Group.objects.get(name=ROLE_COUNSELLOR))
        UserSecurityProfile.objects.create(user=locked_user, manually_locked=True)
        response = self.client.post(reverse("login"), {"username": "locked-user", "password": "pass12345"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This account has been locked")
        self.assertTrue(
            AuditLog.objects.filter(model_name="SecurityEvent", action="login_blocked").exists()
        )

    @override_settings(LOGIN_FAILURE_LIMIT=3, LOGIN_LOCKOUT_SECONDS=900)
    def test_login_lockout_after_repeated_failures(self):
        for _ in range(3):
            response = self.client.post(reverse("login"), {"username": "admin", "password": "wrong-pass"})
            self.assertEqual(response.status_code, 200)
        blocked_response = self.client.post(reverse("login"), {"username": "admin", "password": "pass12345"})
        self.assertEqual(blocked_response.status_code, 200)
        self.assertContains(blocked_response, "Too many sign-in attempts were made")
        self.assertTrue(
            AuditLog.objects.filter(model_name="SecurityEvent", action="login_locked").exists()
        )

    @override_settings(LOGIN_FAILURE_LIMIT=3, LOGIN_LOCKOUT_SECONDS=900)
    def test_successful_login_clears_failure_counter(self):
        response = self.client.post(reverse("login"), {"username": "admin", "password": "wrong-pass"})
        self.assertEqual(response.status_code, 200)
        success_response = self.client.post(reverse("login"), {"username": "admin", "password": "pass12345"})
        self.assertEqual(success_response.status_code, 302)
        response_after_success = self.client.post(reverse("login"), {"username": "admin", "password": "wrong-pass"})
        self.assertEqual(response_after_success.status_code, 200)

    def test_forced_password_reset_redirects_until_completed(self):
        UserSecurityProfile.objects.create(user=self.counsellor, must_reset_password=True)
        client = Client()
        response = client.post(reverse("login"), {"username": "counsellor", "password": "pass12345"})
        self.assertRedirects(response, reverse("password_change_required"))
        dashboard_response = client.get(reverse("dashboard"))
        self.assertRedirects(dashboard_response, reverse("password_change_required"))
        update_response = client.post(
            reverse("password_change_required"),
            {"new_password1": "freshpass123", "new_password2": "freshpass123"},
        )
        self.assertRedirects(update_response, reverse("dashboard"))
        self.counsellor.refresh_from_db()
        self.assertFalse(self.counsellor.security_profile.must_reset_password)
        self.assertTrue(self.counsellor.check_password("freshpass123"))

    def test_security_center_is_available_to_admin(self):
        client = Client()
        client.login(username="admin", password="pass12345")
        response = client.get(reverse("security_center"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Security Center")

    def test_security_policy_can_restrict_staff_domains(self):
        policy = SecurityPolicy.get_solo()
        policy.require_staff_domain_match = True
        policy.allowed_staff_email_domains = "uis.edu"
        policy.save()
        client = Client()
        client.login(username="admin", password="pass12345")
        response = client.post(
            reverse("user_management"),
            {
                "first_name": "New",
                "last_name": "Counsellor",
                "username": "newcounsellor",
                "email": "newcounsellor@gmail.com",
                "is_active": "on",
                "role": ROLE_COUNSELLOR,
                "primary_team": "Korean Team",
                "password": "securepass123",
                "must_reset_password": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This email domain is not allowed for staff accounts.")

    def test_student_portal_redirect_and_dashboard(self):
        portal_user = User.objects.create_user("student1", email="student1@example.com", password="pass12345")
        portal_user.groups.add(Group.objects.get(name=ROLE_STUDENT))
        StudentPortalAccess.objects.create(student=self.student, user=portal_user)
        response = self.client.post(reverse("login"), {"username": "student1", "password": "pass12345"})
        self.assertRedirects(response, reverse("portal_dashboard"))
        portal_response = self.client.get(reverse("portal_dashboard"))
        self.assertEqual(portal_response.status_code, 200)
        self.assertContains(portal_response, "Welcome back, Test Student.")
        self.assertNotContains(portal_response, "Recent audit activity")

    def test_student_dashboard_route_redirects_into_portal(self):
        portal_user = User.objects.create_user("student2", email="student2@example.com", password="pass12345")
        portal_user.groups.add(Group.objects.get(name=ROLE_STUDENT))
        StudentPortalAccess.objects.create(student=self.student, user=portal_user)
        client = Client()
        client.login(username="student2", password="pass12345")
        response = client.get(reverse("dashboard"))
        self.assertRedirects(response, reverse("portal_dashboard"))

    def test_student_group_without_portal_access_sees_setup_page(self):
        student_user = User.objects.create_user("student4", email="student4@example.com", password="pass12345")
        student_user.groups.add(Group.objects.get(name=ROLE_STUDENT))
        client = Client()
        client.login(username="student4", password="pass12345")
        response = client.get(reverse("dashboard"))
        self.assertRedirects(response, reverse("portal_unavailable"))
        unavailable_response = client.get(reverse("portal_unavailable"))
        self.assertContains(unavailable_response, "Student Portal Setup Needed")

    def test_student_can_submit_portal_request(self):
        portal_user = User.objects.create_user("student3", email="student3@example.com", password="pass12345")
        portal_user.groups.add(Group.objects.get(name=ROLE_STUDENT))
        StudentPortalAccess.objects.create(student=self.student, user=portal_user)
        client = Client()
        client.login(username="student3", password="pass12345")
        response = client.post(
            reverse("portal_request_create"),
            {
                "request_type": StudentRequest.REQUEST_TRANSCRIPT,
                "title": "Need a transcript for university",
                "details": "Please prepare it for my application.",
                "preferred_time": "After school",
            },
        )
        self.assertRedirects(response, reverse("portal_dashboard"))
        request_item = StudentRequest.objects.get(title="Need a transcript for university")
        self.assertEqual(request_item.student, self.student)
        self.assertEqual(request_item.submitted_by_name, self.student.full_name)
        self.assertEqual(request_item.student_identifier, self.student.student_id)

    def test_parent_portal_only_shows_linked_children(self):
        term = AcademicTerm.objects.create(school_year="2026-2027", name="Term 1", display_order=1, is_active=True)
        record = StudentTermRecord.objects.create(student=self.student, term=term, planned_course_count=3, is_completed=True)
        TermCourseEnrollment.objects.create(term_record=record, course_name="ENG4U", final_grade=78)
        TermCourseEnrollment.objects.create(term_record=record, course_name="MHF4U", final_grade=72)
        self.student.credits_remaining_manual = 28
        self.student.save(update_fields=["credits_remaining_manual", "updated_at"])
        sibling = Student.objects.create(
            full_name="Sibling Student",
            student_id="S5555",
            grade="9",
            nationality="Canada",
            support_team="Korean Team",
            assigned_counsellor=self.counsellor,
            case_stage=Student.STAGE_ACTIVE,
        )
        other_student = Student.objects.create(
            full_name="Unlinked Student",
            student_id="S4444",
            grade="8",
            nationality="Canada",
            support_team="Global Team",
            case_stage=Student.STAGE_ACTIVE,
        )
        parent_user = User.objects.create_user("parent1", email="parent1@example.com", password="pass12345")
        parent_user.groups.add(Group.objects.get(name=ROLE_PARENT))
        ParentPortalAccess.objects.create(student=self.student, user=parent_user)
        ParentPortalAccess.objects.create(student=sibling, user=parent_user)
        client = Client()
        client.login(username="parent1", password="pass12345")
        response = client.get(reverse("parent_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Student")
        self.assertContains(response, "Sibling Student")
        self.assertNotContains(response, "Unlinked Student")
        self.assertContains(response, "2 / 30")
        self.assertContains(response, "28")

    def test_student_credit_and_volunteer_progress_properties(self):
        self.student.required_credits = 30
        self.student.credits_remaining_manual = 28
        self.student.volunteer_hours_required = 40
        self.student.volunteer_hours_remaining_manual = 28
        self.student.save()
        term = AcademicTerm.objects.create(school_year="2026-2027", name="Term 1", display_order=1, is_active=True)
        record = StudentTermRecord.objects.create(student=self.student, term=term, planned_course_count=3, is_completed=True)
        TermCourseEnrollment.objects.create(term_record=record, course_name="ENG4U", final_grade=78)
        TermCourseEnrollment.objects.create(term_record=record, course_name="MHF4U", final_grade=42)
        TermCourseEnrollment.objects.create(term_record=record, course_name="SBI4U", final_grade=65)
        self.assertEqual(self.student.earned_credits, 2)
        self.assertEqual(self.student.credits_remaining, 28)
        self.assertEqual(self.student.volunteer_hours_remaining, 28)
        self.assertEqual(self.student.volunteer_hours_completed_total, 12)

    def test_term_progress_reminder_command_marks_midterm_and_final(self):
        today = timezone.localdate()
        term = AcademicTerm.objects.create(
            school_year="2026-2027",
            name="Term 1",
            display_order=1,
            start_date=today - timedelta(days=40),
            end_date=today + timedelta(days=20),
            is_active=True,
        )
        record = StudentTermRecord.objects.create(student=self.student, term=term, planned_course_count=2)
        TermCourseEnrollment.objects.create(term_record=record, course_name="ENG4U")
        call_command("send_term_progress_reminders")
        record.refresh_from_db()
        self.assertIsNotNone(record.midterm_reminder_sent_at)

        course = record.courses.first()
        course.midterm_grade = 72
        course.save(update_fields=["midterm_grade", "updated_at"])
        record.midterm_reminder_sent_at = None
        record.final_reminder_sent_at = None
        record.save(update_fields=["midterm_reminder_sent_at", "final_reminder_sent_at", "updated_at"])
        term.start_date = today - timedelta(days=80)
        term.end_date = today - timedelta(days=1)
        term.save(update_fields=["start_date", "end_date", "updated_at"])
        call_command("send_term_progress_reminders")
        record.refresh_from_db()
        self.assertIsNotNone(record.final_reminder_sent_at)

    def test_academic_term_uses_week_milestones_for_standard_terms(self):
        term = AcademicTerm.objects.create(
            school_year="2026-2027",
            name="Term 2",
            display_order=2,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 11, 17),
            is_active=True,
        )
        self.assertEqual(term.midterm_checkpoint_date, date(2026, 10, 6))
        self.assertEqual(term.final_checkpoint_date, date(2026, 11, 10))

    def test_parent_role_without_links_sees_setup_page(self):
        parent_user = User.objects.create_user("parent2", email="parent2@example.com", password="pass12345")
        parent_user.groups.add(Group.objects.get(name=ROLE_PARENT))
        client = Client()
        client.login(username="parent2", password="pass12345")
        response = client.get(reverse("dashboard"))
        self.assertRedirects(response, reverse("parent_unavailable"))

    def test_session_reschedule_request_form_creates_change_request(self):
        session = CounsellingSession.objects.create(
            student=self.student,
            counsellor=self.counsellor,
            start_at="2026-06-01T14:00:00Z",
            end_at="2026-06-01T14:30:00Z",
        )
        response = self.client.post(
            reverse("session_reschedule", args=[session.reschedule_token]),
            {
                "requester_name": "Test Student",
                "requester_email": "student@example.com",
                "requested_start": "2026-06-02T14:00",
                "requested_end": "2026-06-02T14:30",
                "reason": "Conflict with class.",
            },
        )
        self.assertRedirects(response, reverse("session_reschedule_success"))
        self.assertEqual(SessionChangeRequest.objects.count(), 1)

    def test_session_create_page_loads_from_student_link(self):
        client = Client()
        client.login(username="counsellor", password="pass12345")
        response = client.get(reverse("session_create"), {"student": self.student.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Book a Session")

    def test_session_create_page_loads_from_request_link(self):
        request_item = StudentRequest.objects.create(
            student=self.student,
            assigned_to=self.counsellor,
            submitted_by_name="Jamie Student",
            submitted_by_email="jamie@example.com",
            student_identifier=self.student.student_id,
            request_type=StudentRequest.REQUEST_COUNSELLING,
            title="Need counselling",
            details="Please book a support session.",
        )
        client = Client()
        client.login(username="counsellor", password="pass12345")
        response = client.get(reverse("session_create"), {"request": request_item.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Book a Session")

    def test_counsellor_can_accept_session_request_from_session_workspace(self):
        request_item = StudentRequest.objects.create(
            student=self.student,
            assigned_to=self.counsellor,
            submitted_by_name="Jamie Student",
            submitted_by_email="jamie@example.com",
            student_identifier=self.student.student_id,
            request_type=StudentRequest.REQUEST_COUNSELLING,
            title="Please book counselling",
            details="I need to meet this week.",
            status=StudentRequest.STATUS_IN_REVIEW,
        )
        client = Client()
        client.login(username="counsellor", password="pass12345")
        response = client.post(reverse("session_list"), {"request_id": request_item.pk, "request_action": "approve"})
        self.assertRedirects(response, reverse("session_list"))
        request_item.refresh_from_db()
        self.assertEqual(request_item.status, StudentRequest.STATUS_APPROVED)

    def test_counsellor_can_decline_session_request_from_session_workspace(self):
        request_item = StudentRequest.objects.create(
            student=self.student,
            assigned_to=self.counsellor,
            submitted_by_name="Jamie Student",
            submitted_by_email="jamie@example.com",
            student_identifier=self.student.student_id,
            request_type=StudentRequest.REQUEST_COUNSELLING,
            title="Please book counselling",
            details="I need to meet this week.",
            status=StudentRequest.STATUS_NEW,
        )
        client = Client()
        client.login(username="counsellor", password="pass12345")
        response = client.post(reverse("session_list"), {"request_id": request_item.pk, "request_action": "decline"})
        self.assertRedirects(response, reverse("session_list"))
        request_item.refresh_from_db()
        self.assertEqual(request_item.status, StudentRequest.STATUS_DECLINED)

    def test_prepared_report_save_redirects_to_saved_report_page(self):
        client = Client()
        client.login(username="counsellor", password="pass12345")
        response = client.post(
            reverse("student_report_add", args=[self.student.pk]),
            {
                "student": self.student.pk,
                "audience": PreparedReport.AUDIENCE_PARENT,
                "title": "May family update",
                "recipient_name": "Parent Contact",
                "recipient_email": "parent@example.com",
                "summary": "Summary text.",
                "academic_progress": "Academic update.",
                "attendance_update": "Attendance update.",
                "counselling_update": "Counselling update.",
                "recommendations": "Recommendations.",
            },
        )
        report = PreparedReport.objects.get()
        self.assertRedirects(response, reverse("prepared_report_update", args=[report.pk]))
        detail_response = client.get(reverse("prepared_report_update", args=[report.pk]))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "May family update")

    def test_counsellor_can_close_and_reopen_report(self):
        report = PreparedReport.objects.create(
            student=self.student,
            prepared_by=self.counsellor,
            audience=PreparedReport.AUDIENCE_PARENT,
            title="Close me",
            recipient_email="parent@example.com",
        )
        client = Client()
        client.login(username="counsellor", password="pass12345")
        close_response = client.post(reverse("prepared_report_update", args=[report.pk]), {"close_report": "1"})
        self.assertRedirects(close_response, reverse("prepared_report_update", args=[report.pk]))
        report.refresh_from_db()
        self.assertTrue(report.is_closed)
        self.assertIsNotNone(report.closed_at)

        reopen_response = client.post(reverse("prepared_report_update", args=[report.pk]), {"reopen_report": "1"})
        self.assertRedirects(reopen_response, reverse("prepared_report_update", args=[report.pk]))
        report.refresh_from_db()
        self.assertFalse(report.is_closed)
        self.assertIsNone(report.closed_at)

    def test_counsellor_can_close_and_reopen_task(self):
        task = FollowUpTask.objects.create(
            student=self.student,
            assigned_to=self.counsellor,
            created_by=self.counsellor,
            title="Follow up with family",
            due_date="2026-06-10",
        )
        client = Client()
        client.login(username="counsellor", password="pass12345")
        close_response = client.post(reverse("task_list"), {"task_id": task.pk, "action": "close"})
        self.assertRedirects(close_response, reverse("task_list"))
        task.refresh_from_db()
        self.assertTrue(task.is_closed)
        self.assertIsNotNone(task.closed_at)

        reopen_response = client.post(reverse("task_list"), {"task_id": task.pk, "action": "reopen"})
        self.assertRedirects(reopen_response, reverse("task_list"))
        task.refresh_from_db()
        self.assertFalse(task.is_closed)
        self.assertIsNone(task.closed_at)

    def test_counsellor_can_close_and_reopen_session(self):
        session = CounsellingSession.objects.create(
            student=self.student,
            counsellor=self.counsellor,
            start_at="2026-06-01T14:00:00Z",
            end_at="2026-06-01T14:30:00Z",
        )
        client = Client()
        client.login(username="counsellor", password="pass12345")
        close_response = client.post(reverse("session_list"), {"session_id": session.pk, "action": "close"})
        self.assertRedirects(close_response, reverse("session_list"))
        session.refresh_from_db()
        self.assertTrue(session.is_closed)
        self.assertIsNotNone(session.closed_at)

        reopen_response = client.post(reverse("session_list"), {"session_id": session.pk, "action": "reopen"})
        self.assertRedirects(reopen_response, reverse("session_list"))
        session.refresh_from_db()
        self.assertFalse(session.is_closed)
        self.assertIsNone(session.closed_at)

    def test_request_attachment_download_requires_access(self):
        request_item = StudentRequest.objects.create(
            student=self.student,
            assigned_to=self.counsellor,
            submitted_by_name="Jamie Student",
            submitted_by_email="jamie@example.com",
            student_identifier=self.student.student_id,
            request_type=StudentRequest.REQUEST_DOCUMENT,
            title="Need supporting file",
            details="Please review this upload.",
        )
        attachment = request_item.attachments.create(
            original_name="proof.pdf",
            file=SimpleUploadedFile("proof.pdf", b"test-file", content_type="application/pdf"),
        )
        client = Client()
        client.login(username="counsellor", password="pass12345")
        response = client.get(reverse("request_attachment_download", args=[attachment.pk]))
        self.assertEqual(response.status_code, 200)

        blocked_user = User.objects.create_user("outsider", password="pass12345")
        blocked_user.groups.add(Group.objects.get(name=ROLE_PARENT))
        blocked_client = Client()
        blocked_client.login(username="outsider", password="pass12345")
        blocked_response = blocked_client.get(reverse("request_attachment_download", args=[attachment.pk]))
        self.assertEqual(blocked_response.status_code, 302)

    def test_prepared_report_attachment_download_requires_access(self):
        report = PreparedReport.objects.create(
            student=self.student,
            prepared_by=self.counsellor,
            audience=PreparedReport.AUDIENCE_PARENT,
            title="Secure report",
            recipient_email="parent@example.com",
            attachment=SimpleUploadedFile("report.pdf", b"report-file", content_type="application/pdf"),
        )
        parent_user = User.objects.create_user("parent-secure", email="parent-secure@example.com", password="pass12345")
        parent_user.groups.add(Group.objects.get(name=ROLE_PARENT))
        ParentPortalAccess.objects.create(student=self.student, user=parent_user)
        client = Client()
        client.login(username="parent-secure", password="pass12345")
        response = client.get(reverse("prepared_report_attachment", args=[report.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            AuditLog.objects.filter(action="downloaded", details__section="prepared_report_attachment").exists()
        )

    @override_settings(SESSION_IDLE_TIMEOUT_SECONDS=1)
    def test_idle_session_timeout_logs_user_out(self):
        client = Client()
        client.login(username="counsellor", password="pass12345")
        session = client.session
        session["last_activity_ts"] = timezone.now().timestamp() - 120
        session.save()
        response = client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_admin_tools_shows_security_activity(self):
        client = Client()
        client.login(username="admin", password="pass12345")
        response = client.get(reverse("admin_tools"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Recent security activity")
