from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0021_securitypolicy_institutional_readiness_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="securitypolicy",
            name="allowed_staff_ip_ranges",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="securitypolicy",
            name="restrict_staff_to_allowed_ip_ranges",
            field=models.BooleanField(default=False),
        ),
    ]
