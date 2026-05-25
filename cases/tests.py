from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from .models import CounsellingSession, SessionChangeRequest, Student, StudentPortalAccess, StudentRequest
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
