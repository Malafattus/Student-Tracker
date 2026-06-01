from django.core.management.base import BaseCommand

from cases.crypto import active_field_key_id, encrypt_text, needs_reencryption
from cases.sensitive_fields import AUDITED_FIELDS


class Command(BaseCommand):
    help = "Re-encrypt sensitive text fields with the currently active field encryption key."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show what would be rotated without saving changes.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        rotated_values = 0
        rotated_records = 0
        active_key = active_field_key_id()
        for model, field_names in AUDITED_FIELDS.items():
            for obj in model.objects.all().iterator():
                changed_fields = []
                for field_name in field_names:
                    value = getattr(obj, field_name)
                    if needs_reencryption(value):
                        setattr(obj, field_name, encrypt_text(value, force_reencrypt=True))
                        changed_fields.append(field_name)
                if changed_fields:
                    rotated_records += 1
                    rotated_values += len(changed_fields)
                    if not dry_run:
                        obj.save(update_fields=changed_fields)
        action = "Would rotate" if dry_run else "Rotated"
        self.stdout.write(f"{action} {rotated_values} sensitive value(s) across {rotated_records} record(s) to key '{active_key}'.")
