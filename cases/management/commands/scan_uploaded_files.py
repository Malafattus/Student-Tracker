from pathlib import Path

from django.conf import settings
from django.core.files.base import File
from django.core.management.base import BaseCommand, CommandError

from cases.file_security import file_integrity_matches, suspicious_upload_reasons
from cases.models import PreparedReport, StudentRequestAttachment, StudentRequestResponse


class Command(BaseCommand):
    help = "Scan existing uploaded files for blocked types, malware test signatures, or suspicious content."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit with a failure code if any suspicious files are found.",
        )

    def handle(self, *args, **options):
        media_root = Path(settings.MEDIA_ROOT)
        if not media_root.exists():
            self.stdout.write("No media directory found.")
            return

        suspicious = []
        integrity_failures = []
        for path in media_root.rglob("*"):
            if not path.is_file():
                continue
            with path.open("rb") as handle:
                wrapped = File(handle, name=path.name)
                reasons = suspicious_upload_reasons(wrapped)
            if reasons:
                suspicious.append((path, reasons))

        tracked_files = []
        tracked_files.extend(
            ("request attachment", item.file, item.file_sha256, item.file_size)
            for item in StudentRequestAttachment.objects.exclude(file="")
        )
        tracked_files.extend(
            ("request response attachment", item.attachment, item.attachment_sha256, item.attachment_size)
            for item in StudentRequestResponse.objects.exclude(attachment="")
        )
        tracked_files.extend(
            ("prepared report attachment", item.attachment, item.attachment_sha256, item.attachment_size)
            for item in PreparedReport.objects.exclude(attachment="")
        )
        for label, file_field, expected_sha256, expected_size in tracked_files:
            if not file_field:
                continue
            file_field.open("rb")
            matches = file_integrity_matches(file_field, expected_sha256, expected_size)
            file_field.close()
            if not matches:
                integrity_failures.append((label, file_field.name))

        if not suspicious and not integrity_failures:
            self.stdout.write(self.style.SUCCESS("No suspicious uploaded files were found."))
            return

        for path, reasons in suspicious:
            self.stdout.write(f"SUSPICIOUS {path}: {' '.join(reasons)}")
        for label, name in integrity_failures:
            self.stdout.write(f"TAMPERED {label}: {name} no longer matches its recorded fingerprint.")

        if options["strict"]:
            raise CommandError(
                f"Found {len(suspicious)} suspicious uploaded file(s) and {len(integrity_failures)} integrity failure(s)."
            )
