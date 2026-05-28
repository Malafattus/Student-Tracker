from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0019_securitypolicy_require_mfa_for_all_accounts_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="usersecurityprofile",
            name="session_revoked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
