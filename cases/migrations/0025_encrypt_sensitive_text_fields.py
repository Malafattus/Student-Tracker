import cases.fields
from django.db import migrations


def encrypt_existing_sensitive_text(apps, schema_editor):
    sensitive_fields = {
        "Student": ["attendance_concerns", "target_universities", "internal_summary"],
        "StudentTermRecord": ["academic_summary", "attendance_summary", "counselling_summary", "agent_notes"],
        "StudentNote": ["note"],
        "StudentRequest": ["details", "internal_notes"],
        "CounsellingSession": ["notes"],
        "StudentRequestResponse": ["message"],
        "PreparedReport": ["summary", "academic_progress", "attendance_update", "counselling_update", "recommendations"],
    }
    for model_name, field_names in sensitive_fields.items():
        model = apps.get_model("cases", model_name)
        for obj in model.objects.all().iterator():
            changed_fields = []
            for field_name in field_names:
                value = getattr(obj, field_name)
                if value:
                    setattr(obj, field_name, value)
                    changed_fields.append(field_name)
            if changed_fields:
                obj.save(update_fields=changed_fields)


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0024_securitypolicy_emergency_lockdown"),
    ]

    operations = [
        migrations.AlterField(
            model_name="student",
            name="attendance_concerns",
            field=cases.fields.EncryptedTextField(blank=True),
        ),
        migrations.AlterField(
            model_name="student",
            name="target_universities",
            field=cases.fields.EncryptedTextField(blank=True),
        ),
        migrations.AlterField(
            model_name="student",
            name="internal_summary",
            field=cases.fields.EncryptedTextField(blank=True),
        ),
        migrations.AlterField(
            model_name="studenttermrecord",
            name="academic_summary",
            field=cases.fields.EncryptedTextField(blank=True),
        ),
        migrations.AlterField(
            model_name="studenttermrecord",
            name="attendance_summary",
            field=cases.fields.EncryptedTextField(blank=True),
        ),
        migrations.AlterField(
            model_name="studenttermrecord",
            name="counselling_summary",
            field=cases.fields.EncryptedTextField(blank=True),
        ),
        migrations.AlterField(
            model_name="studenttermrecord",
            name="agent_notes",
            field=cases.fields.EncryptedTextField(blank=True),
        ),
        migrations.AlterField(
            model_name="studentnote",
            name="note",
            field=cases.fields.EncryptedTextField(),
        ),
        migrations.AlterField(
            model_name="studentrequest",
            name="details",
            field=cases.fields.EncryptedTextField(),
        ),
        migrations.AlterField(
            model_name="studentrequest",
            name="internal_notes",
            field=cases.fields.EncryptedTextField(blank=True),
        ),
        migrations.AlterField(
            model_name="counsellingsession",
            name="notes",
            field=cases.fields.EncryptedTextField(blank=True),
        ),
        migrations.AlterField(
            model_name="studentrequestresponse",
            name="message",
            field=cases.fields.EncryptedTextField(),
        ),
        migrations.AlterField(
            model_name="preparedreport",
            name="summary",
            field=cases.fields.EncryptedTextField(blank=True),
        ),
        migrations.AlterField(
            model_name="preparedreport",
            name="academic_progress",
            field=cases.fields.EncryptedTextField(blank=True),
        ),
        migrations.AlterField(
            model_name="preparedreport",
            name="attendance_update",
            field=cases.fields.EncryptedTextField(blank=True),
        ),
        migrations.AlterField(
            model_name="preparedreport",
            name="counselling_update",
            field=cases.fields.EncryptedTextField(blank=True),
        ),
        migrations.AlterField(
            model_name="preparedreport",
            name="recommendations",
            field=cases.fields.EncryptedTextField(blank=True),
        ),
        migrations.RunPython(encrypt_existing_sensitive_text, migrations.RunPython.noop),
    ]
