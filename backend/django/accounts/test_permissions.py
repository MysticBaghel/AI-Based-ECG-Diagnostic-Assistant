"""The permission classes, including the ones no view uses yet.

`IsDoctorOrAdmin` is the only class wired to endpoints today, so it is covered
through the API (403s in `devices/tests.py` and `monitoring/tests.py`). The
others are reserved for Phase 6 and are tested here directly, against a patient,
an assigned doctor, an unassigned doctor and an admin - so wiring them up later
is a one-line change rather than a discovery exercise.
"""

import pytest

from accounts.models import User
from accounts.permissions import (
    IsAdminRole,
    IsAssignedDoctor,
    IsDoctorOrAdmin,
    IsDoctorRole,
    IsOwnerOrAdmin,
    IsPatientRole,
)

pytestmark = pytest.mark.django_db


class _Request:
    """The only attribute these classes read is `request.user`."""

    def __init__(self, user):
        self.user = user


def test_role_permission_classes(doctor_a, doctor_b, patient_a, admin_user):
    """IsAdminRole / IsDoctorRole / IsPatientRole: exactly one role passes."""
    everyone = [
        ("patient", patient_a, User.Role.PATIENT),
        ("assigned doctor", doctor_a, User.Role.DOCTOR),
        ("unassigned doctor", doctor_b, User.Role.DOCTOR),
        ("admin", admin_user, User.Role.ADMIN),
    ]

    for permission in (IsAdminRole(), IsDoctorRole(), IsPatientRole()):
        for label, user, role in everyone:
            expected = permission.role == role
            assert (
                permission.has_permission(_Request(user), None) is expected
            ), f"{type(permission).__name__} with {label}"


def test_is_doctor_or_admin(patient_a, doctor_a, doctor_b, admin_user):
    permission = IsDoctorOrAdmin()

    assert permission.has_permission(_Request(patient_a), None) is False
    assert permission.has_permission(_Request(doctor_a), None) is True
    assert permission.has_permission(_Request(doctor_b), None) is True
    assert permission.has_permission(_Request(admin_user), None) is True


def test_is_assigned_doctor(doctor_a, doctor_b, patient_a, admin_user):
    """Only the assigned doctor passes; the unassigned doctor does not."""
    permission = IsAssignedDoctor()
    patient = patient_a.patient_profile

    assert permission.has_object_permission(_Request(patient_a), None, patient) is False
    assert permission.has_object_permission(_Request(doctor_a), None, patient) is True
    assert permission.has_object_permission(_Request(doctor_b), None, patient) is False
    assert permission.has_object_permission(_Request(admin_user), None, patient) is True


def test_is_assigned_doctor_accepts_an_object_that_has_a_patient_profile(
    doctor_a, doctor_b, patient_a
):
    """`obj` may be a Session (or anything with a patient_profile)."""
    permission = IsAssignedDoctor()

    assert permission.has_object_permission(_Request(doctor_a), None, patient_a) is True
    assert permission.has_object_permission(_Request(doctor_b), None, patient_a) is False


def test_is_owner_or_admin(doctor_a, doctor_b, patient_a, admin_user, device_a):
    permission = IsOwnerOrAdmin()

    assert (
        permission.has_object_permission(_Request(doctor_a), None, device_a) is True
    )
    assert (
        permission.has_object_permission(_Request(doctor_b), None, device_a) is False
    )
    assert (
        permission.has_object_permission(_Request(patient_a), None, device_a) is False
    )
    assert (
        permission.has_object_permission(_Request(admin_user), None, device_a) is True
    )
