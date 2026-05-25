from django.core.management.base import BaseCommand

from cases.models import CounsellingSession
from cases.notifications import send_session_reminder, sessions_needing_reminders


class Command(BaseCommand):
    help = "Send reminder emails for sessions happening in the next 24 hours."

    def handle(self, *args, **options):
        sessions = sessions_needing_reminders(CounsellingSession.objects.select_related("student"))
        sent = 0
        for session in sessions:
            send_session_reminder(session)
            sent += 1
        self.stdout.write(self.style.SUCCESS(f"Processed {sent} reminder email(s)."))
