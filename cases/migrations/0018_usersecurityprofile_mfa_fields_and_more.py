from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0017_securitypolicy_block_noncompliant_staff_signins_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="securitypolicy",
            name="require_mfa_for_staff",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="usersecurityprofile",
            name="last_mfa_verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="usersecurityprofile",
            name="mfa_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="usersecurityprofile",
            name="mfa_secret",
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
