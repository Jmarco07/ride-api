"""Custom DRF permissions."""
from rest_framework.permissions import BasePermission


class IsAdminRole(BasePermission):
    """Allow access only to authenticated users whose ``role`` is ``admin``.

    This is distinct from Django's ``is_staff``/``is_superuser`` flags: the
    assessment requires gating on the application-level ``role`` column.
    """

    message = "Only users with the 'admin' role may access this endpoint."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and getattr(user, "is_admin_role", False))
