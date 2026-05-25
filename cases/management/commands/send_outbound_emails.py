from django.core.management.base import BaseCommand

from cases.models import PreparedReport, StudentRequestResponse
from cases.notifications import send_prepared_report, send_request_response


class Command(BaseCommand):
    help = "Send queued outbound emails for request responses and prepared reports."

    def handle(self, *args, **options):
        queued_responses = StudentRequestResponse.objects.filter(send_requested_at__isnull=False, sent_at__isnull=True)
        queued_reports = PreparedReport.objects.filter(send_requested_at__isnull=False, sent_at__isnull=True)

        sent_count = 0
        failed_count = 0

        for response_item in queued_responses:
            if send_request_response(response_item):
                sent_count += 1
            else:
                failed_count += 1

        for report in queued_reports:
            if send_prepared_report(report):
                sent_count += 1
            else:
                failed_count += 1

        self.stdout.write(self.style.SUCCESS(f"Queued emails sent: {sent_count}"))
        if failed_count:
            self.stdout.write(self.style.WARNING(f"Queued emails still pending/failed: {failed_count}"))
