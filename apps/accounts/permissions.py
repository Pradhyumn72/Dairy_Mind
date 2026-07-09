"""
Reusable DRF permission classes enforcing role-based access control.
"""
from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    """Grants access only to Farm_Users with the Admin role."""
    message = "You do not have permission to perform this action. Admin role required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_admin)


class IsFarmManager(BasePermission):
    """Grants access to Farm_Manager and Admin roles."""
    message = "Farm Manager or Admin role required."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_farm_manager or request.user.is_admin)
        )


class IsVet(BasePermission):
    """Grants access to Vet and Admin roles."""
    message = "Vet or Admin role required."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_vet or request.user.is_admin)
        )


class IsAdminOrFarmManager(BasePermission):
    """Grants access to Admin and Farm_Manager roles."""
    message = "Admin or Farm Manager role required."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_admin or request.user.is_farm_manager)
        )


class IsAnyRole(BasePermission):
    """Grants access to any authenticated Farm_User regardless of role."""
    message = "Authentication required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)
