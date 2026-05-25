from django.apps import AppConfig


class CasesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'cases'

    def ready(self):
        # Import signal registrations when Django boots the app registry.
        from . import signals  # noqa: F401
