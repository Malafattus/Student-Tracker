from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.utils import timezone


class SessionIdleTimeoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        timeout_seconds = getattr(settings, "SESSION_IDLE_TIMEOUT_SECONDS", 0)
        exempt_paths = {
            getattr(settings, "LOGIN_URL", "/accounts/login/"),
            "/accounts/logout/",
        }
        if timeout_seconds and request.user.is_authenticated and request.path not in exempt_paths:
            now = timezone.now().timestamp()
            last_seen = request.session.get("last_activity_ts")
            if last_seen and now - last_seen > timeout_seconds:
                logout(request)
                if hasattr(request, "_messages"):
                    messages.info(request, "Your session expired after inactivity. Please sign in again.")
                return redirect(settings.LOGIN_URL)
            request.session["last_activity_ts"] = now
        return self.get_response(request)
