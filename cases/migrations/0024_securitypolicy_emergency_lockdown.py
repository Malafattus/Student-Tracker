from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0023_file_integrity_fingerprints"),
    ]

    operations = [
        migrations.AddField(
            model_name="securitypolicy",
            name="emergency_lockdown_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="securitypolicy",
            name="emergency_lockdown_message",
            field=models.TextField(blank=True),
        ),
    ]
