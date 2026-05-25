# Generated manually for safe token backfill on existing session rows.

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def populate_reschedule_tokens(apps, schema_editor):
    CounsellingSession = apps.get_model("cases", "CounsellingSession")
    for session in CounsellingSession.objects.filter(reschedule_token__isnull=True):
        session.reschedule_token = uuid.uuid4()
        session.save(update_fields=["reschedule_token"])


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0002_studentrequest_counsellingsession"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="counsellingsession",
            name="reschedule_token",
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.CreateModel(
            name="SessionChangeRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("requester_name", models.CharField(max_length=255)),
                ("requester_email", models.EmailField(max_length=254)),
                ("requested_start", models.DateTimeField()),
                ("requested_end", models.DateTimeField()),
                ("reason", models.TextField()),
                ("status", models.CharField(choices=[("new", "New"), ("reviewed", "Reviewed"), ("scheduled", "Rescheduled")], default="new", max_length=20)),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="change_requests", to="cases.counsellingsession")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="StudentPortalAccess",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("student", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="portal_access", to="cases.student")),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="student_portal", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "Student portal access", "verbose_name_plural": "Student portal access"},
        ),
        migrations.RunPython(populate_reschedule_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="counsellingsession",
            name="reschedule_token",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
