from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from cases.models import SecurityPolicy
from cases.security import governance_readiness, school_managed_auth_ready


class Command(BaseCommand):
    help = "Summarize whether the app is configured for institutional deployment readiness."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit with a failure code if readiness checks are incomplete.",
        )

    def handle(self, *args, **options):
        policy = SecurityPolicy.get_solo()
        governance = governance_readiness(policy=policy)
        checks = {
            "debug_off": not settings.DEBUG,
            "secret_key_configured": settings.SECRET_KEY != "django-insecure-local-dev-key-change-me",
            "allowed_hosts_configured": bool(settings.ALLOWED_HOSTS and settings.ALLOWED_HOSTS != ["127.0.0.1", "localhost", "testserver"]),
            "school_managed_auth_ready": school_managed_auth_ready(policy=policy),
            "governance_ready": governance["is_ready"],
        }
        for label, passed in checks.items():
            status = "PASS" if passed else "FAIL"
            self.stdout.write(f"{status} {label}")
        if options["strict"] and not all(checks.values()):
            raise CommandError("Institutional readiness checks are incomplete.")
