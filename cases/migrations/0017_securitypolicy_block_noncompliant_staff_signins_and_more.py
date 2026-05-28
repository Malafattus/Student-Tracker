from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0016_securitypolicy_usersecurityprofile"),
    ]

    operations = [
        migrations.AddField(
            model_name="securitypolicy",
            name="block_noncompliant_staff_signins",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="securitypolicy",
            name="password_rotation_days",
            field=models.PositiveSmallIntegerField(default=180),
        ),
    ]
