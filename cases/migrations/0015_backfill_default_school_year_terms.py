import datetime

from django.db import migrations


DEFAULT_TERMS = [
    ("2025-2026", "Semester 1", 1, datetime.date(2025, 9, 2), datetime.date(2025, 11, 7)),
    ("2025-2026", "Semester 2", 2, datetime.date(2025, 11, 11), datetime.date(2026, 1, 29)),
    ("2025-2026", "Semester 3", 3, datetime.date(2026, 2, 2), datetime.date(2026, 4, 20)),
    ("2025-2026", "Semester 4", 4, datetime.date(2026, 4, 21), datetime.date(2026, 6, 26)),
    ("2025-2026", "Summer Semester 1", 5, datetime.date(2026, 7, 2), datetime.date(2026, 7, 28)),
    ("2025-2026", "Summer Semester 2", 6, datetime.date(2026, 7, 29), datetime.date(2026, 8, 25)),
    ("2026-2027", "Semester 1", 1, datetime.date(2026, 9, 1), datetime.date(2026, 11, 6)),
    ("2026-2027", "Semester 2", 2, datetime.date(2026, 11, 10), datetime.date(2027, 1, 28)),
    ("2026-2027", "Semester 3", 3, datetime.date(2027, 2, 2), datetime.date(2027, 4, 19)),
    ("2026-2027", "Semester 4", 4, datetime.date(2027, 4, 21), datetime.date(2027, 6, 28)),
    ("2026-2027", "Summer Semester 1", 5, datetime.date(2027, 7, 5), datetime.date(2027, 7, 29)),
    ("2026-2027", "Summer Semester 2", 6, datetime.date(2027, 8, 3), datetime.date(2027, 8, 27)),
]


def backfill_default_terms(apps, schema_editor):
    AcademicTerm = apps.get_model("cases", "AcademicTerm")
    for school_year, name, display_order, start_date, end_date in DEFAULT_TERMS:
        AcademicTerm.objects.update_or_create(
            school_year=school_year,
            name=name,
            defaults={
                "display_order": display_order,
                "start_date": start_date,
                "end_date": end_date,
                "is_active": True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0014_seed_2025_2026_terms"),
    ]

    operations = [
        migrations.RunPython(backfill_default_terms, migrations.RunPython.noop),
    ]
