from .permissions import (
    counsellor_primary_team,
    has_active_parent_portal,
    has_active_student_portal,
    is_admin,
    is_counsellor,
    is_parent,
    is_student,
    is_viewer,
)


def app_context(request):
    user = request.user
    return {
        "role_flags": {
            "is_admin": is_admin(user),
            "is_counsellor": is_counsellor(user),
            "is_viewer": is_viewer(user),
            "is_student": is_student(user),
            "is_student_portal": has_active_student_portal(user),
            "is_parent": is_parent(user),
            "is_parent_portal": has_active_parent_portal(user),
            "counsellor_team": counsellor_primary_team(user),
        }
    }
