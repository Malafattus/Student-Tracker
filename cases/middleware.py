from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout
from django.contrib.auth.models import User
from django.shortcuts import redirect
from django.utils import timezone

from .audit import log_security_event


class TrustedIdentityHeaderMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            getattr(settings, "TRUSTED_IDENTITY_ENABLED", False)
            and not getattr(request.user, "is_authenticated", False)
        ):
            email_header = getattr(settings, "TRUSTED_IDENTITY_EMAIL_HEADER", "")
            identity_email = (request.META.get(email_header, "") or "").strip().lower()
            if identity_email:
                user = User.objects.filter(email__iexact=identity_email, is_active=True).first()
                if user:
                    auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
                    request.session["auth_completed_at"] = timezone.now().timestamp()
                    provider_name = getattr(settings, "TRUSTED_IDENTITY_PROVIDER_NAME", "School SSO")
                    log_security_event(
                        "trusted_identity_signin",
                        "Trusted identity sign-in",
                        {
                            "section": "trusted_identity",
                            "provider": provider_name,
                            "header": email_header,
                            "email": identity_email,
                        },
                        actor=user,
                    )
        return self.get_response(request)


class SessionIdleTimeoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        timeout_seconds = getattr(settings, "SESSION_IDLE_TIMEOUT_SECONDS", 0)
        exempt_paths = {
            getattr(settings, "LOGIN_URL", "/accounts/login/"),
            "/accounts/logout/",
            "/accounts/password-change-required/",
            "/accounts/mfa/setup/",
            "/accounts/mfa/challenge/",
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
        if request.user.is_authenticated and request.path not in exempt_paths:
            security_profile = getattr(request.user, "security_profile", None)
            auth_completed_at = request.session.get("auth_completed_at")
            if security_profile and security_profile.session_revoked_at:
                revoked_ts = security_profile.session_revoked_at.timestamp()
                if not auth_completed_at or auth_completed_at <= revoked_ts:
                    logout(request)
                    if hasattr(request, "_messages"):
                        messages.info(request, "Your access was ended by an administrator. Please sign in again.")
                    return redirect(settings.LOGIN_URL)
            if security_profile and security_profile.must_reset_password:
                return redirect("/accounts/password-change-required/")
            from .views import mfa_required_for_user

            if mfa_required_for_user(request.user) and (not security_profile or not security_profile.mfa_enabled):
                return redirect("/accounts/mfa/setup/")
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
        response["Content-Security-Policy"] = (
            f"default-src {' '.join(settings.CSP_DEFAULT_SRC)}; "
            f"img-src {' '.join(settings.CSP_IMG_SRC)}; "
            f"style-src {' '.join(settings.CSP_STYLE_SRC)}; "
            f"font-src {' '.join(settings.CSP_FONT_SRC)}; "
            f"script-src {' '.join(settings.CSP_SCRIPT_SRC)}; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        )
        response["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), interest-cohort=()"
        return response
