from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone


def build_absolute_url(path):
    base = getattr(settings, "SITE_URL", "").rstrip("/")
    if not base:
        return path
    return f"{base}{path}"


def send_notification_email(subject, template_prefix, recipients, context):
    recipients = [email for email in recipients if email]
    if not recipients:
        return False
    text_body = render_to_string(f"emails/{template_prefix}.txt", context)
    html_body = render_to_string(f"emails/{template_prefix}.html", context)
    email = EmailMultiAlternatives(
        subject,
        text_body,
        settings.DEFAULT_FROM_EMAIL,
        recipients,
    )
    email.attach_alternative(html_body, "text/html")
    email.send(fail_silently=True)
    return True


def send_request_confirmation(student_request):
    sent = send_notification_email(
        "We received your student support request",
        "request_confirmation",
        [student_request.submitted_by_email],
        {
            "student_request": student_request,
        },
    )
    if sent:
        student_request.confirmation_sent_at = timezone.now()
        student_request.save(update_fields=["confirmation_sent_at", "updated_at"])


def session_recipients(session):
    recipients = []
    if session.confirmation_email:
        recipients.append(session.confirmation_email)
    recipients.extend(session.student.contact_emails())
    return list(dict.fromkeys(recipients))


def send_session_confirmation(session):
    reschedule_url = build_absolute_url(f"/sessions/reschedule/{session.reschedule_token}/")
    sent = send_notification_email(
        "Counselling session confirmation",
        "session_confirmation",
        session_recipients(session),
        {
            "session": session,
            "reschedule_url": reschedule_url,
        },
    )
    if sent:
        session.confirmation_sent_at = timezone.now()
        session.save(update_fields=["confirmation_sent_at", "updated_at"])


def send_session_reminder(session):
    reschedule_url = build_absolute_url(f"/sessions/reschedule/{session.reschedule_token}/")
    sent = send_notification_email(
        "Upcoming counselling session reminder",
        "session_reminder",
        session_recipients(session),
        {
            "session": session,
            "reschedule_url": reschedule_url,
        },
    )
    if sent:
        session.reminder_sent_at = timezone.now()
        session.save(update_fields=["reminder_sent_at", "updated_at"])


def send_session_change_request_notice(change_request):
    session = change_request.session
    recipients = []
    if session.counsellor and session.counsellor.email:
        recipients.append(session.counsellor.email)
    sent = send_notification_email(
        "Student requested a session change",
        "session_change_request_notice",
        recipients,
        {
            "change_request": change_request,
            "session": session,
        },
    )
    return sent


def sessions_needing_reminders(queryset):
    now = timezone.now()
    horizon = now + timedelta(hours=24)
    return queryset.filter(
        status="scheduled",
        start_at__gte=now,
        start_at__lte=horizon,
        reminder_sent_at__isnull=True,
    )
