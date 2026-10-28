"""The permanent patient registry: search, duplicate warning, update."""

import pytest

from patients.models import Patient

pytestmark = pytest.mark.django_db


def _create(client, **overrides):
    payload = {
        "full_name": "New Patient",
        "phone": "+91 99999 88888",
        "email": "new@example.test",
        "date_of_birth": "1990-04-12",
        "sex": "female",
        "notes": "Registered at the front desk.",
    }
    payload.update(overrides)
    return client.post("/api/patients/", payload, format="json")


def test_operator_registers_a_patient_with_a_permanent_id(client_for, operator):
    response = _create(client_for(operator))

    assert response.status_code == 201
    assert response.data["patient_id"].startswith("PT-")
    assert response.data["age"] is not None and response.data["age"] >= 30
    created = Patient.objects.get(pk=response.data["id"])
    assert created.phone_normalized == "+919999988888"


def test_search_finds_by_name_phone_and_patient_id(client_for, operator, patient_a):
    client = client_for(operator)

    by_name = client.get("/api/patients/?q=Aarav").data
    by_phone = client.get("/api/patients/?q=98765").data
    by_code = client.get(f"/api/patients/?q={patient_a.patient_id}").data

    assert [row["id"] for row in by_name] == [patient_a.id]
    assert [row["id"] for row in by_phone] == [patient_a.id]
    assert [row["id"] for row in by_code] == [patient_a.id]


def test_duplicate_phone_warns_and_requires_confirmation(client_for, operator, patient_a):
    client = client_for(operator)
    response = _create(client, full_name="Aarav Sharma", phone="+91 98765 43210")

    assert response.status_code == 409
    assert response.data["code"] == "duplicate_patient"
    assert response.data["duplicates"][0]["id"] == patient_a.id
    assert Patient.objects.filter(full_name="Aarav Sharma").count() == 1


def test_confirmed_duplicate_is_created(client_for, operator, patient_a):
    client = client_for(operator)
    response = _create(
        client,
        full_name="Aarav Sharma (twin brother)",
        phone="+91 98765 43210",
        confirm_duplicate=True,
    )

    assert response.status_code == 201
    assert Patient.objects.count() == 2


def test_an_empty_phone_never_triggers_the_warning(client_for, operator, patient_b):
    patient_b.phone = ""
    patient_b.save(update_fields=["phone", "phone_normalized"])
    response = _create(client_for(operator), phone="")

    assert response.status_code == 201


def test_patient_details_can_be_updated(client_for, operator, patient_a):
    response = client_for(operator).patch(
        f"/api/patients/{patient_a.id}/",
        {"phone": "+91 90000 22222", "notes": "Moved to a new number."},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["phone"] == "+91 90000 22222"
    patient_a.refresh_from_db()
    assert patient_a.phone_normalized == "+919000022222"
    assert patient_a.notes == "Moved to a new number."


def test_patient_id_is_never_client_supplied(client_for, operator):
    response = _create(client_for(operator), patient_id="HACKED")

    assert response.status_code == 201
    assert response.data["patient_id"] != "HACKED"


def test_patient_profile_lists_their_sessions(client_for, operator, patient_a, device_a):
    from monitoring.models import Session

    Session.objects.create(patient=patient_a, device=device_a, started_by=operator)

    response = client_for(operator).get(f"/api/patients/{patient_a.id}/sessions/")

    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["patient_code"] == patient_a.patient_id


def test_registration_requires_auth(api_client):
    response = api_client.post(
        "/api/patients/", {"full_name": "No Auth"}, format="json"
    )
    assert response.status_code == 401
