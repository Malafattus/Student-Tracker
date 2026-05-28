from django.db import migrations, models


def _fingerprint_field(file_field):
    import hashlib

    if not file_field:
        return "", 0
    digest = hashlib.sha256()
    size = 0
    file_field.open("rb")
    for chunk in file_field.chunks():
        digest.update(chunk)
        size += len(chunk)
    file_field.close()
    return digest.hexdigest(), size


def populate_existing_file_fingerprints(apps, schema_editor):
    StudentRequestAttachment = apps.get_model("cases", "StudentRequestAttachment")
    StudentRequestResponse = apps.get_model("cases", "StudentRequestResponse")
    PreparedReport = apps.get_model("cases", "PreparedReport")

    for attachment in StudentRequestAttachment.objects.all():
        sha256, size = _fingerprint_field(attachment.file)
        attachment.file_sha256 = sha256
        attachment.file_size = size
        attachment.save(update_fields=["file_sha256", "file_size"])

    for response in StudentRequestResponse.objects.all():
        sha256, size = _fingerprint_field(response.attachment)
        response.attachment_sha256 = sha256
        response.attachment_size = size
        response.save(update_fields=["attachment_sha256", "attachment_size"])

    for report in PreparedReport.objects.all():
        sha256, size = _fingerprint_field(report.attachment)
        report.attachment_sha256 = sha256
        report.attachment_size = size
        report.save(update_fields=["attachment_sha256", "attachment_size"])


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0022_securitypolicy_staff_ip_controls"),
    ]

    operations = [
        migrations.AddField(
            model_name="preparedreport",
            name="attachment_sha256",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="preparedreport",
            name="attachment_size",
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="studentrequestattachment",
            name="file_sha256",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="studentrequestattachment",
            name="file_size",
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="studentrequestresponse",
            name="attachment_sha256",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="studentrequestresponse",
            name="attachment_size",
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.RunPython(populate_existing_file_fingerprints, migrations.RunPython.noop),
    ]
