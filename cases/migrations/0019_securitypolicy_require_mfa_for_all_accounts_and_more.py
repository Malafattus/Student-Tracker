from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0018_usersecurityprofile_mfa_fields_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="securitypolicy",
            name="dormant_account_review_days",
            field=models.PositiveSmallIntegerField(default=90),
        ),
        migrations.AddField(
            model_name="securitypolicy",
            name="require_mfa_for_all_accounts",
            field=models.BooleanField(default=False),
        ),
    ]
