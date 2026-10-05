"""Reusable permission classes.

Endpoint access today is enforced by three things, all in this package:

* ``IsDoctorOrAdmin`` as the view-level gate on the device and session writes;
* ``get_permissions()`` in ``SessionViewSet``, which asks for ``IsAuthenticated``
  on reads and ``IsDoctorOrAdmin`` on create/stop;
* queryset filtering in each view, so a row the caller may not see is simply not
  in the queryset and DRF answers **404** instead of leaking its existence.

The role classes below (``IsAdminRole``, ``IsDoctorRole``, ``IsPatientRole``)
and the object-level ones (``IsAssignedDoctor``, ``IsOwnerOrAdmin``) are
implemented and unit-tested, but **no view uses them yet**. They are kept
deliberately for Phase 6 (reports, the doctor view, the admin dashboard), where
per-object checks stop being expressible as a queryset filter. Each one carries
that note in its docstring so the next reader does not delete it as dead code.
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
    """Reserved for Phase 6, not yet used by any view."""

    role = User.Role.ADMIN
    message = "Admin role required."


class IsDoctorRole(_RolePermission):
    """Reserved for Phase 6, not yet used by any view."""

    role = User.Role.DOCTOR
    message = "Doctor role required."


class IsPatientRole(_RolePermission):
    """Reserved for Phase 6, not yet used by any view."""

    role = User.Role.PATIENT
    message = "Patient role required."


class IsDoctorOrAdmin(BasePermission):
    """In use: every write a patient must not perform (403).

    Wired to ``DeviceViewSet`` and to the ``create``/``stop`` actions of
    ``SessionViewSet``.
    """

    message = "Doctor or admin role required."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user.is_authenticated
            and user.role in (User.Role.DOCTOR, User.Role.ADMIN)
        )


class IsAssignedDoctor(BasePermission):
    """Reserved for Phase 6, not yet used by any view.

    Object-level: the caller is the doctor assigned to this patient.

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
    """Reserved for Phase 6, not yet used by any view.

    Object-level: the caller owns the object, or is an admin.
    """

    message = "You do not own this object."

    def has_object_permission(self, request, view, obj):
        user = request.user

        if user.role == User.Role.ADMIN:
            return True
        return getattr(obj, "owner_id", None) == user.id
