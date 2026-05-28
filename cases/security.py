from datetime import timedelta

from django.contrib.auth.models import User
from django.utils import timezone

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
