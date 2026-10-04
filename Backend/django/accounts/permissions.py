"""Reusable permission classes.

Two layers are used together:

* role checks (``IsAdminRole`` and friends) answer "may this kind of user call
  this endpoint at all?", and
* queryset filtering in each view answers "which rows may they see?", so an
  object they may not touch is a 404 rather than a 403.

The object-level classes below are for the cases where a view already has an
object in hand (an action such as ``stop`` or ``rotate-token``).
"""

from rest_framework.permissions import BasePermission

from .models import User


class _RolePermission(BasePermission):
    role = None
    message = "You do not have the required role."

    def has_permission(self, request, view):
        user = request.user
        return bool(user.is_authenticated and user.role == self.role)


class IsAdminRole(_RolePermission):
    role = User.Role.ADMIN
    message = "Admin role required."


class IsDoctorRole(_RolePermission):
    role = User.Role.DOCTOR
    message = "Doctor role required."


class IsPatientRole(_RolePermission):
    role = User.Role.PATIENT
    message = "Patient role required."


class IsDoctorOrAdmin(BasePermission):
    """Used for every write a patient must not perform (403)."""

    message = "Doctor or admin role required."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user.is_authenticated
            and user.role in (User.Role.DOCTOR, User.Role.ADMIN)
        )


class IsAssignedDoctor(BasePermission):
    """Object-level: the caller is the doctor assigned to this patient.

    Admins pass; a doctor passes only when a DoctorAssignment links them to the
    patient. ``obj`` may be a PatientProfile or anything with one attached.
    """

    message = "You are not assigned to this patient."

    def has_object_permission(self, request, view, obj):
        user = request.user

        if user.role == User.Role.ADMIN:
            return True
        if user.role != User.Role.DOCTOR:
            return False

        patient = getattr(obj, "patient_profile", obj)
        return patient.assignments.filter(doctor__user=user).exists()


class IsOwnerOrAdmin(BasePermission):
    """Object-level: the caller owns the object, or is an admin."""

    message = "You do not own this object."

    def has_object_permission(self, request, view, obj):
        user = request.user

        if user.role == User.Role.ADMIN:
            return True
        return getattr(obj, "owner_id", None) == user.id
