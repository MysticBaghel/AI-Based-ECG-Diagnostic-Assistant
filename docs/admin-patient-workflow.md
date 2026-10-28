> **Historical note.** This document described the pre-refactor admin workflow
> for creating patient login accounts and assigning doctors. That workflow was
> removed in the ECG refactor. Patients are now permanent registry records, and
> there is no doctor assignment. See `docs/Restructured.pdf`.

# Admin patient, doctor and device workflow

This document describes the account-administration workflow added on top of the
Phase 4 dashboard:

* an admin creates a patient login **and** its patient profile in one action;
* an admin assigns that patient to one or more doctors;
* an admin dedicates a registered ECG device to a patient;
* the assigned doctor sees the patient in the existing monitoring dashboard;
* a doctor or patient who calls the same endpoints directly receives **403** —
  the buttons are not the security boundary.

The system remains a **screening aid, not a medical diagnosis**.

---

## 1. Data model

```
User (role=patient)  1───1  PatientProfile
                                   │
                                   │ many-to-many through DoctorAssignment
                                   │
                             DoctorProfile ──1  User (role=doctor)

Device
  owner           → User (doctor or admin who registered it)
  assigned_patient → PatientProfile, nullable
```

| Model | Meaning |
| --- | --- |
| `User` (`role=patient`) | The login account: username, password hash, role |
| `PatientProfile` | The monitored person: date of birth and notes |
| `DoctorAssignment` | Which doctor is responsible for which patient; unique per pair |
| `Device.owner` | The doctor (or admin) who registered the device; never taken from a request body |
| `Device.assigned_patient` | Optional dedication of one physical unit to one patient |

Two invariants are deliberate:

1. **Registering a device and assigning it to a patient are separate calls.**
   `POST /api/devices/` creates the device with `assigned_patient = NULL`.
   `POST /api/devices/<id>/assign-patient/` is the only way to change it.
2. **An assigned device cannot be used for another patient.** When a session is
   created, `SessionSerializer` rejects a patient that differs from
   `device.assigned_patient`. This is a data rule, so it applies to admins as
   well as doctors.

A third consistency rule is enforced when assigning a device: if the device is
owned by a doctor, that doctor must already be assigned to the patient.
Otherwise the device would be dedicated to someone its owner cannot monitor.

`assigned_patient = NULL` means **shared**: the owning doctor may use the device
for any patient they are assigned to, subject to the one-active-session-per-device
rule.

## 2. API

All endpoints use Django's JWT authentication (`Authorization: Bearer …`).
Permissions are enforced with `IsAdminRole` in the view, not by the React route.

| Method | Path | Permission | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/patients/` | **admin only** | Create `User(role=patient)` + `PatientProfile` atomically, optionally with `doctor_ids` |
| `PUT` | `/api/patients/<id>/doctors/` | **admin only** | Replace the patient's care team with `{"doctor_ids": [...]}`; `[]` removes everyone |
| `GET` | `/api/doctors/` | **admin only** | Doctor profiles for the assignment controls |
| `POST` | `/api/devices/<id>/assign-patient/` | **admin only** | Set `{"patient": <profile id>}` or `{"patient": null}` |
| `GET` | `/api/patients/` | authenticated, queryset-scoped | Admin: all; doctor: assigned; patient: self |
| `GET` | `/api/devices/` | doctor/admin | Admin: all; doctor: owned |
| `POST` | `/api/sessions/` | doctor/admin | Normal session start; now also enforces the device–patient match |

### 2.1 Create a patient

```http
POST /api/patients/
Content-Type: application/json
Authorization: Bearer <admin access token>

{
  "username": "patient5",
  "password": "strong-pass-123",
  "email": "patient5@example.test",
  "date_of_birth": "1994-06-20",
  "notes": "Referred from the clinic.",
  "doctor_ids": [1]
}
```

Response `201` is the same shape as the patient list, including the derived
`doctor_ids` and `doctor_usernames`:

```json
{
  "id": 5,
  "user": 14,
  "username": "patient5",
  "email": "patient5@example.test",
  "date_of_birth": "1994-06-20",
  "notes": "Referred from the clinic.",
  "doctor_ids": [1],
  "doctor_usernames": ["doctor1"]
}
```

Validation:

* username is unique case-insensitively;
* password goes through Django's configured password validators;
* `doctor_ids` must be existing `DoctorProfile` ids;
* user and profile are created in one transaction, so a failure leaves neither.

### 2.2 Replace the care team

```http
PUT /api/patients/5/doctors/
Content-Type: application/json
Authorization: Bearer <admin access token>

{"doctor_ids": [1, 2]}
```

This deletes the patient's existing `DoctorAssignment` rows and creates the new
set. The old doctor loses visibility immediately. An empty list is valid.

After the transaction, each session of that patient is re-pushed to FastAPI (the
registry snapshot of `doctor_ids`) so the new doctor can also open live and
stored recordings. The push is best-effort, exactly like the session-creation
push; if FastAPI is down, live viewer access stays stale until the next
successful push.

### 2.3 Assign a device to a patient

```http
POST /api/devices/<uuid>/assign-patient/
Content-Type: application/json
Authorization: Bearer <admin access token>

{"patient": 5}
```

`{"patient": null}` unassigns it. The response is the normal device shape with
`assigned_patient` and `assigned_patient_name`.

The action refuses with `400` when:

* the patient id does not exist;
* the device is owned by a doctor who is not assigned to that patient.

It does **not** rewrite any existing session. Changing a device's dedication
affects the next session start; a session that is already running keeps its
patient and device.

### 2.4 What a session start now checks

`SessionSerializer.validate` applies, in order:

1. the device is not disabled;
2. `device.assigned_patient` is null or equals the requested patient;
3. for an admin: continue;
4. for a doctor: the doctor is assigned to the patient and owns the device;
5. the device has no other active session.

So an admin-created patient can be monitored by their doctor, but an admin
cannot bypass the physical unit's dedication.

## 3. React frontend

### 3.1 Admin route

`/admin/patients` (`AdminPatientsPage.tsx`) is visible in the **Administration**
nav group only for `admin`, and is also wrapped in `RoleGate allow={['admin']}`.
It contains:

* **Create a patient** — username, temporary password, email, date of birth,
  notes, and an optional doctor multi-select;
* **Patients and their doctors** — one row per patient with a doctor picker and
  a Save button (the picker is local state until saved);
* **Device assignments** — every registered device with an
  “Unassigned (shared)” / patient select.

The page explicitly says the API enforces the permissions; the route guard is
only navigation.

### 3.2 Doctor-facing pages stay about monitoring

The doctor's `/patients` page did not gain account-administration controls. It
still shows exactly the patients the Django queryset returns, with a "Start
session" action. Creating accounts and assigning doctors lives under
`/admin/patients`.

### 3.3 Device assignment is visible in the monitoring UI

* The Devices table has an **Assigned patient** column (`Unassigned / shared`
  when null), for doctors and admins.
* The start-session dialog only offers active devices that are unassigned or
  dedicated to the selected patient. A device dedicated to someone else is
  hidden, and the dialog explains why if none are available.
* The backend still enforces the rule; the filter is a convenience, not the
  control.

## 4. Django Admin

The Django Admin site is the second way to perform the same workflow:

| Admin page | What it does |
| --- | --- |
| **Users → Add user** | The patient profile inline appears for a patient account, so account + profile can be saved together |
| **Patient profiles** | A doctor-assignment inline; `Doctors` column lists the assigned care team |
| **Doctor profiles** | Existing assignment inline, unchanged |
| **Devices** | `assigned_patient` is editable and searchable; `list_filter` includes it |

The API and Django Admin write the same models; there is no second source of
truth.

## 5. Verification performed

The workflow was exercised against a live Django + FastAPI pair:

```text
OK  admin lists doctors: 200
    doctor1 profile id: 1 | current patients: [1, 2]
OK  admin creates patient + assigns doctor1: 201
    patient id: 5 | username: admin_patient_ccaee5 | doctors: ['doctor1']
OK  doctor1 re-reads patient list: 200
    visible to doctor1: ['patient1', 'patient2', 'admin_patient_ccaee5']
OK  doctor cannot create patient: 403
OK  doctor cannot change assignment: 403
OK  doctor1 registers device: 201
    registered with assigned_patient: None
OK  admin dedicates device to patient: 200
    assigned_patient_name: admin_patient_ccaee5
OK  doctor1 starts session for new patient: 201
    session: 824174f9-… | patient_name: admin_patient_ccaee5
OK  doctor session history contains new patient: True
OK  assigned device refused for another patient: 400
    ['This device is assigned to a different patient. Unassign it first.']
OK  session stopped
```

The backend test suite also covers:

* admin creates a user + profile + assignment in one request;
* doctor and patient receive `403` for creation and assignment;
* assignment replacement changes the doctor-visible patient list;
* admin doctor listing is admin-only;
* unknown doctors, duplicate usernames and unknown patients are rejected;
* device creation leaves `assigned_patient` null;
* a doctor cannot assign a device;
* a device owned by doctor B cannot be dedicated to doctor A's patient;
* an assigned device starts a session only for its patient, including for admins;
* an unassigned device remains usable for any permitted patient.

## 6. Security notes and limits

* **Server-side authorization.** `IsAdminRole` gates creation, doctor assignment,
  the doctor list and device assignment. Hiding nav items is not relied on.
* **Registration and assignment are separate.** This is a deliberate two-step
  workflow, not an accident of the form.
* **A dedicated device is a hard constraint.** The session serializer checks it
  for every role, including admin.
* **No audit trail yet.** Who created or reassigned which patient is not logged
  beyond Django's normal request logging; audit-style records are a Phase 6
  concern.
* **Assignment changes do not retroactively edit sessions.** A running or
  completed session keeps the patient and device it started with. The device's
  new dedication applies to future starts.
* **Registry sync is best-effort.** Doctor changes are pushed to FastAPI's
  session registry; if that service is down, Django still saves the assignment
  and FastAPI's viewer permissions stay stale until the next successful push.
* **No bulk import or self-service signup.** An admin creates each patient.
* **Passwords are temporary.** The admin form sets a password that the patient
  can later be given; there is no password-reset email flow in this phase.
* **One patient can have many devices; one device has at most one patient.**
  Multiple devices per patient is allowed (for example a spare unit), and
  unassigned devices are shared.
* **Not a medical device.** The workflow manages accounts and assignments; it
  does not diagnose, and the screening-aid disclaimer remains on every screen.
