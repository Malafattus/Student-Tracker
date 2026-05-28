from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0020_usersecurityprofile_session_revoked_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="securitypolicy",
            name="approved_hosting_environment",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="securitypolicy",
            name="break_glass_usernames",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="securitypolicy",
            name="last_operations_review_at",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="securitypolicy",
            name="last_privacy_review_at",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="securitypolicy",
            name="last_security_test_at",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="securitypolicy",
            name="operations_owner_email",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name="securitypolicy",
            name="operations_owner_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="securitypolicy",
            name="privacy_owner_email",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name="securitypolicy",
            name="privacy_owner_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="securitypolicy",
            name="require_school_managed_auth_for_staff",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="securitypolicy",
            name="security_owner_email",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name="securitypolicy",
            name="security_owner_name",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
