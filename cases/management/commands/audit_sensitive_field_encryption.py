from django.core.management.base import BaseCommand
from django.db import connection

from cases.crypto import encrypted_text_version
from cases.sensitive_fields import AUDITED_FIELDS


class Command(BaseCommand):
    help = "Report whether sensitive text fields are stored in encrypted form."

    def handle(self, *args, **options):
        total_plaintext = 0
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
                    versions = {}
                    for (stored_value,) in cursor.fetchall():
                        version = encrypted_text_version(stored_value)
                        if version is None:
                            plaintext_count += 1
                        else:
                            versions[version] = versions.get(version, 0) + 1
                    total_plaintext += plaintext_count
                    if plaintext_count == 0 and versions:
                        version_summary = ", ".join(f"{version}: {count}" for version, count in sorted(versions.items()))
                        state = f"encrypted ({version_summary})"
                    elif plaintext_count == 0:
                        state = "encrypted"
                    else:
                        state = f"{plaintext_count} plaintext value(s)"
                    self.stdout.write(f"{model.__name__}.{field_name}: {state}")
        if total_plaintext:
            self.stderr.write(self.style.WARNING(f"Found {total_plaintext} plaintext sensitive value(s)."))
        else:
            self.stdout.write(self.style.SUCCESS("All audited sensitive fields are stored in encrypted form."))
