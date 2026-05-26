from django.core.management.base import BaseCommand
from django.utils import timezone

from cases.models import StudentTermRecord
from cases.notifications import send_term_progress_reminder


class Command(BaseCommand):
    help = "Send counsellor reminders when term midterm or final grades should be entered."

    def handle(self, *args, **options):
        today = timezone.localdate()
        sent = 0
        term_records = StudentTermRecord.objects.select_related(
            "student",
            "student__assigned_counsellor",
            "term",
        ).prefetch_related("courses")

        for term_record in term_records:
            if term_record.term.midterm_checkpoint_date and today >= term_record.term.midterm_checkpoint_date:
                if term_record.needs_midterm_grades and term_record.midterm_reminder_sent_at is None:
                    if send_term_progress_reminder(term_record, "midterm"):
                        sent += 1
            if term_record.term.final_checkpoint_date and today >= term_record.term.final_checkpoint_date:
                if term_record.needs_final_grades and term_record.final_reminder_sent_at is None:
                    if send_term_progress_reminder(term_record, "final"):
                        sent += 1

        self.stdout.write(self.style.SUCCESS(f"Processed {sent} term progress reminder email(s)."))
