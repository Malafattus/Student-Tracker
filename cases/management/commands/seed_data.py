import random
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from cases.models import CommunicationLog, DocumentRequirement, FollowUpTask, Student, StudentNote
from cases.permissions import ROLE_ADMIN, ROLE_COUNSELLOR, ROLE_VIEWER, ensure_roles


FIRST_NAMES = ["Ava", "Leo", "Mina", "Noah", "Sofia", "Daniel", "Yuna", "Ethan", "Grace", "Kai"]
LAST_NAMES = ["Chen", "Patel", "Wang", "Kim", "Singh", "Garcia", "Zhang", "Ali", "Nguyen", "Lopez"]
COUNTRIES = ["Canada", "China", "India", "Vietnam", "South Korea", "Brazil", "Nigeria", "Mexico"]
PROGRAMS = ["Business", "Engineering", "Computer Science", "Health Sciences", "Media Studies"]
UNIVERSITIES = ["University of Toronto", "UBC", "McMaster", "Waterloo", "York University"]


class Command(BaseCommand):
    help = "Creates role groups, sample users, and fake student case data."

    def handle(self, *args, **options):
        ensure_roles()
        self._make_user("admin", ROLE_ADMIN, "admin123!", "System", "Admin")
        counsellors = [
            self._make_user("counsellor1", ROLE_COUNSELLOR, "counsellor123!", "Maya", "Lin"),
            self._make_user("counsellor2", ROLE_COUNSELLOR, "counsellor123!", "Owen", "Park"),
        ]
        self._make_user("viewer1", ROLE_VIEWER, "viewer123!", "Chris", "Viewer")

        if Student.objects.exists():
            self.stdout.write(self.style.WARNING("Students already exist. Seed users/roles ensured only."))
            return

        for index in range(18):
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            student = Student.objects.create(
                full_name=f"{first} {last}",
                student_id=f"S{1000 + index}",
                grade=random.choice(["9", "10", "11", "12"]),
                nationality=random.choice(COUNTRIES),
                preferred_language=random.choice(["English", "Mandarin", "Korean", "Hindi"]),
                assigned_counsellor=random.choice(counsellors),
                agency=random.choice(["NorthBridge", "Global Pathways", "Maple Access", ""]),
                parent_guardian_name=f"{last} Family",
                parent_guardian_email=f"family{index}@example.com",
                parent_guardian_phone=f"+1-416-555-01{index:02d}",
                academic_status=random.choice([choice[0] for choice in Student.ACADEMIC_STATUS_CHOICES]),
                attendance_concerns=random.choice(["", "Occasional lateness", "Monitoring attendance closely"]),
                ossd_credit_progress=random.choice([choice[0] for choice in Student.PROGRESS_CHOICES]),
                graduation_status=random.choice([choice[0] for choice in Student.GRADUATION_STATUS_CHOICES]),
                counselling_status=random.choice([choice[0] for choice in Student.COUNSELLING_STATUS_CHOICES]),
                homestay_status=random.choice([choice[0] for choice in Student.HOMESTAY_STATUS_CHOICES]),
                payment_status=random.choice([choice[0] for choice in Student.PAYMENT_STATUS_CHOICES]),
                insurance_status=random.choice([choice[0] for choice in Student.DOCUMENT_STATUS_CHOICES]),
                target_country=random.choice(["Canada", "UK", "USA", "Australia"]),
                target_program=random.choice(PROGRAMS),
                target_universities=", ".join(random.sample(UNIVERSITIES, 3)),
                ielts_english_status=random.choice(["Completed", "Scheduled", "Not required"]),
                university_application_status=random.choice([choice[0] for choice in Student.APPLICATION_STATUS_CHOICES]),
                overall_risk_level=random.choice([choice[0] for choice in Student.RISK_LEVEL_CHOICES]),
                internal_summary="Sample summary for testing dashboard and reports.",
            )
            StudentNote.objects.create(student=student, author=student.assigned_counsellor, note="Initial case review completed.")
            FollowUpTask.objects.create(
                student=student,
                assigned_to=student.assigned_counsellor,
                created_by=student.assigned_counsellor,
                title="Follow up with family",
                description="Confirm target university shortlist and missing paperwork.",
                due_date=timezone.localdate() + timedelta(days=random.randint(-5, 10)),
                status=random.choice([choice[0] for choice in FollowUpTask.STATUS_CHOICES]),
                priority=random.choice([choice[0] for choice in FollowUpTask.PRIORITY_CHOICES]),
            )
            DocumentRequirement.objects.create(
                student=student,
                document_name=random.choice(["Passport Copy", "Transcript", "Custodianship Form", "Insurance Proof"]),
                status=random.choice([choice[0] for choice in Student.DOCUMENT_STATUS_CHOICES]),
                due_date=timezone.localdate() + timedelta(days=random.randint(2, 20)),
                notes="Auto-generated demo document status.",
            )
            CommunicationLog.objects.create(
                student=student,
                created_by=student.assigned_counsellor,
                direction="outbound",
                method=random.choice(["email", "phone", "meeting"]),
                contact_person=student.parent_guardian_name,
                communicated_at=timezone.now() - timedelta(days=random.randint(0, 7)),
                summary="Checked in with the family regarding application timeline and next steps.",
            )

        self.stdout.write(self.style.SUCCESS("Seed data created."))

    def _make_user(self, username, role, password, first_name, last_name):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"first_name": first_name, "last_name": last_name, "email": f"{username}@example.com"},
        )
        if created:
            user.set_password(password)
            user.save()
        user.groups.clear()
        user.groups.add(user.groups.model.objects.get(name=role))
        return user
