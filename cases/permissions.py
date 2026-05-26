from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied


ROLE_ADMIN = "Admin"
ROLE_COUNSELLOR = "Counsellor"
ROLE_VIEWER = "Viewer"
ROLE_STUDENT = "Student"
ROLE_PARENT = "Parent"
ROLE_NAMES = [ROLE_ADMIN, ROLE_COUNSELLOR, ROLE_VIEWER, ROLE_STUDENT, ROLE_PARENT]


def ensure_roles():
    for role_name in ROLE_NAMES:
        Group.objects.get_or_create(name=role_name)


def user_has_role(user, role_name):
    if not user.is_authenticated:
        return False
    if role_name == ROLE_ADMIN:
        return user.is_superuser or user.groups.filter(name=role_name).exists()
    return user.groups.filter(name=role_name).exists()


def is_admin(user):
    return user_has_role(user, ROLE_ADMIN)


def is_counsellor(user):
    return user_has_role(user, ROLE_COUNSELLOR)


def is_viewer(user):
    return user_has_role(user, ROLE_VIEWER)


def is_student(user):
    return user_has_role(user, ROLE_STUDENT)


def is_parent(user):
    return user_has_role(user, ROLE_PARENT)


def get_portal_student(user):
    if not is_student(user):
        return None
    portal_access = getattr(user, "student_portal", None)
    if portal_access and portal_access.is_active:
        return portal_access.student
    return None


def has_active_student_portal(user):
    return get_portal_student(user) is not None


def get_parent_students(user):
    if not is_parent(user):
        return []
    return [link.student for link in user.parent_portal_links.select_related("student").filter(is_active=True)]


def has_active_parent_portal(user):
    return bool(get_parent_students(user))


def normalized_team_name(value):
    return (value or "").strip().casefold()


def counsellor_primary_team(user):
    profile = getattr(user, "counsellor_profile", None)
    if not profile:
        return ""
    return profile.primary_team


def counsellor_has_granted_student_access(user, student):
    if not is_counsellor(user):
        return False
    return student.extra_counsellor_access.filter(counsellor=user, is_active=True).exists()


def counsellor_can_access_student(user, student):
    if not is_counsellor(user):
        return False
    if student.assigned_counsellor_id == user.id:
        return True
    if counsellor_has_granted_student_access(user, student):
        return True
    return normalized_team_name(student.support_team) and normalized_team_name(student.support_team) == normalized_team_name(
        counsellor_primary_team(user)
    )


def can_view_student(user, student):
    if not user.is_authenticated:
        return False
    if is_admin(user) or is_viewer(user):
        return True
    if is_parent(user):
        return any(child.pk == student.pk for child in get_parent_students(user))
    if has_active_student_portal(user):
        portal_student = get_portal_student(user)
        return bool(portal_student and portal_student.pk == student.pk)
    return counsellor_can_access_student(user, student)


def can_edit_student(user, student):
    if not user.is_authenticated:
        return False
    if is_admin(user):
        return True
    return counsellor_can_access_student(user, student)


def require_admin(user):
    if not is_admin(user):
        raise PermissionDenied("You do not have permission to access this page.")
