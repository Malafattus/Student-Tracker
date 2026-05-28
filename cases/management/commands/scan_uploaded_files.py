from pathlib import Path

from django.conf import settings
from django.core.files.base import File
from django.core.management.base import BaseCommand, CommandError

from cases.file_security import suspicious_upload_reasons


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
        for path in media_root.rglob("*"):
            if not path.is_file():
                continue
            with path.open("rb") as handle:
                wrapped = File(handle, name=path.name)
                reasons = suspicious_upload_reasons(wrapped)
            if reasons:
                suspicious.append((path, reasons))

        if not suspicious:
            self.stdout.write(self.style.SUCCESS("No suspicious uploaded files were found."))
            return

        for path, reasons in suspicious:
            self.stdout.write(f"SUSPICIOUS {path}: {' '.join(reasons)}")

        if options["strict"]:
            raise CommandError(f"Found {len(suspicious)} suspicious uploaded file(s).")
