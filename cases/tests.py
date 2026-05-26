from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from .models import CommunicationLog, CommunicationTemplate, CounsellingSession, FollowUpTask, PreparedReport, SessionChangeRequest, Student, StudentPortalAccess, StudentRequest
from .permissions import ROLE_ADMIN, ROLE_COUNSELLOR, ROLE_STUDENT, ensure_roles


class CaseTrackerSmokeTests(TestCase):
    def setUp(self):
        ensure_roles()
        self.admin_user = User.objects.create_user("admin", password="pass12345")
        self.admin_user.groups.add(Group.objects.get(name=ROLE_ADMIN))
        self.counsellor = User.objects.create_user("counsellor", password="pass12345")
        self.counsellor.groups.add(Group.objects.get(name=ROLE_COUNSELLOR))
        self.student = Student.objects.create(
            full_name="Test Student",
            student_id="S9999",
            grade="12",
            nationality="Canada",
            assigned_counsellor=self.counsellor,
            case_stage=Student.STAGE_ACTIVE,
        )

    def test_admin_can_load_dashboard(self):
        client = Client()
        client.login(username="admin", password="pass12345")
        response = client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_counsellor_can_view_assigned_student(self):
        client = Client()
        client.login(username="counsellor", password="pass12345")
        response = client.get(reverse("student_detail", args=[self.student.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Case stage and next steps")

    def test_counsellor_can_open_communication_center(self):
        client = Client()
        client.login(username="counsellor", password="pass12345")
        response = client.get(reverse("communication_center"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Communication Center")

    def test_student_list_can_filter_by_case_stage(self):
        Student.objects.create(
            full_name="Waiting Student",
            student_id="S8888",
            grade="11",
            nationality="Canada",
            assigned_counsellor=self.counsellor,
            case_stage=Student.STAGE_WAITING_STUDENT,
        )
        client = Client()
        client.login(username="counsellor", password="pass12345")
        response = client.get(reverse("student_list"), {"case_stage": Student.STAGE_WAITING_STUDENT})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Waiting Student")
        self.assertNotContains(response, "Test Student")

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
