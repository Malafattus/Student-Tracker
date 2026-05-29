from datetime import timedelta
import ipaddress

from django.conf import settings

from django.contrib.auth.models import User
from django.utils import timezone

from .export_security import secure_export_ready
from .models import SecurityPolicy, UserSecurityProfile
from .permissions import is_admin, is_counsellor, is_parent, is_student


def is_staff_style_user(user):
    return bool(
        user
        and user.is_authenticated
        and (is_admin(user) or is_counsellor(user) or user.groups.filter(name="Viewer").exists())
    )


def user_security_compliance_state(user, policy=None):
    policy = policy or SecurityPolicy.get_solo()
    security_profile, _ = UserSecurityProfile.objects.get_or_create(user=user)
    issues = []

    if is_staff_style_user(user) and policy.require_staff_domain_match and not policy.user_has_allowed_staff_email(user):
        issues.append("email_domain")
    password_age_days = security_profile.password_age_days()
    if (
        is_staff_style_user(user)
        and policy.password_rotation_days
        and security_profile.password_changed_at is not None
        and password_age_days is not None
        and password_age_days >= policy.password_rotation_days
    ):
        issues.append("password_rotation")
    return {
        "policy": policy,
        "security_profile": security_profile,
        "issues": issues,
        "password_age_days": password_age_days,
        "is_compliant": not issues,
    }


def mfa_required_for_user(user, policy=None):
    policy = policy or SecurityPolicy.get_solo()
    if policy.require_mfa_for_all_accounts:
        return bool(user and user.is_authenticated)
    return is_staff_style_user(user) and policy.require_mfa_for_staff


def school_managed_auth_ready(policy=None):
    policy = policy or SecurityPolicy.get_solo()
    if not policy.require_school_managed_auth_for_staff:
        return True
    return bool(
        getattr(settings, "TRUSTED_IDENTITY_ENABLED", False)
        and getattr(settings, "TRUSTED_IDENTITY_EMAIL_HEADER", "")
    )


def local_staff_login_allowed(user, policy=None):
    policy = policy or SecurityPolicy.get_solo()
    if not is_staff_style_user(user):
        return True
    if not policy.require_school_managed_auth_for_staff:
        return True
    return user.username.lower() in policy.break_glass_accounts


def staff_ip_allowed(ip_address, user=None, policy=None):
    policy = policy or SecurityPolicy.get_solo()
    if not policy.restrict_staff_to_allowed_ip_ranges:
        return True
    if user and user.username.lower() in policy.break_glass_accounts:
        return True
    try:
        address = ipaddress.ip_address(ip_address)
    except ValueError:
        return False
    for item in policy.allowed_ip_ranges:
        try:
            if "/" in item:
                if address in ipaddress.ip_network(item, strict=False):
                    return True
            elif address == ipaddress.ip_address(item):
                return True
        except ValueError:
            continue
    return False


def governance_readiness(policy=None, now=None):
    policy = policy or SecurityPolicy.get_solo()
    now = now or timezone.localdate()
    checks = {
        "hosting": bool(policy.approved_hosting_environment.strip()),
        "privacy_owner": bool(policy.privacy_owner_name.strip() and policy.privacy_owner_email.strip()),
        "security_owner": bool(policy.security_owner_name.strip() and policy.security_owner_email.strip()),
        "operations_owner": bool(policy.operations_owner_name.strip() and policy.operations_owner_email.strip()),
        "privacy_review": bool(policy.last_privacy_review_at),
        "security_test": bool(policy.last_security_test_at),
        "operations_review": bool(policy.last_operations_review_at),
        "school_auth": school_managed_auth_ready(policy=policy),
        "staff_ip_ranges": (not policy.restrict_staff_to_allowed_ip_ranges) or bool(policy.allowed_ip_ranges),
    }
    return {
        "checks": checks,
        "complete_count": sum(1 for value in checks.values() if value),
        "total_count": len(checks),
        "is_ready": all(checks.values()),
    }


def deployment_security_posture():
    default_key = "django-insecure-local-dev-key-change-me"
    checks = {
        "debug_disabled": not getattr(settings, "DEBUG", True),
        "secret_key_replaced": getattr(settings, "SECRET_KEY", "") != default_key,
        "https_cookies": bool(getattr(settings, "SESSION_COOKIE_SECURE", False))
        and bool(getattr(settings, "CSRF_COOKIE_SECURE", False)),
        "ssl_redirect": bool(getattr(settings, "SECURE_SSL_REDIRECT", False)),
        "secure_exports_ready": secure_export_ready(),
        "trusted_hosts_configured": bool(getattr(settings, "ALLOWED_HOSTS", [])),
    }
    details = {
        "checks": checks,
        "complete_count": sum(1 for value in checks.values() if value),
        "total_count": len(checks),
        "is_ready": all(checks.values()),
        "warnings": [],
    }
    if not checks["debug_disabled"]:
        details["warnings"].append("Debug mode is still on.")
    if not checks["secret_key_replaced"]:
        details["warnings"].append("The default secret key is still in use.")
    if not checks["https_cookies"]:
        details["warnings"].append("Secure cookie protection is not fully enabled.")
    if not checks["ssl_redirect"]:
        details["warnings"].append("Automatic HTTPS redirect is not enabled.")
    if not checks["secure_exports_ready"]:
        details["warnings"].append("Encrypted export downloads are not ready on this server.")
    return details


def build_security_review_rows(users=None, policy=None, now=None):
    policy = policy or SecurityPolicy.get_solo()
    now = now or timezone.now()
    users = list(
        users
        or User.objects.select_related("security_profile", "counsellor_profile")
        .prefetch_related("groups")
        .order_by("username")
    )
    for user in users:
        UserSecurityProfile.objects.get_or_create(user=user)
    dormant_cutoff = now - timedelta(days=policy.dormant_account_review_days or 0)
    rows = []
    for user in users:
        compliance = user_security_compliance_state(user, policy=policy)
        dormant_for_review = False
        if policy.dormant_account_review_days:
            dormant_for_review = user.last_login is None or user.last_login < dormant_cutoff
        rows.append(
            {
                "user": user,
                "profile": compliance["security_profile"],
                "issues": compliance["issues"],
                "password_age_days": compliance["password_age_days"],
                "is_compliant": compliance["is_compliant"],
                "dormant_for_review": dormant_for_review,
                "mfa_required": mfa_required_for_user(user, policy=policy),
                "role_name": user.groups.first().name if user.groups.exists() else "",
                "local_staff_login_allowed": local_staff_login_allowed(user, policy=policy),
            }
        )
    return rows


def security_review_recipients():
    return list(
        User.objects.filter(groups__name="Admin", is_active=True)
        .exclude(email="")
        .values_list("email", flat=True)
        .distinct()
    )
