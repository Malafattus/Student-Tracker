from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils import timezone

from cases.models import SecurityPolicy
from cases.notifications import send_notification_email
from cases.security import build_security_review_rows, security_review_recipients


class Command(BaseCommand):
    help = "Send a security access-review digest to admin users."

    def handle(self, *args, **options):
        recipients = security_review_recipients()
        if not recipients:
            self.stdout.write("No admin recipients configured.")
            return

        policy = SecurityPolicy.get_solo()
        rows = build_security_review_rows(policy=policy)
        flagged_rows = [
            row
            for row in rows
            if (not row["is_compliant"]) or row["dormant_for_review"] or (row["mfa_required"] and not row["profile"].mfa_enabled)
        ][:20]
        summary = {
            "noncompliant": sum(1 for row in rows if not row["is_compliant"]),
            "locked": sum(1 for row in rows if row["profile"].manually_locked),
            "reset_required": sum(1 for row in rows if row["profile"].must_reset_password),
            "stale_passwords": sum(1 for row in rows if "password_rotation" in row["issues"]),
            "mfa_enabled": sum(1 for row in rows if row["profile"].mfa_enabled),
            "dormant_accounts": sum(1 for row in rows if row["dormant_for_review"]),
        }
        subject = f"UIS security review digest - {timezone.localdate():%Y-%m-%d}"
        send_notification_email(
            subject,
            "security_review_digest",
            recipients,
            {
                "summary": summary,
                "rows": flagged_rows,
            },
        )
        self.stdout.write(f"Sent security review digest to {len(recipients)} admin recipient(s).")
