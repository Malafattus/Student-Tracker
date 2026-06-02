from django.core.management.base import BaseCommand
from django.db import connection

from cases.crypto import decrypt_text, encrypted_text_version
from cases.sensitive_fields import AUDITED_FIELDS


class Command(BaseCommand):
    help = "Report whether sensitive text fields are stored in encrypted form."

    def handle(self, *args, **options):
        total_plaintext = 0
        total_unreadable = 0
        with connection.cursor() as cursor:
            for model, field_names in AUDITED_FIELDS.items():
                table_name = model._meta.db_table
                for field_name in field_names:
                    field = model._meta.get_field(field_name)
                    cursor.execute(
                        f"""
                        SELECT {field.column}
                        FROM {table_name}
                        WHERE {field.column} IS NOT NULL
                          AND {field.column} != ''
                        """,
                    )
                    plaintext_count = 0
                    unreadable_count = 0
                    versions = {}
                    for (stored_value,) in cursor.fetchall():
                        version = encrypted_text_version(stored_value)
                        if version is None:
                            plaintext_count += 1
                        else:
                            try:
                                decrypt_text(stored_value)
                                versions[version] = versions.get(version, 0) + 1
                            except Exception:
                                unreadable_count += 1
                    total_plaintext += plaintext_count
                    total_unreadable += unreadable_count
                    if plaintext_count == 0 and unreadable_count == 0 and versions:
                        version_summary = ", ".join(f"{version}: {count}" for version, count in sorted(versions.items()))
                        state = f"encrypted ({version_summary})"
                    elif plaintext_count == 0 and unreadable_count == 0:
                        state = "encrypted"
                    elif unreadable_count:
                        state = f"{plaintext_count} plaintext value(s), {unreadable_count} unreadable encrypted value(s)"
                    else:
                        state = f"{plaintext_count} plaintext value(s)"
                    self.stdout.write(f"{model.__name__}.{field_name}: {state}")
        if total_plaintext:
            self.stderr.write(self.style.WARNING(f"Found {total_plaintext} plaintext sensitive value(s)."))
        if total_unreadable:
            self.stderr.write(self.style.WARNING(f"Found {total_unreadable} unreadable encrypted sensitive value(s)."))
        if not total_plaintext and not total_unreadable:
            self.stdout.write(self.style.SUCCESS("All audited sensitive fields are stored in encrypted form."))
