from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied


ROLE_ADMIN = "Admin"
ROLE_COUNSELLOR = "Counsellor"
ROLE_VIEWER = "Viewer"
ROLE_NAMES = [ROLE_ADMIN, ROLE_COUNSELLOR, ROLE_VIEWER]


def ensure_roles():
    for role_name in ROLE_NAMES:
        Group.objects.get_or_create(name=role_name)


def user_has_role(user, role_name):
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name=role_name).exists())


def is_admin(user):
    return user_has_role(user, ROLE_ADMIN)


def is_counsellor(user):
    return user_has_role(user, ROLE_COUNSELLOR)


def is_viewer(user):
    return user_has_role(user, ROLE_VIEWER)


def can_view_student(user, student):
    if not user.is_authenticated:
        return False
    if is_admin(user) or is_viewer(user):
        return True
    return student.assigned_counsellor_id == user.id or is_counsellor(user)


def can_edit_student(user, student):
    if not user.is_authenticated:
        return False
    if is_admin(user):
        return True
    return is_counsellor(user) and student.assigned_counsellor_id == user.id


def require_admin(user):
    if not is_admin(user):
        raise PermissionDenied("You do not have permission to access this page.")
