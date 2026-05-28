from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def create_default_security_policy(apps, schema_editor):
    SecurityPolicy = apps.get_model("cases", "SecurityPolicy")
    if not SecurityPolicy.objects.exists():
        SecurityPolicy.objects.create()


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0015_backfill_default_school_year_terms"),
    ]

    operations = [
        migrations.CreateModel(
            name="SecurityPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("require_staff_domain_match", models.BooleanField(default=False)),
                ("allowed_staff_email_domains", models.TextField(blank=True)),
                ("require_password_reset_for_new_accounts", models.BooleanField(default=True)),
                ("minimum_password_length", models.PositiveSmallIntegerField(default=10)),
            ],
            options={
                "verbose_name": "Security policy",
                "verbose_name_plural": "Security policy",
            },
        ),
        migrations.CreateModel(
            name="UserSecurityProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("must_reset_password", models.BooleanField(default=False)),
                ("manually_locked", models.BooleanField(default=False)),
                ("password_changed_at", models.DateTimeField(blank=True, null=True)),
                ("security_note", models.TextField(blank=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="security_profile", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["user__username"],
            },
        ),
        migrations.RunPython(create_default_security_policy, migrations.RunPython.noop),
    ]
