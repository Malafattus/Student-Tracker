from getpass import getpass
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from cases.export_security import SecureExportError, decrypt_export_bytes


class Command(BaseCommand):
    help = "Decrypt an encrypted backup or export created by the app."

    def add_arguments(self, parser):
        parser.add_argument("encrypted_file", help="Path to the encrypted .enc file.")
        parser.add_argument("output_file", help="Path to write the decrypted file.")
        parser.add_argument("--passphrase", help="Export password. If omitted, you will be prompted.")

    def handle(self, *args, **options):
        encrypted_path = Path(options["encrypted_file"])
        output_path = Path(options["output_file"])
        if not encrypted_path.exists():
            raise CommandError("Encrypted file not found.")

        passphrase = options.get("passphrase") or getpass("Export password: ")
        if not passphrase:
            raise CommandError("A password is required to decrypt this file.")

        try:
            decrypted = decrypt_export_bytes(encrypted_path.read_bytes(), passphrase)
        except SecureExportError as exc:
            raise CommandError(str(exc)) from exc

        output_path.write_bytes(decrypted)
        self.stdout.write(self.style.SUCCESS(f"Decrypted export written to {output_path}"))
