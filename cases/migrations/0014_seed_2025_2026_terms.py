import datetime

from django.db import migrations


def seed_2025_2026_terms(apps, schema_editor):
    AcademicTerm = apps.get_model("cases", "AcademicTerm")
    terms = [
        ("2025-2026", "Semester 1", 1, datetime.date(2025, 9, 2), datetime.date(2025, 11, 7)),
        ("2025-2026", "Semester 2", 2, datetime.date(2025, 11, 11), datetime.date(2026, 1, 29)),
        ("2025-2026", "Semester 3", 3, datetime.date(2026, 2, 2), datetime.date(2026, 4, 20)),
        ("2025-2026", "Semester 4", 4, datetime.date(2026, 4, 21), datetime.date(2026, 6, 26)),
        ("2025-2026", "Summer Semester 1", 5, datetime.date(2026, 7, 2), datetime.date(2026, 7, 28)),
        ("2025-2026", "Summer Semester 2", 6, datetime.date(2026, 7, 29), datetime.date(2026, 8, 25)),
    ]
    for school_year, name, display_order, start_date, end_date in terms:
        AcademicTerm.objects.get_or_create(
            school_year=school_year,
            name=name,
            defaults={
                "display_order": display_order,
                "start_date": start_date,
                "end_date": end_date,
                "is_active": True,
            },
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0013_student_credits_remaining_manual_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_2025_2026_terms, noop_reverse),
    ]
