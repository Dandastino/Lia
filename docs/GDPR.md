# GDPR / privacy analysis

> Technical analysis of the code. It is **not legal advice** and does not state that Lia "is" or "is not" compliant.
> Several requirements depend on organizational, contractual and legal facts that cannot be read from the code;
> those are listed explicitly at the end.

## 1. Roles (to be confirmed by the operator)

Typical setup: each customer organization is the **controller** of its business data (meetings, contacts, ...) and
the operator running Lia is a **processor** for that data; for Lia's own user accounts the operator is likely the
controller. This allocation is a legal determination: it is an open question below.

## 2. What personal data exists, where, and who can reach it

| Data | Where stored | Evidence in code | Who can access |
|------|--------------|------------------|----------------|
| User e-mail, bcrypt password hash, role, org, creation date | Lia PostgreSQL `users` | `models.User` | the user (own export), any `admin`/`owner`, DB operators |
| Mapping Lia user ↔ CRM user id and CRM e-mail | `external_user_mapping` | `models.ExternalUserMapping` | admins, the user (own export) |
| Which external records a user "owns" | `user_entity_ownership` (ids only) | `models.UserEntityOwnership` | admins, the user |
| Sync log (status, target, error text ≤ 500 chars) | `sync_logs` | `DataManager._log_sync_operation*` | DB operators. **Error text may echo personal data** coming from a CRM/driver error |
| Tenant connector credentials (not personal data of users, but of tenant staff) | `organizations.connector_config`, encrypted if key set | `app/crypto.py` | org admins (masked), DB operators |
| Meeting notes, participants, contacts, patients, ... | **Not stored by Lia**: written to the tenant's own DB/CRM | drivers | whoever the tenant's system allows |
| Voice audio and transcript | Streamed through LiveKit and OpenAI; Lia does not persist it | `agent.py` (OpenAI Realtime), `routes/livekit.py` | LiveKit and OpenAI as sub-processors |
| Request data in application/nginx logs | stdout / `/var/log/nginx` | nginx `access_log` records IP, user agent, `$remote_user` | operator |
| Browser | `localStorage`: JWT + user object (id, e-mail, org, role) | `frontend/src/lib/storage.js` | the browser profile |

No analytics, advertising or third-party tracking code and no cookies were found in the frontend. `localStorage` is
strictly necessary for the session, so a consent banner is probably not required for it (to be confirmed).

## 3. Third parties receiving personal data

* **OpenAI** (voice model and the schema-mapping call): audio, transcripts, table/column names and tool arguments
  that contain tenant data. Likely a transfer outside the EEA.
* **LiveKit** (cloud or self-hosted): audio, participant identity `User_<uuid>` and display name (the e-mail by default).
* **The tenant's CRM/DB provider** (HubSpot, Salesforce, Microsoft, ...): receives the data the user dictates.
* HubSpot owner look-up sends the user's e-mail to HubSpot.

## 4. Requirement-by-requirement

| Topic | Finding from code | Gap / action |
|-------|-------------------|--------------|
| Access/portability (Art. 15, 20) | **Added** `GET /me/export` (Lia-held data only) | Business records must be exported from the tenant's system; document this in the controller's procedure |
| Erasure (Art. 17) | **Added** `DELETE /me` (password-confirmed; cascades to ownership and mappings); admins already had `DELETE /admin/users/<id>` | Does not delete data in the tenant's CRM; backups and logs are outside the app |
| Rectification (Art. 16) | Admin can change e-mail; users cannot yet change their own e-mail (**`PUT /me/password` added**) | Decide whether self-service e-mail change is needed |
| Retention / storage limitation | No retention existed for `sync_logs` | **Added** `manage.py purge-sync-logs --days N`; schedule it (cron) and choose N. No retention for accounts beyond manual deletion |
| Data minimization | Display name sent to LiveKit defaults to the e-mail; sync-log errors may hold personal data (now truncated to 500 chars) | Consider a pseudonymous display name; avoid logging record content |
| Security of processing (Art. 32) | Encryption of credentials at rest, bcrypt, TLS termination in nginx, rate limiting, headers | DB-level encryption/backups, key management (who holds `CONNECTOR_ENCRYPTION_KEY`) are operational |
| Privacy by default | Tenant read scope defaults to permissive (`allow_unowned_read=true`) | Recommend `restrict_to_owned_entities=true` default for new tenants (see SECURITY.md) |
| Logging | nginx logs full client IP + `X-Forwarded-For`; app logs contain user e-mails/ids (e.g. `Created … for user <email>`) | Define log retention; consider IP truncation |
| Consent / transparency (Art. 13) | No privacy notice, no consent capture, no notice that conversations are processed by OpenAI/LiveKit | Needs a notice and, if voice is recorded/transcribed for meeting participants, a legal basis for **other participants** whose data is spoken |
| Special categories | Industry examples mention patients/clinics; the code is industry-agnostic | If health data is processed, Art. 9 conditions and a DPIA are likely needed |
| International transfers | OpenAI/LiveKit/CRM regions are not configurable in code | Needs SCCs/DPF assessment and region choice |
| Breach notification | No audit log of admin/data-access actions | Add audit logging if required by the controller's policy |

## 5. Information needed from the operator (cannot be derived from the code)

1. Controller/processor roles per data category; signed DPAs with each tenant, OpenAI, LiveKit and hosting provider.
2. Legal basis per purpose, and for non-user participants in meetings.
3. Retention periods for accounts, sync logs, nginx/application logs and backups.
4. Hosting region(s), LiveKit deployment (cloud vs self-hosted), OpenAI data-retention/zero-retention settings.
5. Whether any tenant processes special-category data (health) → DPIA.
6. Who may hold the encryption and JWT keys, and the incident-response / breach-notification procedure.
7. Privacy notice text and where it is shown to end users.
