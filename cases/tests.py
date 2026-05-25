from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from .models import Student
from .permissions import ROLE_ADMIN, ROLE_COUNSELLOR, ensure_roles


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
