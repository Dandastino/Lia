"""HubSpot CRM driver for Lia."""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

from .base import BaseDriver
from .sql_driver_common import get_entity_mapping

logger = logging.getLogger("hubspot_driver")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_TASK_TYPES = {"CALL", "EMAIL", "TODO"}
_TASK_STATUSES = {"NOT_STARTED", "IN_PROGRESS", "WAITING", "COMPLETED", "DEFERRED"}
_MEETING_OUTCOMES = {"SCHEDULED", "COMPLETED", "RESCHEDULED", "NO_SHOW", "CANCELED"}
_READ_ONLY_PROPS = {"hs_createdate", "hs_lastmodifieddate", "hs_object_id", "hs_body_preview"}

_OBJECT_ALIASES: Dict[str, str] = {
    "contact": "contacts",    "company": "companies",  "deal": "deals",
    "ticket": "tickets",      "task": "tasks",          "note": "notes",
    "meeting": "meetings",    "call": "calls",          "email": "emails",
    "product": "products",    "quote": "quotes",        "line_item": "line_items",
    "client": "contacts",     "clients": "contacts",
    "customer": "contacts",   "customers": "contacts",
    "contacts": "contacts",   "companies": "companies", "deals": "deals",
    "tickets": "tickets",     "tasks": "tasks",         "notes": "notes",
    "meetings": "meetings",   "calls": "calls",         "emails": "emails",
}

_ACTIVITY_TYPES = {"meetings", "calls", "notes", "emails", "tasks"}


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
class HubSpotDriver(BaseDriver):
    """HubSpot CRM connector for Lia."""

    def __init__(self, connector_config: Optional[Dict[str, Any]] = None):
        super().__init__(connector_config)

        api_key = self.config.get("api_key")
        if not api_key:
            raise ValueError("HubSpot connector requires 'api_key' in connector_config")

        self._api_key: str = api_key
        self._base_url = "https://api.hubapi.com"
        self._verify_ssl = bool(self.config.get("verify_ssl", True))
        try:
            self._timeout = max(1.0, float(self.config.get("request_timeout_seconds", 20)))
        except (TypeError, ValueError):
            self._timeout = 20.0

        if not self._verify_ssl:
            logger.warning("[HubSpot] SSL verification disabled — enable outside local testing")

    # -------------------------------------------------------------------------
    # HTTP layer
    # -------------------------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = path if path.startswith("http") else f"{self._base_url}{path}"
        kwargs.setdefault("headers", self._headers())
        kwargs.setdefault("verify", self._verify_ssl)
        kwargs.setdefault("timeout", self._timeout)
        try:
            response = requests.request(method.upper(), url, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as err:
            resp = getattr(err, "response", None)
            detail = (
                f"HTTP {resp.status_code}: {(resp.text or '').strip()[:400]}"
                if resp is not None
                else str(err)
            )
            logger.warning("[HubSpot] %s %s -> %s", method.upper(), path, detail)
            raise

    # -------------------------------------------------------------------------
    # Timestamp utilities
    # -------------------------------------------------------------------------

    @staticmethod
    def _ts_now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _ts_coerce(value: Any) -> Optional[str]:
        """Convert epoch (ms or s), datetime, or ISO string to RFC3339 UTC."""
        if value is None:
            return None
        if isinstance(value, datetime):
            dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        if isinstance(value, (int, float)):
            ts = float(value)
            if ts > 1e10:   # milliseconds -> seconds
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return None
            if re.fullmatch(r"\d+(?:\.\d+)?", s):
                return HubSpotDriver._ts_coerce(float(s))
            try:
                parsed = datetime.fromisoformat(s.replace("Z", "+00:00"))
                if not parsed.tzinfo:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            except ValueError:
                return None
        return None

    # -------------------------------------------------------------------------
    # Object type normalization
    # -------------------------------------------------------------------------

    @staticmethod
    def _get_prop_value(properties: Dict[str, Any], mapping_value: Any) -> Any:
        """Resolve a column-mapping value from a HubSpot properties dict."""
        if isinstance(mapping_value, list):
            parts = [
                str(properties.get(p) or "").strip()
                for p in mapping_value
                if isinstance(p, str) and p.strip()
            ]
            joined = " ".join(p for p in parts if p)
            return joined or None
        return properties.get(mapping_value)

    @staticmethod
    def _normalize_object_type(raw: str) -> str:
        """
        Accept singular or plural names ('contact', 'contacts', 'meeting_id')
        and return the canonical HubSpot API path segment (always plural).
        """
        cleaned = raw.strip().lower()
        if cleaned.endswith("_id"):
            cleaned = cleaned[:-3]
        return _OBJECT_ALIASES.get(cleaned, cleaned)

    # -------------------------------------------------------------------------
    # Contact & Company lookup 
    # -------------------------------------------------------------------------

    def find_contact(
        self,
        email: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Search a HubSpot contact by email (preferred) or full name."""
        if not email and not name:
            return None

        if email:
            logger.info("[HubSpot] Searching contact by email: %s", email)
            search_filters = [{"propertyName": "email", "operator": "EQ", "value": email.strip()}]
        else:
            parts = (name or "").strip().split(None, 1)
            firstname, lastname = parts[0], parts[1] if len(parts) > 1 else ""
            logger.info("[HubSpot] Searching contact by name: %s", name)
            search_filters = [{"propertyName": "firstname", "operator": "EQ", "value": firstname}]
            if lastname:
                search_filters.append({"propertyName": "lastname", "operator": "EQ", "value": lastname})

        try:
            resp = self._request(
                "POST",
                "/crm/v3/objects/contacts/search",
                json={
                    "filterGroups": [{"filters": search_filters}],
                    "properties": ["firstname", "lastname", "email", "hubspot_owner_id"],
                    "limit": 20,
                },
            )
            results = resp.json().get("results", [])
            if not results and name:
                # Fallback: exact first/last filters are strict and can miss
                return self._find_contact_by_loose_name(name)
            if not results:
                logger.info("[HubSpot] Contact not found")
                return None

            item = results[0]
            if len(results) > 1:
                requested_owner = str(getattr(self, "request_owner_id", "") or "").strip()
                if requested_owner:
                    owner_matches = []
                    for row in results:
                        props = row.get("properties", {}) if isinstance(row.get("properties"), dict) else {}
                        owner_val = str(props.get("hubspot_owner_id") or "").strip()
                        if owner_val and owner_val == requested_owner:
                            owner_matches.append(row)
                    if len(owner_matches) == 1:
                        item = owner_matches[0]
                    elif len(owner_matches) > 1:
                        item = owner_matches[0]

                candidate_ids = [str(r.get("id")) for r in results if isinstance(r, dict) and r.get("id")]
                logger.warning(
                    "[HubSpot] Ambiguous contact match for '%s' (%d candidates). Selected id=%s candidates=%s",
                    name or email,
                    len(results),
                    item.get("id"),
                    candidate_ids,
                )

            props = item.get("properties", {})
            contact = {
                "id": item["id"],
                "email": props.get("email", ""),
                "firstname": props.get("firstname", ""),
                "lastname": props.get("lastname", ""),
            }
            logger.info("[HubSpot] Contact found -> id=%s", contact["id"])
            return contact
        except Exception as err:
            logger.warning("[HubSpot] Contact search failed: %s", err)
            if name:
                return self._find_contact_by_loose_name(name)
            return None

    def _find_contact_by_loose_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Best-effort contact match by normalized full-name containment."""
        target = self._normalize_text_for_match(name)
        if not target:
            return None

        try:
            limit = int(self.config.get("contact_text_match_limit", 200))
        except (TypeError, ValueError):
            limit = 200
        limit = max(20, min(limit, 500))

        try:
            contacts = self._search_objects(
                "contacts",
                properties=["firstname", "lastname", "email"],
                limit=limit,
            )
        except Exception as exc:
            logger.debug("[HubSpot] Loose contact-name lookup skipped: %s", exc)
            return None

        for row in contacts:
            if not isinstance(row, dict):
                continue
            props = row.get("properties", {}) if isinstance(row.get("properties"), dict) else {}
            first = str(props.get("firstname") or "").strip()
            last = str(props.get("lastname") or "").strip()
            full_name = " ".join(part for part in [first, last] if part).strip()
            if not full_name:
                continue

            candidate = self._normalize_text_for_match(full_name)
            if not candidate:
                continue

            if target in candidate or candidate in target:
                logger.info("[HubSpot] Contact loosely matched by name -> id=%s", row.get("id"))
                return {
                    "id": row.get("id"),
                    "email": props.get("email", ""),
                    "firstname": first,
                    "lastname": last,
                }

        logger.info("[HubSpot] Contact not found (loose name)")
        return None

    def find_company(self, name: str) -> Optional[Dict[str, Any]]:
        """Search a HubSpot company by exact name."""
        logger.info("[HubSpot] Searching company by name: %s", name)
        try:
            resp = self._request(
                "POST",
                "/crm/v3/objects/companies/search",
                json={
                    "filterGroups": [{"filters": [
                        {"propertyName": "name", "operator": "EQ", "value": name.strip()}
                    ]}],
                    "properties": ["name", "domain"],
                    "limit": 1,
                },
            )
            results = resp.json().get("results", [])
            if not results:
                logger.info("[HubSpot] Company not found")
                return None
            item = results[0]
            props = item.get("properties", {})
            company = {
                "id": item["id"],
                "name": props.get("name", ""),
                "domain": props.get("domain", ""),
            }
            logger.info("[HubSpot] Company found -> id=%s", company["id"])
            return company
        except Exception as err:
            logger.warning("[HubSpot] Company search failed: %s", err)
            return None

    # -------------------------------------------------------------------------
    # Association (CRM v4) 
    # -------------------------------------------------------------------------

    def _associate(self, from_type: str, from_id: str, to_type: str, to_id: str) -> bool:
        """Create a default association between two HubSpot objects (v4 API)."""
        from_t = self._normalize_object_type(from_type)
        to_t = self._normalize_object_type(to_type)
        logger.info("[HubSpot] Associating %s/%s -> %s/%s", from_t, from_id, to_t, to_id)
        try:
            self._request(
                "PUT",
                f"/crm/v4/objects/{from_t}/{from_id}/associations/default/{to_t}/{to_id}",
            )
            logger.info("[HubSpot] Association OK: %s/%s -> %s/%s", from_t, from_id, to_t, to_id)
            return True
        except Exception as err:
            logger.warning(
                "[HubSpot] Association FAILED %s/%s -> %s/%s: %s",
                from_t, from_id, to_t, to_id, err,
            )
            return False

    def _list_association_ids(self, from_type: str, from_id: str, to_type: str) -> List[str]:
        """Return associated object IDs for a HubSpot object relation."""
        from_t = self._normalize_object_type(from_type)
        to_t = self._normalize_object_type(to_type)
        try:
            resp = self._request(
                "GET",
                f"/crm/v4/objects/{from_t}/{from_id}/associations/{to_t}",
            )
            results = (resp.json() or {}).get("results") or []
            ids: List[str] = []
            for row in results:
                if not isinstance(row, dict):
                    continue
                to_obj = row.get("toObjectId")
                if to_obj is None:
                    continue
                text = str(to_obj).strip()
                if text:
                    ids.append(text)
            return ids
        except Exception as exc:
            logger.debug(
                "[HubSpot] Failed to list associations %s/%s -> %s: %s",
                from_t,
                from_id,
                to_t,
                exc,
            )
            return []

    # -------------------------------------------------------------------------
    # Smart association resolver 
    # -------------------------------------------------------------------------

    def _resolve_and_associate(
        self,
        obj_type: str,
        obj_id: str,
        payload: Dict[str, Any],
    ) -> int:
        """
        After creating a HubSpot object, inspect the payload for association hints and create all relevant links automatically."""
        count = 0
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}

        def _pick(*values: Any) -> str:
            for val in values:
                text = str(val or "").strip()
                if text:
                    return text
            return ""

        contact_id_hint = _pick(
            payload.get("contact_id"),
            metadata.get("contact_id"),
            metadata.get("related_contact_id"),
            metadata.get("related_client_id"),
            metadata.get("client_id"),
        )
        company_id_hint = _pick(
            payload.get("company_id"),
            metadata.get("company_id"),
            metadata.get("related_company_id"),
            metadata.get("account_id"),
        )
        contact_email_hint = _pick(payload.get("contact_email"), metadata.get("contact_email"))
        contact_name_hint = _pick(payload.get("contact_name"), metadata.get("contact_name"))
        company_name_hint = _pick(payload.get("company_name"), metadata.get("company_name"))

        # 1. Direct IDs -> no network lookup needed
        if contact_id := contact_id_hint:
            if self._associate(obj_type, obj_id, "contacts", contact_id):
                count += 1

        if company_id := company_id_hint:
            if self._associate(obj_type, obj_id, "companies", company_id):
                count += 1

        # 2. Lookup by email or name when no direct contact_id was given
        if not contact_id_hint:
            contact: Optional[Dict[str, Any]] = None
            if email := contact_email_hint:
                contact = self.find_contact(email=email)
            elif cname := contact_name_hint:
                contact = self.find_contact(name=cname)
            if contact and self._associate(obj_type, obj_id, "contacts", contact["id"]):
                count += 1

        if not company_id_hint:
            if company_name := company_name_hint:
                company = self.find_company(company_name)
                if company and self._associate(obj_type, obj_id, "companies", company["id"]):
                    count += 1

        # 3. Language-agnostic participant hints (names/emails) from payload.
        if count == 0 and not contact_id_hint:
            for hint in self._extract_participant_contact_hints(payload):
                contact: Optional[Dict[str, Any]] = None
                if hint.get("email"):
                    contact = self.find_contact(email=hint["email"])
                if not contact and hint.get("name"):
                    contact = self.find_contact(name=hint["name"])
                if contact and self._associate(obj_type, obj_id, "contacts", contact["id"]):
                    logger.info(
                        "[HubSpot] Auto-associated participant hint: email=%s name=%s",
                        hint.get("email", ""),
                        hint.get("name", ""),
                    )
                    count += 1
                    break

        # 3b. Language-agnostic fallback: match activity text against known CRM contacts.
        if count == 0 and not contact_id_hint:
            contact = self._find_contact_from_payload_text(payload)
            if contact and self._associate(obj_type, obj_id, "contacts", contact["id"]):
                logger.info(
                    "[HubSpot] Auto-associated contact by text match: id=%s name=%s %s",
                    contact.get("id"),
                    contact.get("firstname", ""),
                    contact.get("lastname", ""),
                )
                count += 1

        # 4. Explicit related_entities {"contacts": ["123", "456"], "deals": "789"}
        related = payload.get("related_entities")
        if isinstance(related, dict):
            for raw_type, raw_ids in related.items():
                # HubSpot owner is a property (hubspot_owner_id), not an associated object.
                if str(raw_type).strip().lower() in {"owner", "owners", "hubspot_owner", "hubspot_owner_id"}:
                    continue
                to_type = self._normalize_object_type(str(raw_type))
                ids: List[str] = (
                    [str(raw_ids)]
                    if isinstance(raw_ids, (str, int))
                    else [str(i) for i in raw_ids if i]
                )
                for to_id in ids:
                    if not to_id:
                        continue

                    resolved_id = to_id
                    # If a contact/company name is passed instead of ID, resolve first.
                    if isinstance(raw_ids, str) and not str(to_id).strip().isdigit():
                        if to_type == "contacts":
                            found = self.find_contact(name=str(to_id).strip())
                            if found and found.get("id"):
                                resolved_id = str(found["id"])
                        elif to_type == "companies":
                            found = self.find_company(str(to_id).strip())
                            if found and found.get("id"):
                                resolved_id = str(found["id"])

                    if resolved_id and self._associate(obj_type, obj_id, to_type, resolved_id):
                        count += 1

        return count

    @staticmethod
    def _normalize_text_for_match(value: str) -> str:
        """Unicode-safe normalization for loose multilingual matching."""
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = text.casefold()
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _extract_participant_contact_hints(payload: Dict[str, Any]) -> List[Dict[str, str]]:
        """Extract participant name/email hints in a language-agnostic way."""
        participants = payload.get("participants")
        if not isinstance(participants, list):
            return []

        hints: List[Dict[str, str]] = []
        seen: set = set()

        for p in participants:
            email = ""
            name = ""

            if isinstance(p, dict):
                for key in ("email", "mail", "contact_email"):
                    val = p.get(key)
                    if isinstance(val, str) and val.strip():
                        email = val.strip()
                        break

                direct_name = p.get("name") or p.get("full_name") or p.get("display_name")
                if isinstance(direct_name, str) and direct_name.strip():
                    name = direct_name.strip()
                else:
                    first = str(p.get("first_name") or "").strip()
                    last = str(p.get("last_name") or "").strip()
                    name = " ".join(part for part in [first, last] if part).strip()

            elif isinstance(p, str):
                raw = p.strip()
                if not raw:
                    continue
                if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", raw):
                    email = raw
                else:
                    name = raw
            else:
                continue

            if not email and not name:
                continue

            dedupe_key = (email.casefold(), HubSpotDriver._normalize_text_for_match(name))
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            hints.append({"email": email, "name": name})

        return hints

    def _find_contact_from_payload_text(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Best-effort multilingual matching between meeting text and known contacts.
        This avoids language-specific keyword rules and works with any language
        where contact names appear in text.
        """
        title = str(payload.get("title") or "").strip()
        summary = str(payload.get("summary") or "").strip()
        participant_chunks: List[str] = []
        for hint in self._extract_participant_contact_hints(payload):
            if hint.get("name"):
                participant_chunks.append(str(hint["name"]))
            if hint.get("email"):
                participant_chunks.append(str(hint["email"]))

        raw_text = " ".join(part for part in [title, summary, *participant_chunks] if part).strip()
        if not raw_text:
            return None

        norm_text = self._normalize_text_for_match(raw_text)
        if not norm_text:
            return None

        try:
            limit = int(self.config.get("contact_text_match_limit", 200))
        except (TypeError, ValueError):
            limit = 200
        limit = max(20, min(limit, 500))

        try:
            contacts = self._search_objects(
                "contacts",
                properties=["firstname", "lastname", "email"],
                limit=limit,
            )
        except Exception as exc:
            logger.debug("[HubSpot] Contact text-match lookup skipped: %s", exc)
            return None

        for row in contacts:
            if not isinstance(row, dict):
                continue
            props = row.get("properties", {}) if isinstance(row.get("properties"), dict) else {}
            first = str(props.get("firstname") or "").strip()
            last = str(props.get("lastname") or "").strip()
            if not first and not last:
                continue

            full_name = " ".join(part for part in [first, last] if part).strip()
            if not full_name:
                continue

            # Try both spaced and compact variants for robust matching.
            variants = {
                self._normalize_text_for_match(full_name),
                self._normalize_text_for_match(full_name).replace(" ", ""),
            }
            haystack_variants = {norm_text, norm_text.replace(" ", "")}

            if any(v and any(v in h for h in haystack_variants) for v in variants):
                return {
                    "id": row.get("id"),
                    "firstname": first,
                    "lastname": last,
                    "email": props.get("email", ""),
                }

        return None

    # -------------------------------------------------------------------------
    # Activity property builder (replaces 4 old fragmented methods)
    # -------------------------------------------------------------------------

    def _build_activity_properties(
        self,
        obj_type: str,
        payload: Dict[str, Any],
        user_id: str = "",
    ) -> Dict[str, Any]:
        """
        Translate a generic Lia payload into HubSpot-native properties dict.
        Handles notes, tasks, meetings, calls, and emails.
        For unknown/custom types, passes through non-system fields as-is.
        """
        props: Dict[str, Any] = {}
        ot = self._normalize_object_type(obj_type)

        def _apply_owner_if_available() -> None:
            owner_id = self._resolve_owner_id(user_id, payload)
            if owner_id:
                props["hubspot_owner_id"] = owner_id

        if ot == "notes":
            body = payload.get("hs_note_body") or "\n".join(filter(None, [
                str(payload.get("title") or "").strip(),
                str(payload.get("summary") or "").strip(),
            ]))
            if body:
                props["hs_note_body"] = body
            props["hs_timestamp"] = self._ts_coerce(payload.get("timestamp")) or self._ts_now()
            _apply_owner_if_available()
            return props

        if ot == "tasks":
            if title := str(payload.get("title") or payload.get("hs_task_subject") or "").strip():
                props["hs_task_subject"] = title
            if body := str(payload.get("summary") or payload.get("hs_task_body") or "").strip():
                props["hs_task_body"] = body
            task_type = str(payload.get("hs_task_type") or "TODO").strip().upper()
            props["hs_task_type"] = task_type if task_type in _TASK_TYPES else "TODO"
            task_status = str(payload.get("hs_task_status") or "").strip().upper()
            if task_status in _TASK_STATUSES:
                props["hs_task_status"] = task_status
            props["hs_timestamp"] = self._ts_coerce(payload.get("timestamp")) or self._ts_now()
            _apply_owner_if_available()
            return props

        if ot == "meetings":
            title = str(payload.get("title") or payload.get("hs_meeting_title") or "Meeting").strip()
            props["hs_meeting_title"] = title

            if summary := str(payload.get("summary") or payload.get("hs_meeting_body") or "").strip():
                props["hs_meeting_body"] = summary

            start = (
                self._ts_coerce(payload.get("start_time"))
                or self._ts_coerce(payload.get("hs_meeting_start_time"))
                or self._ts_coerce(payload.get("timestamp"))
                or self._ts_now()
            )
            end = (
                self._ts_coerce(payload.get("end_time"))
                or self._ts_coerce(payload.get("hs_meeting_end_time"))
            )
            if not end:
                start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                end = (start_dt + timedelta(minutes=30)).isoformat().replace("+00:00", "Z")

            props["hs_timestamp"] = start
            props["hs_meeting_start_time"] = start
            props["hs_meeting_end_time"] = end

            outcome = str(
                payload.get("meeting_outcome") or payload.get("hs_meeting_outcome") or "SCHEDULED"
            ).strip().upper()
            props["hs_meeting_outcome"] = outcome if outcome in _MEETING_OUTCOMES else "SCHEDULED"

            if location := str(payload.get("location") or payload.get("hs_meeting_location") or "").strip():
                props["hs_meeting_location"] = location
            if url := str(payload.get("meeting_url") or payload.get("hs_meeting_external_url") or "").strip():
                props["hs_meeting_external_url"] = url

            _apply_owner_if_available()

            return props

        if ot == "calls":
            if title := str(payload.get("title") or payload.get("hs_call_title") or "").strip():
                props["hs_call_title"] = title
            if body := str(payload.get("summary") or payload.get("hs_call_body") or "").strip():
                props["hs_call_body"] = body
            duration = payload.get("duration_ms") or payload.get("hs_call_duration")
            if duration is not None:
                try:
                    props["hs_call_duration"] = int(duration)
                except (TypeError, ValueError):
                    pass
            props["hs_timestamp"] = self._ts_coerce(payload.get("timestamp")) or self._ts_now()
            _apply_owner_if_available()
            return props

        if ot == "emails":
            if subject := str(payload.get("title") or payload.get("hs_email_subject") or "").strip():
                props["hs_email_subject"] = subject
            if body := str(payload.get("summary") or payload.get("hs_email_text") or "").strip():
                props["hs_email_text"] = body
            props["hs_timestamp"] = self._ts_coerce(payload.get("timestamp")) or self._ts_now()
            _apply_owner_if_available()
            return props

        # Generic / custom objects: pass through non-system payload fields
        _skip = _READ_ONLY_PROPS | {
            "related_entities", "metadata",
            "contact_email", "contact_name", "company_name", "contact_id", "company_id",
        }
        for key, value in payload.items():
            if value is not None and key not in _skip:
                props[key] = value
        return props

    def _resolve_owner_id(self, user_id: str, payload: Dict[str, Any]) -> Optional[str]:
        """Resolve HubSpot owner ID: explicit payload > per-request context > CRM mapper."""
        related = payload.get("related_entities")
        related_owner = None
        if isinstance(related, dict):
            related_owner = related.get("owner") or related.get("owners")

        for candidate in (
            payload.get("hubspot_owner_id"),
            payload.get("owner_id"),
            related_owner,
            getattr(self, "request_owner_id", None),
        ):
            if candidate:
                value = str(candidate).strip()
                if not value:
                    continue
                # Accept values like "Q6" by extracting the numeric owner id.
                if not value.isdigit():
                    nums = re.findall(r"\d+", value)
                    if len(nums) == 1:
                        value = nums[0]
                # HubSpot owner IDs are numeric. If token is still non-numeric
                # (e.g. initials like "QC"), ignore and continue fallback chain.
                if not value.isdigit():
                    continue
                return value
        if user_id:
            try:
                from ..services.crm_mapper import CRMEntityMapper
                resolved = CRMEntityMapper().resolve_doctor_in_crm(user_id=user_id, crm_type="hubspot")
                if resolved:
                    return str(resolved).strip()
            except Exception:
                pass
        return None

    # -------------------------------------------------------------------------
    # Low-level object helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _extract_enum_values_from_error_response(error_text: str) -> Optional[List[str]]:
        """
        Extract valid enum values from HubSpot HTTP 400 error message.
        
        HubSpot returns something like:
        "Valid options are: pipelineId=default : [appointmentscheduled, qualifiedtobuy, ...]"
        
        Returns list of valid values, or None if no enum error detected.
        """
        # Look for pattern: "Valid options are: ... : [value1, value2, ...]"
        # This is more specific than just looking for any [...] to avoid matching JSON structures
        match = re.search(r'Valid options are:.*?:\s*\[([^\]]+)\]', error_text, re.IGNORECASE)
        if not match:
            return None
        
        enum_str = match.group(1)
        # Split by comma and quote marks, clean up
        # Handle both: "value1, value2" and "'value1', 'value2'"
        values = re.findall(r"'([^']+)'|\"([^\"]+)\"|([a-z0-9_]+)", enum_str, re.IGNORECASE)
        enum_values = []
        for match_tuple in values:
            # One of the groups will match
            val = match_tuple[0] or match_tuple[1] or match_tuple[2]
            if val.strip():
                enum_values.append(val.strip().lower())
        
        return enum_values if enum_values else None

    @staticmethod
    def _find_closest_enum_match(attempted_value: str, valid_options: List[str], cutoff: float = 0.6) -> Optional[str]:
        """
        Use string similarity to find the closest valid enum value.
        
        Example: attempted_value="scheduled" + valid_options=["appointmentscheduled", "closedwon"]
        Returns: "appointmentscheduled" (best match above cutoff)
        """
        from difflib import SequenceMatcher
        
        attempted = str(attempted_value).strip().lower()
        if not attempted or not valid_options:
            return None
        
        best_match = None
        best_ratio = cutoff
        
        for option in valid_options:
            option_lower = str(option).strip().lower()
            ratio = SequenceMatcher(None, attempted, option_lower).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = option_lower
        
        return best_match

    def _create_object(self, obj_type: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        resp = self._request("POST", f"/crm/v3/objects/{obj_type}", json={"properties": properties})
        return resp.json()

    def _patch_object(self, obj_type: str, obj_id: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        resp = self._request(
            "PATCH", f"/crm/v3/objects/{obj_type}/{obj_id}", json={"properties": properties}
        )
        return resp.json()

    def _delete_object(self, obj_type: str, obj_id: str) -> bool:
        resp = self._request("DELETE", f"/crm/v3/objects/{obj_type}/{obj_id}")
        return resp.status_code == 204

    def _search_objects(
        self,
        obj_type: str,
        properties: Optional[List[str]] = None,
        filters: Optional[List[Dict[str, Any]]] = None,
        sort_property: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        body: Dict[str, Any] = {"limit": limit}
        if properties:
            body["properties"] = properties
        if filters:
            body["filterGroups"] = [{"filters": filters}]
        if sort_property:
            body["sorts"] = [{"propertyName": sort_property, "direction": "DESCENDING"}]
        resp = self._request("POST", f"/crm/v3/objects/{obj_type}/search", json=body)
        return resp.json().get("results", [])

    @staticmethod
    def _extract_enum_values_from_properties(properties: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """
        Extract all enum values from a list of HubSpot property definitions.
        
        HubSpot returns properties with type="enumeration" and enumValues list:
        [{"label": "Appointment Scheduled", "value": "appointmentscheduled"}, ...]
        
        Returns:
            {"dealstage": ["appointmentscheduled", "qualifiedtobuy", ...], ...}
        """
        enum_map: Dict[str, List[str]] = {}
        for prop in properties:
            if not isinstance(prop, dict) or prop.get("type") != "enumeration":
                continue
            prop_name = prop.get("name")
            if not prop_name:
                continue
            enum_values = []
            for ev in prop.get("enumValues") or []:
                if isinstance(ev, dict) and "value" in ev:
                    enum_values.append(str(ev["value"]).strip())
            if enum_values:
                enum_map[prop_name] = enum_values
        return enum_map

    @staticmethod
    def _to_epoch_millis(value: Any) -> Optional[int]:
        """Convert numeric or ISO datetime/date value to epoch milliseconds."""
        if isinstance(value, bool):
            return None

        if isinstance(value, (int, float)):
            iv = int(value)
            # If seconds precision is passed, up-convert to ms.
            if 0 < iv < 10_000_000_000:
                return iv * 1000
            return iv

        if not isinstance(value, str):
            return None

        txt = value.strip()
        if not txt:
            return None

        # Plain numeric string (seconds or milliseconds)
        if re.fullmatch(r"\d{10,16}", txt):
            iv = int(txt)
            if len(txt) <= 10:
                return iv * 1000
            return iv

        # Accept common ISO forms and treat naive timestamps as UTC.
        try:
            iso = txt.replace("Z", "+00:00")
            dt = datetime.fromisoformat(iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except Exception:
            return None

    @staticmethod
    def _normalize_property_types(
        properties: Dict[str, Any],
        column_types: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Normalize property types to match HubSpot API requirements.
        
        - hubspot_owner_id: string → integer
        - amount: string/float → float
        - date/datetime fields: ISO/numeric → epoch milliseconds (long)
        
        Returns normalized properties dict.
        """
        normalized = dict(properties)
        normalized_types = {
            str(k): str(v).strip().lower()
            for k, v in (column_types or {}).items()
            if isinstance(k, str) and isinstance(v, str) and str(v).strip()
        }
        
        # Owner ID must be integer for HubSpot
        if "hubspot_owner_id" in normalized:
            try:
                val = normalized["hubspot_owner_id"]
                if isinstance(val, str) and val.strip():
                    normalized["hubspot_owner_id"] = int(val.strip())
                elif isinstance(val, (int, float)):
                    normalized["hubspot_owner_id"] = int(val)
            except (ValueError, TypeError) as e:
                logger.warning(
                    "[HubSpot] Failed to convert hubspot_owner_id to integer: %s (keeping original)",
                    e
                )
        
        # Amount should be numeric (float)
        if "amount" in normalized:
            try:
                val = normalized["amount"]
                if isinstance(val, str) and val.strip():
                    normalized["amount"] = float(val.strip())
                elif isinstance(val, int):
                    normalized["amount"] = float(val)
            except (ValueError, TypeError) as e:
                logger.warning("[HubSpot] Failed to convert amount to float: %s (keeping original)", e)

        # Generic conversion for HubSpot date/datetime fields that require long values.
        for prop_name, prop_value in list(normalized.items()):
            prop_type = normalized_types.get(prop_name)
            if prop_type not in {"date", "datetime"}:
                continue
            epoch_ms = HubSpotDriver._to_epoch_millis(prop_value)
            if epoch_ms is not None:
                normalized[prop_name] = epoch_ms
            else:
                logger.warning(
                    "[HubSpot] Failed to convert %s (type=%s) to epoch ms; keeping original value",
                    prop_name,
                    prop_type,
                )
        
        return normalized

    @staticmethod
    def _collect_mapped_properties(
        payload: Dict[str, Any],
        col_map: Dict[str, str],
        table_cols: set,
    ) -> Dict[str, Any]:
        """
        Build {hubspot_property: value} from a normalized payload using the
        schema column mapping. Skips read-only system fields and internal keys.
        """
        _skip = _READ_ONLY_PROPS | {
            "related_entities", "metadata",
            "contact_email", "contact_name", "company_name", "contact_id", "company_id",
        }
        props: Dict[str, Any] = {}
        for norm_field, hs_field in col_map.items():
            if not isinstance(hs_field, str) or hs_field in _READ_ONLY_PROPS:
                continue
            if (value := payload.get(norm_field)) is not None:
                props[hs_field] = value
        for key, value in payload.items():
            if value is not None and key not in _skip and key in table_cols:
                props[key] = value

        # Fallback: schema-driven alias matching (e.g. close_date -> closedate,
        # deal_stage -> dealstage, closeDate -> closedate).
        def _canon(text: str) -> str:
            return re.sub(r"[^a-z0-9]", "", str(text).strip().lower())

        canonical_cols: Dict[str, List[str]] = {}
        for col in table_cols:
            canonical_cols.setdefault(_canon(str(col)), []).append(str(col))

        for key, value in payload.items():
            if value is None or key in _skip or key in props:
                continue

            canon_key = _canon(key)
            if not canon_key:
                continue

            candidates = canonical_cols.get(canon_key, [])
            if len(candidates) == 1:
                props[candidates[0]] = value
                continue

            # Soft heuristic for common CRM naming differences.
            if canon_key == "stage":
                if "dealstage" in table_cols:
                    props["dealstage"] = value
                    continue
                stage_candidates = [c for c in table_cols if _canon(c).endswith("stage")]
                if len(stage_candidates) == 1:
                    props[str(stage_candidates[0])] = value

        return props

    # -------------------------------------------------------------------------
    # BaseDriver: legacy meeting interface (sync)
    # -------------------------------------------------------------------------

    def save_meeting(self, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a HubSpot Meeting and link it to the relevant contacts/companies.

        Full flow logged for Lia audit trail:
            [HubSpot] save_meeting -> user=... title=...
            [HubSpot] Meeting created -> id=...
            [HubSpot] Searching contact by email: ...
            [HubSpot] Contact found -> id=...
            [HubSpot] Associating meetings/... -> contacts/...
            [HubSpot] Association OK: meetings/... -> contacts/...
            [HubSpot] Meeting associations created: 1
        """
        logger.info("[HubSpot] save_meeting -> user=%s title=%s", user_id, payload.get("title"))
        try:
            props = self._build_activity_properties("meetings", payload, user_id=user_id)
            props = self._normalize_property_types(
                props,
                {
                    "hs_timestamp": "datetime",
                    "hs_meeting_start_time": "datetime",
                    "hs_meeting_end_time": "datetime",
                    "hubspot_owner_id": "number",
                },
            )
            result = self._create_object("meetings", props)
            meeting_id = result["id"]
            logger.info("[HubSpot] Meeting created -> id=%s", meeting_id)

            linked = self._resolve_and_associate("meetings", meeting_id, payload)
            logger.info("[HubSpot] Meeting associations created: %d", linked)

            associated_contact_ids = self._list_association_ids("meetings", meeting_id, "contacts")
            associated_company_ids = self._list_association_ids("meetings", meeting_id, "companies")

            return {
                "id": meeting_id,
                "title": props.get("hs_meeting_title") or payload.get("title"),
                "summary": props.get("hs_meeting_body") or payload.get("summary"),
                "linked_associations": linked,
                "associated_contact_ids": associated_contact_ids,
                "associated_company_ids": associated_company_ids,
                "visibility_hint": (
                    None
                    if associated_contact_ids or associated_company_ids
                    else (
                        "Meeting created with no CRM associations — it will not appear "
                        "in any contact or company timeline until linked."
                    )
                ),
                "source": "hubspot",
            }
        except requests.exceptions.RequestException as err:
            resp = getattr(err, "response", None)
            detail = (
                f"HTTP {resp.status_code}: {(resp.text or '').strip()[:400]}"
                if resp else str(err)
            )
            raise Exception(f"Failed to save meeting to HubSpot: {detail}") from err

    def get_meeting_history(
        self,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Return recent HubSpot Meetings for the given user, newest first."""
        try:
            limit = int((filters or {}).get("limit", 20))
            results = self._search_objects(
                "meetings",
                properties=[
                    "hs_meeting_title", "hs_meeting_body", "hs_timestamp",
                    "hs_meeting_start_time", "hs_meeting_end_time",
                    "hs_meeting_outcome", "hubspot_owner_id", "hs_createdate",
                ],
                sort_property="hs_timestamp",
                limit=limit,
            )

            owned_ids = {str(i) for i in (filters or {}).get("owned_entity_ids", [])}
            if owned_ids:
                results = [r for r in results if str(r.get("id")) in owned_ids]

            meetings = []
            for r in results:
                p = r.get("properties", {})
                meetings.append({
                    "id": r["id"],
                    "title": p.get("hs_meeting_title") or "",
                    "summary": p.get("hs_meeting_body") or "",
                    "metadata": {
                        "hubspot_id": r["id"],
                        "hs_meeting_outcome": p.get("hs_meeting_outcome"),
                        "hubspot_owner_id": p.get("hubspot_owner_id"),
                    },
                    "created_at": p.get("hs_timestamp") or p.get("hs_createdate"),
                    "source": "hubspot",
                })
            return meetings
        except requests.exceptions.RequestException as err:
            raise Exception(f"Failed to fetch meeting history from HubSpot: {err}") from err

    def prepare_meeting_history_filters(
        self,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
        owned_entity_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        scoped = dict(filters or {})
        restrict = bool(scoped.get(
            "restrict_to_owned_entities",
            self.config.get("restrict_to_owned_entities", False),
        ))
        if restrict and owned_entity_ids:
            scoped["owned_entity_ids"] = [str(i) for i in owned_entity_ids]
        return scoped

    # -------------------------------------------------------------------------
    # BaseDriver: generic CRUD (async)
    # -------------------------------------------------------------------------

    async def get_schema_info(self) -> Dict[str, Any]:
        """
        Introspect HubSpot schema: custom objects from /crm/v3/schemas plus
        all 12 standard objects. Also extract enum values for all fields.
        
        Returns:
            {"tables": [{"name": "deals", "columns": [...], "column_types": {...}, 
                         "enum_values": {"dealstage": [...], ...}}, ...]}
        """
        try:
            resp = self._request("GET", "/crm/v3/schemas")
            schemas = resp.json().get("results", [])
            tables = []
            for s in schemas:
                props = s.get("properties", [])
                table_entry = {
                    "name": s.get("fullyQualifiedName") or s.get("name"),
                    "columns": [p["name"] for p in props if p.get("name")],
                    "column_types": {p["name"]: p.get("type") for p in props if p.get("name")},
                }
                enum_vals = self._extract_enum_values_from_properties(props)
                if enum_vals:
                    table_entry["enum_values"] = enum_vals
                tables.append(table_entry)
            
            standard_objects = [
                "contacts", "companies", "deals", "tickets", "calls",
                "emails", "meetings", "notes", "tasks", "products", "line_items", "quotes",
            ]
            for obj in standard_objects:
                try:
                    pr = self._request("GET", f"/crm/v3/properties/{obj}")
                    props = [
                        p for p in pr.json().get("results", [])
                        if isinstance(p, dict) and p.get("name")
                    ]
                    table_entry = {
                        "name": obj,
                        "columns": [p["name"] for p in props],
                        "column_types": {p["name"]: p.get("type") for p in props},
                    }
                    enum_vals = self._extract_enum_values_from_properties(props)
                    if enum_vals:
                        table_entry["enum_values"] = enum_vals
                    tables.append(table_entry)
                except Exception:
                    continue     # best-effort; keep partial results
            logger.info("[HubSpot] Schema introspected: %d objects", len(tables))
            return {"tables": tables}
        except Exception as err:
            logger.error("[HubSpot] Schema introspection failed: %s", err)
            raise

    async def create_entity(self, entity_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create a record of any entity type in HubSpot.."""
        mapping = get_entity_mapping(self.config, entity_type)
        obj_type = self._normalize_object_type(mapping.get("table_name") or entity_type)
        logger.info("[HubSpot] create_entity type=%s obj_type=%s", entity_type, obj_type)

        if obj_type in _ACTIVITY_TYPES:
            props = self._build_activity_properties(obj_type, payload)
        else:
            col_map = mapping.get("column_mapping", {})
            table_cols = set(mapping.get("table_columns") or [])
            props = self._collect_mapped_properties(payload, col_map, table_cols)

            owner_id = self._resolve_owner_id("", payload)
            if owner_id and "hubspot_owner_id" not in props:
                props["hubspot_owner_id"] = owner_id

        # Normalize property types (e.g., convert owner_id to integer)
        props = self._normalize_property_types(props, mapping.get("column_types"))

        # Try to create object; on enum validation error, attempt fuzzy matching + retry
        try:
            result = self._create_object(obj_type, props)
        except requests.exceptions.HTTPError as err:
            resp = getattr(err, "response", None)
            if resp is not None and resp.status_code == 400:
                error_text = resp.text or ""
                logger.warning("[HubSpot] HTTP 400 during create_entity: %s", error_text[:300])
                
                # Try to extract valid enum values and do fuzzy matching
                valid_enums = self._extract_enum_values_from_error_response(error_text)
                if valid_enums:
                    logger.info("[HubSpot] Detected enum validation error. Valid options: %s", valid_enums)
                    
                    # Try to fuzzy-match props values against valid enums
                    props_modified = False
                    for prop_name, prop_value in list(props.items()):
                        if isinstance(prop_value, str):
                            best_match = self._find_closest_enum_match(prop_value, valid_enums, cutoff=0.5)
                            if best_match and best_match != str(prop_value).strip().lower():
                                logger.info(
                                    "[HubSpot] Fuzzy-matched enum: %s='%s' -> '%s'",
                                    prop_name, prop_value, best_match
                                )
                                props[prop_name] = best_match
                                props_modified = True
                    
                    if props_modified:
                        logger.info("[HubSpot] Retrying create_entity with corrected enum values")
                        try:
                            result = self._create_object(obj_type, props)
                        except Exception as retry_err:
                            logger.error("[HubSpot] Retry failed: %s", retry_err)
                            raise err  # Raise original error if retry fails
                    else:
                        logger.warning("[HubSpot] Enum validation error detected but no props could be fuzzy-matched")
                        raise err
                else:
                    logger.debug("[HubSpot] HTTP 400 error but no enum validation detected (no 'Valid options' pattern found)")
                    raise err
            else:
                raise
        
        obj_id = result["id"]
        logger.info("[HubSpot] Object created -> %s/%s", obj_type, obj_id)

        linked = self._resolve_and_associate(obj_type, obj_id, payload)
        col_map = mapping.get("column_mapping", {})
        associated_contact_ids = self._list_association_ids(obj_type, obj_id, "contacts")
        associated_company_ids = self._list_association_ids(obj_type, obj_id, "companies")
        visibility_hint = None
        if obj_type in _ACTIVITY_TYPES and not (associated_contact_ids or associated_company_ids):
            visibility_hint = (
                "Activity created but not linked to a contact/company. "
                "It may not appear in the client Activities timeline until associated."
            )
        return {
            "id": obj_id,
            "linked_associations": linked,
            "associated_contact_ids": associated_contact_ids,
            "associated_company_ids": associated_company_ids,
            "visibility_hint": visibility_hint,
            "source": "hubspot",
            **{k: self._get_prop_value(result.get("properties", {}), v) for k, v in col_map.items()},
        }

    async def read_entities(
        self,
        entity_type: str,
        user_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        mapping = get_entity_mapping(self.config, entity_type)
        obj_type = self._normalize_object_type(mapping.get("table_name") or entity_type)
        col_map = mapping.get("column_mapping", {})
        sort_col = col_map.get("created_at")

        wanted_props = sorted({
            prop
            for v in col_map.values()
            for prop in ([v] if isinstance(v, str) else (v if isinstance(v, list) else []))
            if isinstance(prop, str) and prop.strip()
        } | set(mapping.get("table_columns") or []))

        limit = int((filters or {}).get("limit", 20))
        results = self._search_objects(
            obj_type,
            properties=wanted_props or None,
            sort_property=sort_col,
            limit=limit,
        )

        owned_ids = {str(i) for i in (filters or {}).get("owned_entity_ids", [])}
        if owned_ids:
            results = [r for r in results if str(r.get("id")) in owned_ids]

        return [
            {
                "id": r["id"],
                "source": "hubspot",
                **{k: self._get_prop_value(r.get("properties", {}), v) for k, v in col_map.items()},
            }
            for r in results
        ]

    async def update_entity(
        self,
        entity_type: str,
        entity_id: str,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        mapping = get_entity_mapping(self.config, entity_type)
        obj_type = self._normalize_object_type(mapping.get("table_name") or entity_type)

        if obj_type in _ACTIVITY_TYPES:
            props = self._build_activity_properties(obj_type, updates)
        else:
            col_map = mapping.get("column_mapping", {})
            table_cols = set(mapping.get("table_columns") or [])
            props = self._collect_mapped_properties(updates, col_map, table_cols)

            owner_id = self._resolve_owner_id("", updates)
            if owner_id and "hubspot_owner_id" not in props:
                props["hubspot_owner_id"] = owner_id

        # Normalize property types (e.g., convert owner_id to integer)
        props = self._normalize_property_types(props, mapping.get("column_types"))

        has_association_hints = any(
            updates.get(key) is not None
            for key in ("related_entities", "contact_id", "contact_email", "contact_name", "company_id", "company_name")
        )

        result: Dict[str, Any]
        if props:
            result = self._patch_object(obj_type, entity_id, props)
        elif has_association_hints:
            # Association-only update: skip PATCH and still process relationships.
            result = {"id": entity_id, "properties": {}}
        else:
            raise ValueError(f"No writable HubSpot properties found in payload for {entity_type}")

        # Allow relationship linking during updates when caller provides
        # related_entities/contact/company hints (useful for already-created meetings).
        linked = 0
        try:
            linked = self._resolve_and_associate(obj_type, str(entity_id), updates)
        except Exception as exc:
            logger.warning("[HubSpot] Post-update association step failed for %s/%s: %s", obj_type, entity_id, exc)

        col_map = mapping.get("column_mapping", {})
        return {
            "id": result.get("id"),
            "source": "hubspot",
            "linked_associations": linked,
            **{k: self._get_prop_value(result.get("properties", {}), v) for k, v in col_map.items()},
        }

    async def delete_entity(self, entity_type: str, entity_id: str) -> bool:
        mapping = get_entity_mapping(self.config, entity_type)
        obj_type = self._normalize_object_type(mapping.get("table_name") or entity_type)
        return self._delete_object(obj_type, entity_id)
