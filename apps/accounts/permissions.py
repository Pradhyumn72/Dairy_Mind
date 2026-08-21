"""
Custom DRF permission classes based on Profile roles.
"""
from rest_framework import permissions

class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Allows read-only access for any authenticated user.
    Allows creation (POST) for OWNER and WORKER.
    Restricts DELETE (and potentially PUT/PATCH) to OWNER only.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return True

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        if request.method in permissions.SAFE_METHODS:
            return True

        profile = getattr(request.user, 'profile', None)
        if not profile:
            return False

        if request.method == 'DELETE':
            return profile.is_owner
        
        # Depending on exact semantics, we allow WORKERs to update objects
        # as well as OWNERs. If we wanted to restrict updates to OWNERs only, 
        # we would add `if request.method in ['PUT', 'PATCH']: return profile.is_owner` here.
        return True


class IsVetOrOwner(permissions.BasePermission):
    """
    Allows access only to VET or OWNER roles.
    Useful for sensitive operations like uploading Vet Reports.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
            
        profile = getattr(request.user, 'profile', None)
        if not profile:
            return False
            
        return profile.is_vet or profile.is_owner

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)
