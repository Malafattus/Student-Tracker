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
        response = self.get_response(request)
        sensitive_prefixes = (
            "/students/",
            "/requests/",
            "/sessions/",
            "/tasks/",
            "/reports/",
            "/prepared-reports/",
            "/communications/",
            "/team-access/",
            "/admin-tools/",
            "/academics/",
            "/portal/",
            "/family/",
            "/users/",
        )
        if request.user.is_authenticated or request.path.startswith("/request-support/") or request.path in exempt_paths:
            response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0, private"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"
            response["X-Robots-Tag"] = "noindex, nofollow"
        elif request.path.startswith(sensitive_prefixes):
            response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0, private"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"
            response["X-Robots-Tag"] = "noindex, nofollow"
        return response
