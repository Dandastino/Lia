"""HubSpot driver: all HTTP traffic is mocked with ``responses``."""
from __future__ import annotations

import logging
import sys
import types
from datetime import UTC, datetime

import pytest
import requests
import responses

from app.drivers.hubspot_driver import HubSpotDriver

from .helpers import calls_matching, json_body

HS = "https://api.hubapi.com"

MAPPINGS = {
    "contact": {
        "table_name": "contacts",
        "column_mapping": {
            "first_name": "firstname",
            "last_name": "lastname",
            "email": "email",
            "full_name": ["firstname", "lastname"],
            "created_at": "createdate",
        },
        "table_columns": ["firstname", "lastname", "email", "phone", "hubspot_owner_id", "createdate"],
    },
    "deal": {
        "table_name": "deals",
        "column_mapping": {"deal_name": "dealname", "stage": "dealstage", "amount": "amount"},
        "table_columns": ["dealname", "dealstage", "amount", "closedate", "hubspot_owner_id"],
        "column_types": {"closedate": "date", "amount": "number"},
    },
    "meeting": {
        "table_name": "meetings",
        "column_mapping": {"title": "hs_meeting_title", "summary": "hs_meeting_body"},
    },
    "note": {"table_name": "notes", "column_mapping": {"body": "hs_note_body"}},
    "company": {"table_name": "companies"},
    "customer": {"column_mapping": {"email": "email"}},
}


def make_driver(**overrides):
    config = {"api_key": "pat-secret", "schema_mappings": MAPPINGS}
    config.update(overrides)
    return HubSpotDriver(config)


@pytest.fixture
def driver():
    return make_driver()


def epoch_ms(*args):
    return int(datetime(*args, tzinfo=UTC).timestamp() * 1000)


# ------------------------------------------------------------ construction/HTTP
class TestConstructionAndHttp:
    def test_requires_api_key(self):
        with pytest.raises(ValueError, match="api_key"):
            HubSpotDriver({})
        with pytest.raises(ValueError, match="api_key"):
            HubSpotDriver(None)
        with pytest.raises(ValueError, match="api_key"):
            HubSpotDriver({"api_key": ""})

    def test_defaults(self, driver):
        assert driver._base_url == HS
        assert driver._verify_ssl is True
        assert driver._timeout == 20.0

    @pytest.mark.parametrize("raw,expected", [(5, 5.0), ("abc", 20.0), (None, 20.0), (0, 1.0), (-4, 1.0), ("2.5", 2.5)])
    def test_timeout_config(self, raw, expected):
        assert make_driver(request_timeout_seconds=raw)._timeout == expected

    def test_verify_ssl_disabled_warns(self, caplog):
        with caplog.at_level(logging.WARNING, logger="hubspot_driver"):
            drv = make_driver(verify_ssl=False)
        assert drv._verify_ssl is False
        assert "SSL verification disabled" in caplog.text

    def test_request_headers_timeout_verify(self, rsps):
        drv = make_driver(request_timeout_seconds=9, verify_ssl=False)
        rsps.add(responses.GET, f"{HS}/ping", json={})
        drv._request("get", "/ping")
        call = rsps.calls[0]
        assert call.request.headers["Authorization"] == "Bearer pat-secret"
        assert call.request.headers["Content-Type"] == "application/json"
        assert call.request.req_kwargs["timeout"] == 9.0
        assert call.request.req_kwargs["verify"] is False

    def test_absolute_url(self, driver, rsps):
        rsps.add(responses.GET, "https://api.hubapi.com/abs", json={})
        driver._request("GET", "https://api.hubapi.com/abs")
        assert rsps.calls[0].request.url == "https://api.hubapi.com/abs"

    @pytest.mark.parametrize("status", [400, 401, 404, 429, 500])
    def test_http_errors_raise_without_retry(self, driver, rsps, status):
        rsps.add(responses.GET, f"{HS}/ping", status=status, body="nope")
        with pytest.raises(requests.exceptions.HTTPError) as info:
            driver._request("GET", "/ping")
        assert info.value.response.status_code == status
        assert len(rsps.calls) == 1  # API-key auth: there is no token refresh to retry with

    def test_http_error_is_logged_with_detail(self, driver, rsps, caplog):
        rsps.add(responses.GET, f"{HS}/ping", status=400, body="bad things")
        with caplog.at_level(logging.WARNING, logger="hubspot_driver"):
            with pytest.raises(requests.exceptions.HTTPError):
                driver._request("GET", "/ping")
        assert "HTTP 400: bad things" in caplog.text

    def test_timeout_and_connection_errors_propagate(self, driver, rsps):
        rsps.add(responses.GET, f"{HS}/slow", body=requests.exceptions.ReadTimeout("slow"))
        rsps.add(responses.GET, f"{HS}/down", body=requests.exceptions.ConnectionError("down"))
        with pytest.raises(requests.exceptions.ReadTimeout):
            driver._request("GET", "/slow")
        with pytest.raises(requests.exceptions.ConnectionError):
            driver._request("GET", "/down")

    def test_unregistered_url_never_reaches_network(self, driver, rsps):
        with pytest.raises(requests.exceptions.ConnectionError):
            driver._request("GET", "/not-mocked")


# ----------------------------------------------------------------- timestamps
class TestTimestamps:
    def test_ts_now_is_rfc3339_utc(self):
        now = HubSpotDriver._ts_now()
        assert now.endswith("Z")
        assert datetime.fromisoformat(now.replace("Z", "+00:00")).tzinfo is not None

    @pytest.mark.parametrize(
        "value,expected",
        [
            (None, None),
            (1700000000, "2023-11-14T22:13:20Z"),
            (1700000000000, "2023-11-14T22:13:20Z"),
            (1700000000.5, "2023-11-14T22:13:20.500000Z"),
            ("1700000000", "2023-11-14T22:13:20Z"),
            ("1700000000000", "2023-11-14T22:13:20Z"),
            ("  1700000000  ", "2023-11-14T22:13:20Z"),
            ("2024-01-01T12:00:00Z", "2024-01-01T12:00:00Z"),
            ("2024-01-01T12:00:00+02:00", "2024-01-01T10:00:00Z"),
            ("2024-01-01T12:00:00", "2024-01-01T12:00:00Z"),
            ("2024-01-01", "2024-01-01T00:00:00Z"),
            ("", None),
            ("   ", None),
            ("not a date", None),
            ([], None),
            ({}, None),
        ],
    )
    def test_ts_coerce(self, value, expected):
        assert HubSpotDriver._ts_coerce(value) == expected

    def test_ts_coerce_datetime(self):
        assert HubSpotDriver._ts_coerce(datetime(2024, 1, 1, 12)) == "2024-01-01T12:00:00Z"
        from datetime import timedelta, timezone

        aware = datetime(2024, 1, 1, 12, tzinfo=timezone(timedelta(hours=2)))
        assert HubSpotDriver._ts_coerce(aware) == "2024-01-01T10:00:00Z"

    @pytest.mark.parametrize(
        "value,expected",
        [
            (True, None),
            (False, None),
            (1700000000, 1700000000000),
            (1700000000000, 1700000000000),
            (0, 0),
            (1700000000.0, 1700000000000),
            ("1700000000", 1700000000000),
            ("1700000000000", 1700000000000),
            ("2024-01-01T10:00:00Z", epoch_ms(2024, 1, 1, 10)),
            ("2024-01-01T10:00:00", epoch_ms(2024, 1, 1, 10)),
            ("2024-01-01", epoch_ms(2024, 1, 1)),
            ("garbage", None),
            ("", None),
            ("   ", None),
            (None, None),
            ([], None),
        ],
    )
    def test_to_epoch_millis(self, value, expected):
        assert HubSpotDriver._to_epoch_millis(value) == expected


# ------------------------------------------------- property normalisation
class TestNormalizePropertyTypes:
    def test_owner_id_becomes_int(self):
        assert HubSpotDriver._normalize_property_types({"hubspot_owner_id": " 12 "}) == {"hubspot_owner_id": 12}
        assert HubSpotDriver._normalize_property_types({"hubspot_owner_id": 12.0}) == {"hubspot_owner_id": 12}
        assert HubSpotDriver._normalize_property_types({"hubspot_owner_id": 7}) == {"hubspot_owner_id": 7}

    def test_owner_id_invalid_is_kept(self, caplog):
        with caplog.at_level(logging.WARNING, logger="hubspot_driver"):
            out = HubSpotDriver._normalize_property_types({"hubspot_owner_id": "abc"})
        assert out == {"hubspot_owner_id": "abc"}
        assert "hubspot_owner_id" in caplog.text

    def test_owner_id_blank_untouched(self):
        assert HubSpotDriver._normalize_property_types({"hubspot_owner_id": "  "}) == {"hubspot_owner_id": "  "}

    def test_amount_becomes_float(self):
        assert HubSpotDriver._normalize_property_types({"amount": "12.5"}) == {"amount": 12.5}
        assert HubSpotDriver._normalize_property_types({"amount": 3}) == {"amount": 3.0}
        assert HubSpotDriver._normalize_property_types({"amount": 3.5}) == {"amount": 3.5}
        assert HubSpotDriver._normalize_property_types({"amount": "  "}) == {"amount": "  "}

    def test_amount_invalid_is_kept(self):
        assert HubSpotDriver._normalize_property_types({"amount": "1,2k"}) == {"amount": "1,2k"}

    def test_date_columns_are_converted_to_epoch_ms(self):
        out = HubSpotDriver._normalize_property_types(
            {"closedate": "2024-01-31", "other": "2024-01-31", "when": "2024-01-01T10:00:00Z", "bad": "nope"},
            {"closedate": "date", "when": "DateTime", "bad": "date", "other": "string", 5: "date", "x": None},
        )
        assert out["closedate"] == epoch_ms(2024, 1, 31)
        assert out["when"] == epoch_ms(2024, 1, 1, 10)
        assert out["other"] == "2024-01-31"
        assert out["bad"] == "nope"  # unparsable values are left for HubSpot to reject

    def test_input_is_not_mutated(self):
        props = {"amount": "1"}
        HubSpotDriver._normalize_property_types(props)
        assert props == {"amount": "1"}


# ------------------------------------------------------ small pure helpers
class TestPureHelpers:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("contact", "contacts"), ("Contacts", "contacts"), ("  DEAL ", "deals"), ("client", "contacts"),
            ("customers", "contacts"), ("company", "companies"), ("meeting_id", "meetings"), ("line_item", "line_items"),
            ("ticket", "tickets"), ("call", "calls"), ("email", "emails"), ("note", "notes"), ("task", "tasks"),
            ("product", "products"), ("quote", "quotes"), ("2-12345", "2-12345"), ("custom_obj", "custom_obj"),
        ],
    )
    def test_normalize_object_type(self, raw, expected):
        assert HubSpotDriver._normalize_object_type(raw) == expected

    def test_get_prop_value(self):
        props = {"firstname": "Ada", "lastname": " Lovelace ", "empty": "", "none": None}
        assert HubSpotDriver._get_prop_value(props, "firstname") == "Ada"
        assert HubSpotDriver._get_prop_value(props, "missing") is None
        assert HubSpotDriver._get_prop_value(props, ["firstname", "lastname"]) == "Ada Lovelace"
        assert HubSpotDriver._get_prop_value(props, ["empty", "none", "firstname", 5, " "]) == "Ada"
        assert HubSpotDriver._get_prop_value(props, ["empty", "none"]) is None

    @pytest.mark.parametrize(
        "value,expected",
        [("José  GARCÍA", "jose garcia"), ("  A\tB\n", "a b"), (None, ""), ("", ""), ("Straße", "strasse")],
    )
    def test_normalize_text_for_match(self, value, expected):
        assert HubSpotDriver._normalize_text_for_match(value) == expected

    def test_extract_enum_values_from_error_response(self):
        text = "Property values were not valid. Valid options are: pipelineId=default : [appointmentscheduled, qualifiedtobuy, ClosedWon]"
        assert HubSpotDriver._extract_enum_values_from_error_response(text) == [
            "appointmentscheduled", "qualifiedtobuy", "closedwon",
        ]
        quoted = "valid OPTIONS are: stage : ['in progress', \"done\", plain]"
        assert HubSpotDriver._extract_enum_values_from_error_response(quoted) == ["in progress", "done", "plain"]

    @pytest.mark.parametrize("text", ["", "something [a, b] went wrong", "Valid options are: x : [ ]", "no pattern"])
    def test_extract_enum_values_none(self, text):
        assert HubSpotDriver._extract_enum_values_from_error_response(text) is None

    def test_find_closest_enum_match(self):
        options = ["appointmentscheduled", "qualifiedtobuy", "closedwon"]
        assert HubSpotDriver._find_closest_enum_match("scheduled", options) == "appointmentscheduled"
        assert HubSpotDriver._find_closest_enum_match("ClosedWon", options) == "closedwon"
        assert HubSpotDriver._find_closest_enum_match("zzzz", options) is None
        assert HubSpotDriver._find_closest_enum_match("", options) is None
        assert HubSpotDriver._find_closest_enum_match("x", []) is None
        assert HubSpotDriver._find_closest_enum_match("scheduled", options, cutoff=0.95) is None

    def test_extract_enum_values_from_properties(self):
        props = [
            {"name": "dealstage", "type": "enumeration",
             "enumValues": [{"value": " a "}, {"value": "b"}, {"label": "no value"}, "junk"]},
            {"name": "plain", "type": "string"},
            {"name": "empty", "type": "enumeration", "enumValues": []},
            {"name": "none", "type": "enumeration", "enumValues": None},
            {"type": "enumeration", "enumValues": [{"value": "x"}]},
            "not a dict",
        ]
        assert HubSpotDriver._extract_enum_values_from_properties(props) == {"dealstage": ["a", "b"]}

    def test_collect_mapped_properties(self):
        props = HubSpotDriver._collect_mapped_properties(
            {
                "first_name": "Ada",
                "email": None,
                "phone": "1",
                "hs_object_id": "9",
                "hs_createdate": "x",
                "metadata": {"m": 1},
                "contact_email": "a@b.c",
                "unknown": "dropped",
            },
            {"first_name": "firstname", "email": "email", "created": "hs_createdate", "bad": ["x"]},
            {"phone", "hs_object_id", "metadata", "contact_email"},
        )
        assert props == {"firstname": "Ada", "phone": "1"}

    def test_collect_mapped_properties_alias_matching(self):
        cols = {"closedate", "dealstage", "dealname"}
        props = HubSpotDriver._collect_mapped_properties(
            {"close_date": "2024-01-01", "stage": "won", "Deal Name": "X", "???": "skip", "nothing": 1},
            {},
            cols,
        )
        assert props == {"closedate": "2024-01-01", "dealstage": "won", "dealname": "X"}

    def test_collect_mapped_properties_stage_heuristics(self):
        single = HubSpotDriver._collect_mapped_properties({"stage": "x"}, {}, {"pipeline_stage", "name"})
        assert single == {"pipeline_stage": "x"}
        ambiguous = HubSpotDriver._collect_mapped_properties({"stage": "x"}, {}, {"a_stage", "b_stage"})
        assert ambiguous == {}

    def test_collect_mapped_properties_ambiguous_alias_is_dropped(self):
        props = HubSpotDriver._collect_mapped_properties({"closedate": "1"}, {}, {"close_date", "closeDate"})
        assert props == {}

    def test_extract_participant_contact_hints(self):
        hints = HubSpotDriver._extract_participant_contact_hints({"participants": [
            {"email": " a@b.c ", "name": " Ada "},
            {"mail": "m@x.y", "first_name": "Grace", "last_name": "Hopper"},
            {"contact_email": "c@x.y", "full_name": "Cee"},
            {"display_name": "Disp"},
            {"first_name": "Solo"},
            {"email": 5, "name": 5},
            {},
            "plain@mail.com",
            "Bob Builder",
            "   ",
            "bob builder",
            "PLAIN@mail.com",
            42,
            None,
        ]})
        assert hints == [
            {"email": "a@b.c", "name": "Ada"},
            {"email": "m@x.y", "name": "Grace Hopper"},
            {"email": "c@x.y", "name": "Cee"},
            {"email": "", "name": "Disp"},
            {"email": "", "name": "Solo"},
            {"email": "plain@mail.com", "name": ""},
            {"email": "", "name": "Bob Builder"},
        ]

    def test_extract_participant_hints_non_list(self):
        assert HubSpotDriver._extract_participant_contact_hints({"participants": "x"}) == []
        assert HubSpotDriver._extract_participant_contact_hints({}) == []


# ------------------------------------------------------------ find_contact
def contact_row(cid, first="", last="", email="", owner=None):
    props = {"firstname": first, "lastname": last, "email": email}
    if owner is not None:
        props["hubspot_owner_id"] = owner
    return {"id": cid, "properties": props}


class TestFindContact:
    SEARCH = f"{HS}/crm/v3/objects/contacts/search"

    def test_needs_email_or_name(self, driver, rsps):
        assert driver.find_contact() is None
        assert driver.find_contact(email="", name="") is None
        assert len(rsps.calls) == 0

    def test_by_email(self, driver, rsps):
        rsps.add(responses.POST, self.SEARCH, json={"results": [contact_row("1", "Ada", "L", "ada@x.y")]})
        out = driver.find_contact(email="  ada@x.y ")
        assert out == {"id": "1", "email": "ada@x.y", "firstname": "Ada", "lastname": "L"}
        assert json_body(rsps.calls[0]) == {
            "filterGroups": [{"filters": [{"propertyName": "email", "operator": "EQ", "value": "ada@x.y"}]}],
            "properties": ["firstname", "lastname", "email", "hubspot_owner_id"],
            "limit": 20,
        }

    def test_email_wins_over_name(self, driver, rsps):
        rsps.add(responses.POST, self.SEARCH, json={"results": [contact_row("1")]})
        driver.find_contact(email="a@b.c", name="Ignored Name")
        assert json_body(rsps.calls[0])["filterGroups"][0]["filters"][0]["propertyName"] == "email"

    @pytest.mark.parametrize(
        "name,expected_filters",
        [
            ("Ada Lovelace", [("firstname", "Ada"), ("lastname", "Lovelace")]),
            ("  Ada   van Lovelace ", [("firstname", "Ada"), ("lastname", "van Lovelace")]),
            ("Ada", [("firstname", "Ada")]),
        ],
    )
    def test_by_name_filters(self, driver, rsps, name, expected_filters):
        rsps.add(responses.POST, self.SEARCH, json={"results": [contact_row("1", "Ada")]})
        assert driver.find_contact(name=name)["id"] == "1"
        filters = json_body(rsps.calls[0])["filterGroups"][0]["filters"]
        assert [(f["propertyName"], f["value"]) for f in filters] == expected_filters
        assert all(f["operator"] == "EQ" for f in filters)

    def test_blank_name_returns_none_without_crashing(self, driver, rsps):
        # whitespace-only names are truthy but have no tokens to search for
        assert driver.find_contact(name="   ") is None
        assert len(rsps.calls) == 0

    def test_email_not_found(self, driver, rsps):
        rsps.add(responses.POST, self.SEARCH, json={"results": []})
        assert driver.find_contact(email="none@x.y") is None
        assert len(rsps.calls) == 1  # no loose fallback for emails

    def test_name_not_found_falls_back_to_loose_match(self, driver, rsps):
        rsps.add(responses.POST, self.SEARCH, json={"results": []})
        rsps.add(responses.POST, self.SEARCH, json={"results": [contact_row("5", "José", "García", "j@x.y")]})
        out = driver.find_contact(name="Jose Garcia")
        assert out == {"id": "5", "email": "j@x.y", "firstname": "José", "lastname": "García"}
        loose = json_body(rsps.calls[1])
        assert loose["limit"] == 200
        assert loose["properties"] == ["firstname", "lastname", "email"]
        assert "filterGroups" not in loose

    def test_name_not_found_and_loose_miss(self, driver, rsps):
        rsps.add(responses.POST, self.SEARCH, json={"results": []})
        rsps.add(responses.POST, self.SEARCH, json={"results": [contact_row("5", "Other", "Person")]})
        assert driver.find_contact(name="Jose Garcia") is None

    def test_ambiguous_prefers_request_owner(self, driver, rsps, caplog):
        driver.request_owner_id = "42"
        rsps.add(responses.POST, self.SEARCH, json={"results": [
            contact_row("1", "A", owner="1"), contact_row("2", "A", owner="42"), contact_row("3", "A", owner="42"),
        ]})
        with caplog.at_level(logging.WARNING, logger="hubspot_driver"):
            assert driver.find_contact(name="A")["id"] == "2"
        assert "Ambiguous contact match" in caplog.text

    def test_ambiguous_single_owner_match(self, driver, rsps):
        driver.request_owner_id = 42
        rsps.add(responses.POST, self.SEARCH, json={"results": [
            contact_row("1", owner="7"), contact_row("2", owner="42"), {"id": "3", "properties": None},
        ]})
        assert driver.find_contact(name="A")["id"] == "2"

    def test_ambiguous_without_owner_takes_first(self, driver, rsps):
        rsps.add(responses.POST, self.SEARCH, json={"results": [contact_row("1"), contact_row("2")]})
        assert driver.find_contact(name="A")["id"] == "1"

    def test_ambiguous_with_no_owner_match_takes_first(self, driver, rsps):
        driver.request_owner_id = "99"
        rsps.add(responses.POST, self.SEARCH, json={"results": [contact_row("1", owner="1"), contact_row("2", owner="2")]})
        assert driver.find_contact(name="A")["id"] == "1"

    def test_http_error_email_returns_none(self, driver, rsps):
        rsps.add(responses.POST, self.SEARCH, status=500)
        assert driver.find_contact(email="a@b.c") is None
        assert len(rsps.calls) == 1

    def test_http_error_name_tries_loose_lookup_then_none(self, driver, rsps):
        rsps.add(responses.POST, self.SEARCH, status=500)
        assert driver.find_contact(name="Ada Lovelace") is None
        assert len(rsps.calls) == 2

    def test_http_error_then_loose_success(self, driver, rsps):
        rsps.add(responses.POST, self.SEARCH, status=500)
        rsps.add(responses.POST, self.SEARCH, json={"results": [contact_row("8", "Ada", "Lovelace")]})
        assert driver.find_contact(name="Ada Lovelace")["id"] == "8"


class TestLooseContactLookups:
    SEARCH = f"{HS}/crm/v3/objects/contacts/search"

    def test_blank_name(self, driver, rsps):
        assert driver._find_contact_by_loose_name("   ") is None
        assert len(rsps.calls) == 0

    @pytest.mark.parametrize("configured,expected", [(5, 20), (100, 100), (99999, 500), ("bad", 200), (None, 200)])
    def test_limit_clamping(self, rsps, configured, expected):
        drv = make_driver(contact_text_match_limit=configured)
        rsps.add(responses.POST, self.SEARCH, json={"results": []})
        drv._find_contact_by_loose_name("Ada")
        assert json_body(rsps.calls[0])["limit"] == expected
        rsps.calls.reset()
        drv._find_contact_from_payload_text({"title": "Ada"})
        assert json_body(rsps.calls[0])["limit"] == expected

    def test_matching_rules(self, driver, rsps):
        rsps.add(responses.POST, self.SEARCH, json={"results": [
            "garbage",
            {"id": "0", "properties": None},
            contact_row("1"),
            contact_row("2", "Totally", "Different"),
            contact_row("3", "Ada", "Lovelace", "ada@x.y"),
        ]})
        # candidate "ada lovelace" is contained in the (longer) target
        assert driver._find_contact_by_loose_name("Dr. Ada Lovelace Jr")["id"] == "3"

    def test_target_inside_candidate(self, driver, rsps):
        rsps.add(responses.POST, self.SEARCH, json={"results": [contact_row("3", "Ada", "Lovelace")]})
        assert driver._find_contact_by_loose_name("Lovelace")["id"] == "3"

    def test_lookup_failure_is_swallowed(self, driver, rsps):
        rsps.add(responses.POST, self.SEARCH, status=500)
        assert driver._find_contact_by_loose_name("Ada") is None

    def test_text_match_by_title_summary_and_compact_form(self, driver, rsps):
        rsps.add(responses.POST, self.SEARCH, json={"results": [
            {"id": "x", "properties": None}, contact_row("n"), contact_row("1", "Grace", "Hopper", "g@x.y"),
        ]})
        out = driver._find_contact_from_payload_text({"title": "Sync", "summary": "met GraceHopper today"})
        assert out == {"id": "1", "firstname": "Grace", "lastname": "Hopper", "email": "g@x.y"}

    def test_text_match_uses_participants(self, driver, rsps):
        rsps.add(responses.POST, self.SEARCH, json={"results": [contact_row("1", "Grace", "Hopper")]})
        out = driver._find_contact_from_payload_text({"participants": [{"name": "grace hopper"}]})
        assert out["id"] == "1"

    def test_text_match_empty_and_miss_and_error(self, driver, rsps):
        assert driver._find_contact_from_payload_text({}) is None
        assert driver._find_contact_from_payload_text({"title": "   ", "summary": None}) is None
        assert len(rsps.calls) == 0
        rsps.add(responses.POST, self.SEARCH, json={"results": [contact_row("1", "Grace", "Hopper")]})
        assert driver._find_contact_from_payload_text({"title": "unrelated"}) is None
        rsps.replace(responses.POST, self.SEARCH, status=500)
        assert driver._find_contact_from_payload_text({"title": "Grace Hopper"}) is None


class TestFindCompany:
    SEARCH = f"{HS}/crm/v3/objects/companies/search"

    def test_found(self, driver, rsps):
        rsps.add(responses.POST, self.SEARCH, json={"results": [
            {"id": "9", "properties": {"name": "Acme", "domain": "acme.test"}},
        ]})
        assert driver.find_company("  Acme ") == {"id": "9", "name": "Acme", "domain": "acme.test"}
        assert json_body(rsps.calls[0]) == {
            "filterGroups": [{"filters": [{"propertyName": "name", "operator": "EQ", "value": "Acme"}]}],
            "properties": ["name", "domain"],
            "limit": 1,
        }

    def test_not_found(self, driver, rsps):
        rsps.add(responses.POST, self.SEARCH, json={"results": []})
        assert driver.find_company("Nope") is None

    def test_error(self, driver, rsps):
        rsps.add(responses.POST, self.SEARCH, status=500)
        assert driver.find_company("Acme") is None


# ----------------------------------------------------------------- associations
class TestAssociations:
    def test_associate_success_uses_v4_default_endpoint(self, driver, rsps):
        url = f"{HS}/crm/v4/objects/meetings/1/associations/default/contacts/2"
        rsps.add(responses.PUT, url, json={})
        assert driver._associate("meeting", "1", "contact", "2") is True
        assert rsps.calls[0].request.url == url

    def test_associate_failure_returns_false(self, driver, rsps):
        rsps.add(responses.PUT, f"{HS}/crm/v4/objects/meetings/1/associations/default/contacts/2", status=404)
        assert driver._associate("meetings", "1", "contacts", "2") is False

    def test_list_association_ids(self, driver, rsps):
        rsps.add(responses.GET, f"{HS}/crm/v4/objects/meetings/1/associations/contacts", json={"results": [
            {"toObjectId": 11}, {"toObjectId": "12"}, {"toObjectId": None}, {"toObjectId": "  "}, "junk", {},
        ]})
        assert driver._list_association_ids("meeting", "1", "contact") == ["11", "12"]

    def test_list_association_ids_empty_and_errors(self, driver, rsps):
        rsps.add(responses.GET, f"{HS}/crm/v4/objects/meetings/1/associations/contacts", json={})
        rsps.add(responses.GET, f"{HS}/crm/v4/objects/meetings/1/associations/companies", status=500)
        assert driver._list_association_ids("meetings", "1", "contacts") == []
        assert driver._list_association_ids("meetings", "1", "companies") == []


@pytest.fixture
def assoc(driver, monkeypatch):
    """Replace network-bound collaborators with recording fakes to exercise the resolver branching."""
    state = types.SimpleNamespace(
        associated=[], contacts={}, companies={}, text_contact=None, find_contact_calls=[], find_company_calls=[],
        fail_for=set(),
    )

    def fake_associate(from_type, from_id, to_type, to_id):
        state.associated.append((from_type, from_id, to_type, to_id))
        return to_id not in state.fail_for

    def fake_find_contact(email=None, name=None):
        state.find_contact_calls.append((email, name))
        return state.contacts.get(email or name)

    def fake_find_company(name):
        state.find_company_calls.append(name)
        return state.companies.get(name)

    monkeypatch.setattr(driver, "_associate", fake_associate)
    monkeypatch.setattr(driver, "find_contact", fake_find_contact)
    monkeypatch.setattr(driver, "find_company", fake_find_company)
    monkeypatch.setattr(driver, "_find_contact_from_payload_text", lambda payload: state.text_contact)
    state.driver = driver
    return state


class TestResolveAndAssociate:
    def test_direct_ids(self, assoc):
        count = assoc.driver._resolve_and_associate("meetings", "m", {"contact_id": 1, "company_id": "2"})
        assert count == 2
        assert assoc.associated == [("meetings", "m", "contacts", "1"), ("meetings", "m", "companies", "2")]
        assert assoc.find_contact_calls == [] and assoc.find_company_calls == []

    def test_metadata_id_hints(self, assoc):
        count = assoc.driver._resolve_and_associate(
            "meetings", "m", {"metadata": {"related_client_id": "5", "account_id": "6"}}
        )
        assert count == 2
        assert assoc.associated == [("meetings", "m", "contacts", "5"), ("meetings", "m", "companies", "6")]

    def test_failed_association_not_counted(self, assoc):
        assoc.fail_for = {"1"}
        assert assoc.driver._resolve_and_associate("meetings", "m", {"contact_id": "1", "company_id": "2"}) == 1

    def test_email_hint(self, assoc):
        assoc.contacts["a@b.c"] = {"id": "7"}
        count = assoc.driver._resolve_and_associate("notes", "n", {"metadata": {"contact_email": "a@b.c"}})
        assert count == 1
        assert assoc.associated == [("notes", "n", "contacts", "7")]
        assert assoc.find_contact_calls == [("a@b.c", None)]

    def test_name_hint_and_company_name_hint(self, assoc):
        assoc.contacts["Ada"] = {"id": "7"}
        assoc.companies["Acme"] = {"id": "8"}
        count = assoc.driver._resolve_and_associate(
            "calls", "c", {"contact_name": "Ada", "metadata": {"company_name": "Acme"}}
        )
        assert count == 2
        assert assoc.associated == [("calls", "c", "contacts", "7"), ("calls", "c", "companies", "8")]

    def test_participant_hints_stop_at_first_match(self, assoc):
        assoc.contacts["Bob"] = {"id": "9"}
        assoc.contacts["Zed"] = {"id": "10"}
        payload = {"participants": [{"email": "p@x.y"}, "Bob", "Zed"]}
        assert assoc.driver._resolve_and_associate("meetings", "m", payload) == 1
        assert assoc.associated == [("meetings", "m", "contacts", "9")]
        assert ("p@x.y", None) in assoc.find_contact_calls

    def test_participant_email_match_preferred_over_name(self, assoc):
        assoc.contacts["p@x.y"] = {"id": "3"}
        payload = {"participants": [{"email": "p@x.y", "name": "Pat"}]}
        assert assoc.driver._resolve_and_associate("meetings", "m", payload) == 1
        assert assoc.find_contact_calls == [("p@x.y", None)]

    def test_text_match_fallback(self, assoc):
        assoc.text_contact = {"id": "55", "firstname": "A", "lastname": "B"}
        assert assoc.driver._resolve_and_associate("meetings", "m", {"title": "Call with A B"}) == 1
        assert assoc.associated == [("meetings", "m", "contacts", "55")]

    def test_text_match_skipped_when_contact_id_hint_given(self, assoc):
        assoc.text_contact = {"id": "55"}
        assert assoc.driver._resolve_and_associate("meetings", "m", {"company_id": "2"}) == 1
        assert assoc.associated == [("meetings", "m", "companies", "2")]

    def test_nothing_to_associate(self, assoc):
        assert assoc.driver._resolve_and_associate("meetings", "m", {}) == 0
        assert assoc.associated == []

    def test_related_entities(self, assoc):
        assoc.companies["Acme Corp"] = {"id": "300"}
        assoc.contacts["Jane Roe"] = {"id": "400"}
        payload = {
            "contact_id": "1",  # suppress the fallbacks so only related_entities are exercised
            "related_entities": {
                "owner": "123",
                "hubspot_owner_id": "123",
                "contacts": ["10", "", 11, None],
                "deals": "99",
                "company": "Acme Corp",
                "contact": "Jane Roe",
                "tickets": 5,
                "companies": "Ghost Inc",
            },
        }
        count = assoc.driver._resolve_and_associate("meetings", "m", payload)
        assert assoc.associated == [
            ("meetings", "m", "contacts", "1"),
            ("meetings", "m", "contacts", "10"),
            ("meetings", "m", "contacts", "11"),
            ("meetings", "m", "deals", "99"),
            ("meetings", "m", "companies", "300"),
            ("meetings", "m", "contacts", "400"),
            ("meetings", "m", "tickets", "5"),
            ("meetings", "m", "companies", "Ghost Inc"),  # unresolved names are passed through as-is
        ]
        assert count == 8

    def test_related_entities_not_a_dict_is_ignored(self, assoc):
        assert assoc.driver._resolve_and_associate("meetings", "m", {"related_entities": ["1"]}) == 0


# ------------------------------------------------ activity property builder
class TestBuildActivityProperties:
    def test_note(self, driver):
        props = driver._build_activity_properties("note", {"title": "T", "summary": "S", "timestamp": 1700000000})
        assert props == {"hs_note_body": "T\nS", "hs_timestamp": "2023-11-14T22:13:20Z"}

    def test_note_explicit_body_and_default_timestamp(self, driver):
        props = driver._build_activity_properties("notes", {"hs_note_body": "raw", "title": "ignored"})
        assert props["hs_note_body"] == "raw"
        assert props["hs_timestamp"].endswith("Z")

    def test_empty_note_has_no_body(self, driver):
        assert "hs_note_body" not in driver._build_activity_properties("notes", {})

    def test_task(self, driver):
        props = driver._build_activity_properties(
            "task",
            {"title": "Do it", "summary": "details", "hs_task_type": "call", "hs_task_status": "completed"},
        )
        assert props["hs_task_subject"] == "Do it"
        assert props["hs_task_body"] == "details"
        assert props["hs_task_type"] == "CALL"
        assert props["hs_task_status"] == "COMPLETED"
        assert "hs_timestamp" in props

    def test_task_invalid_enums_fall_back(self, driver):
        props = driver._build_activity_properties(
            "tasks", {"hs_task_subject": "S", "hs_task_body": "B", "hs_task_type": "weird", "hs_task_status": "nope"}
        )
        assert props["hs_task_type"] == "TODO"
        assert "hs_task_status" not in props
        assert props["hs_task_subject"] == "S" and props["hs_task_body"] == "B"

    def test_meeting_full(self, driver):
        props = driver._build_activity_properties(
            "meeting",
            {
                "title": "Sync", "summary": "Notes", "start_time": 1714557600000, "end_time": "2024-05-01T11:00:00Z",
                "meeting_outcome": "completed", "location": "Room 1", "meeting_url": "http://x.test/m",
            },
        )
        assert props == {
            "hs_meeting_title": "Sync",
            "hs_meeting_body": "Notes",
            "hs_timestamp": "2024-05-01T10:00:00Z",
            "hs_meeting_start_time": "2024-05-01T10:00:00Z",
            "hs_meeting_end_time": "2024-05-01T11:00:00Z",
            "hs_meeting_outcome": "COMPLETED",
            "hs_meeting_location": "Room 1",
            "hs_meeting_external_url": "http://x.test/m",
        }

    def test_meeting_defaults(self, driver):
        props = driver._build_activity_properties("meetings", {"hs_meeting_start_time": "2024-05-01T10:00:00Z",
                                                              "hs_meeting_outcome": "bogus"})
        assert props["hs_meeting_title"] == "Meeting"
        assert props["hs_meeting_end_time"] == "2024-05-01T10:30:00Z"  # start + 30 minutes
        assert props["hs_meeting_outcome"] == "SCHEDULED"
        assert "hs_meeting_body" not in props

    def test_meeting_start_falls_back_to_timestamp_then_now(self, driver):
        assert driver._build_activity_properties("meetings", {"timestamp": 1714557600})["hs_timestamp"] == (
            "2024-05-01T10:00:00Z"
        )
        assert driver._build_activity_properties("meetings", {})["hs_meeting_start_time"].endswith("Z")

    def test_call(self, driver):
        props = driver._build_activity_properties("call", {"title": "T", "summary": "S", "duration_ms": "1500"})
        assert props["hs_call_title"] == "T" and props["hs_call_body"] == "S"
        assert props["hs_call_duration"] == 1500
        assert driver._build_activity_properties("calls", {"hs_call_duration": 7})["hs_call_duration"] == 7
        assert "hs_call_duration" not in driver._build_activity_properties("calls", {"duration_ms": "abc"})
        assert "hs_call_duration" not in driver._build_activity_properties("calls", {})

    def test_email(self, driver):
        props = driver._build_activity_properties("email", {"title": "Subj", "summary": "Body"})
        assert props["hs_email_subject"] == "Subj" and props["hs_email_text"] == "Body"
        props = driver._build_activity_properties("emails", {"hs_email_subject": "S2", "hs_email_text": "B2"})
        assert props["hs_email_subject"] == "S2" and props["hs_email_text"] == "B2"
        assert "hs_email_subject" not in driver._build_activity_properties("emails", {})

    def test_generic_object_passthrough_skips_system_fields(self, driver):
        props = driver._build_activity_properties(
            "deals",
            {"dealname": "X", "amount": 5, "none": None, "hs_object_id": "1", "metadata": {}, "related_entities": {},
             "contact_email": "a@b.c", "contact_name": "n", "company_name": "c", "contact_id": 1, "company_id": 2},
        )
        assert props == {"dealname": "X", "amount": 5}

    def test_owner_applied_from_request_context(self, driver):
        driver.request_owner_id = "9"
        assert driver._build_activity_properties("notes", {"title": "t"})["hubspot_owner_id"] == "9"
        assert driver._build_activity_properties("tasks", {"title": "t"})["hubspot_owner_id"] == "9"
        assert driver._build_activity_properties("calls", {"title": "t"})["hubspot_owner_id"] == "9"
        assert driver._build_activity_properties("emails", {"title": "t"})["hubspot_owner_id"] == "9"
        assert driver._build_activity_properties("meetings", {"title": "t"})["hubspot_owner_id"] == "9"

    def test_no_owner_by_default(self, driver):
        assert "hubspot_owner_id" not in driver._build_activity_properties("meetings", {"title": "t"})


class TestResolveOwnerId:
    def test_priority_order(self, driver):
        driver.request_owner_id = "4"
        assert driver._resolve_owner_id("", {"hubspot_owner_id": "1", "owner_id": "2",
                                             "related_entities": {"owner": "3"}}) == "1"
        assert driver._resolve_owner_id("", {"owner_id": "2", "related_entities": {"owner": "3"}}) == "2"
        assert driver._resolve_owner_id("", {"related_entities": {"owner": "3"}}) == "3"
        assert driver._resolve_owner_id("", {"related_entities": {"owners": 30}}) == "30"
        assert driver._resolve_owner_id("", {}) == "4"

    def test_numeric_extraction(self, driver):
        assert driver._resolve_owner_id("", {"owner_id": "Q6"}) == "6"
        assert driver._resolve_owner_id("", {"owner_id": " 12 "}) == "12"

    def test_non_numeric_falls_through_to_next_candidate(self, driver):
        driver.request_owner_id = "8"
        assert driver._resolve_owner_id("", {"owner_id": "QC"}) == "8"
        assert driver._resolve_owner_id("", {"owner_id": "A1B2"}) == "8"  # ambiguous digits are ignored
        assert driver._resolve_owner_id("", {"owner_id": "   "}) == "8"

    def test_nothing_resolvable(self, driver):
        assert driver._resolve_owner_id("", {}) is None
        assert driver._resolve_owner_id("", {"owner_id": "QC", "related_entities": "x"}) is None

    def _install_mapper(self, monkeypatch, behaviour):
        class FakeMapper:
            def resolve_doctor_in_crm(self, user_id, crm_type):
                return behaviour(user_id, crm_type)

        module = sys.modules["app.services.crm_mapper"]
        monkeypatch.setattr(module, "CRMEntityMapper", FakeMapper)

    def test_user_mapping_lookup(self, driver, monkeypatch):
        seen = []

        def behaviour(user_id, crm_type):
            seen.append((user_id, crm_type))
            return " 55 "

        self._install_mapper(monkeypatch, behaviour)
        assert driver._resolve_owner_id("user-1", {}) == "55"
        assert seen == [("user-1", "hubspot")]

    def test_user_mapping_not_consulted_when_owner_known(self, driver, monkeypatch):
        self._install_mapper(monkeypatch, lambda *a: pytest.fail("should not be called"))
        assert driver._resolve_owner_id("user-1", {"owner_id": "5"}) == "5"

    def test_user_mapping_miss_and_failure(self, driver, monkeypatch):
        self._install_mapper(monkeypatch, lambda *a: None)
        assert driver._resolve_owner_id("user-1", {}) is None

        def boom(*a):
            raise RuntimeError("db down")

        self._install_mapper(monkeypatch, boom)
        assert driver._resolve_owner_id("user-1", {}) is None


# ------------------------------------------------------- object-level helpers
class TestObjectHelpers:
    def test_create_patch_delete_search(self, driver, rsps):
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/deals", json={"id": "1"}, status=201)
        rsps.add(responses.PATCH, f"{HS}/crm/v3/objects/deals/1", json={"id": "1", "properties": {"a": "b"}})
        rsps.add(responses.DELETE, f"{HS}/crm/v3/objects/deals/1", status=204)
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/deals/search", json={"results": [{"id": "1"}]})
        assert driver._create_object("deals", {"a": 1})["id"] == "1"
        assert json_body(rsps.calls[0]) == {"properties": {"a": 1}}
        assert driver._patch_object("deals", "1", {"a": "b"})["properties"] == {"a": "b"}
        assert driver._delete_object("deals", "1") is True
        assert driver._search_objects("deals", properties=["a"], filters=[{"x": 1}], sort_property="a", limit=3) == [
            {"id": "1"}
        ]
        assert json_body(rsps.calls[3]) == {
            "limit": 3,
            "properties": ["a"],
            "filterGroups": [{"filters": [{"x": 1}]}],
            "sorts": [{"propertyName": "a", "direction": "DESCENDING"}],
        }

    def test_search_minimal_body(self, driver, rsps):
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/deals/search", json={})
        assert driver._search_objects("deals") == []
        assert json_body(rsps.calls[0]) == {"limit": 20}

    def test_delete_non_204(self, driver, rsps):
        rsps.add(responses.DELETE, f"{HS}/crm/v3/objects/deals/1", status=200)
        assert driver._delete_object("deals", "1") is False


# ----------------------------------------------------------------- meetings
def register_meeting_flow(rsps, meeting_id="m1", contacts=(), companies=()):
    rsps.add(responses.POST, f"{HS}/crm/v3/objects/meetings", json={"id": meeting_id}, status=201)
    rsps.add(
        responses.GET,
        f"{HS}/crm/v4/objects/meetings/{meeting_id}/associations/contacts",
        json={"results": [{"toObjectId": c} for c in contacts]},
    )
    rsps.add(
        responses.GET,
        f"{HS}/crm/v4/objects/meetings/{meeting_id}/associations/companies",
        json={"results": [{"toObjectId": c} for c in companies]},
    )


class TestSaveMeeting:
    def test_full_flow_with_direct_ids(self, driver, rsps):
        driver.request_owner_id = "77"
        register_meeting_flow(rsps, contacts=[101], companies=[202])
        rsps.add(responses.PUT, f"{HS}/crm/v4/objects/meetings/m1/associations/default/contacts/101", json={})
        rsps.add(responses.PUT, f"{HS}/crm/v4/objects/meetings/m1/associations/default/companies/202", json={})
        out = driver.save_meeting(
            "u1",
            {"title": "Sync", "summary": "Notes", "start_time": "2024-05-01T10:00:00Z",
             "contact_id": "101", "company_id": "202"},
        )
        create = json_body(rsps.calls[0])["properties"]
        assert create["hs_meeting_title"] == "Sync"
        assert create["hs_meeting_body"] == "Notes"
        # datetime properties are normalised to epoch milliseconds, owner id to an int
        assert create["hs_timestamp"] == epoch_ms(2024, 5, 1, 10)
        assert create["hs_meeting_start_time"] == epoch_ms(2024, 5, 1, 10)
        assert create["hs_meeting_end_time"] == epoch_ms(2024, 5, 1, 10, 30)
        assert create["hubspot_owner_id"] == 77
        assert create["hs_meeting_outcome"] == "SCHEDULED"
        assert out == {
            "id": "m1",
            "title": "Sync",
            "summary": "Notes",
            "linked_associations": 2,
            "associated_contact_ids": ["101"],
            "associated_company_ids": ["202"],
            "visibility_hint": None,
            "source": "hubspot",
        }

    def test_unassociated_meeting_gets_visibility_hint(self, driver, rsps):
        register_meeting_flow(rsps)
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/contacts/search", json={"results": []})
        out = driver.save_meeting("u1", {"title": "Lonely"})
        assert out["linked_associations"] == 0
        assert out["associated_contact_ids"] == [] and out["associated_company_ids"] == []
        assert "no CRM associations" in out["visibility_hint"]

    def test_association_by_email_lookup(self, driver, rsps):
        register_meeting_flow(rsps, contacts=[5])
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/contacts/search", json={"results": [contact_row("5", "A")]})
        rsps.add(responses.PUT, f"{HS}/crm/v4/objects/meetings/m1/associations/default/contacts/5", json={})
        out = driver.save_meeting("u1", {"title": "T", "contact_email": "a@b.c"})
        assert out["linked_associations"] == 1
        assert len(calls_matching(rsps, "PUT")) == 1

    def test_title_summary_fallback_to_payload(self, driver, rsps):
        register_meeting_flow(rsps)
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/contacts/search", json={"results": []})
        out = driver.save_meeting("u1", {"summary": "only summary"})
        assert out["title"] == "Meeting"
        assert out["summary"] == "only summary"

    def test_user_id_owner_lookup(self, driver, rsps, monkeypatch):
        class FakeMapper:
            def resolve_doctor_in_crm(self, user_id, crm_type):
                return "314"

        monkeypatch.setattr(sys.modules["app.services.crm_mapper"], "CRMEntityMapper", FakeMapper)
        register_meeting_flow(rsps)
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/contacts/search", json={"results": []})
        driver.save_meeting("lia-user", {"title": "T"})
        assert json_body(rsps.calls[0])["properties"]["hubspot_owner_id"] == 314

    def test_create_http_error_surfaces_status_and_body(self, driver, rsps):
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/meetings", status=400, body="bad props")
        with pytest.raises(Exception, match="Failed to save meeting to HubSpot: HTTP 400: bad props"):
            driver.save_meeting("u1", {"title": "T"})

    def test_connection_error_is_wrapped(self, driver, rsps):
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/meetings", body=requests.exceptions.ConnectTimeout("slow"))
        with pytest.raises(Exception, match="Failed to save meeting to HubSpot: slow"):
            driver.save_meeting("u1", {"title": "T"})


class TestMeetingHistory:
    SEARCH = f"{HS}/crm/v3/objects/meetings/search"

    def test_history(self, driver, rsps):
        rsps.add(responses.POST, self.SEARCH, json={"results": [
            {"id": "1", "properties": {"hs_meeting_title": "A", "hs_meeting_body": "B", "hs_timestamp": "T1",
                                       "hs_meeting_outcome": "COMPLETED", "hubspot_owner_id": "5"}},
            {"id": "2", "properties": {"hs_createdate": "C2"}},
            {"id": "3"},
        ]})
        out = driver.get_meeting_history("u1")
        body = json_body(rsps.calls[0])
        assert body["limit"] == 20
        assert body["sorts"] == [{"propertyName": "hs_timestamp", "direction": "DESCENDING"}]
        assert "hs_meeting_title" in body["properties"] and "filterGroups" not in body
        assert out[0] == {
            "id": "1", "title": "A", "summary": "B",
            "metadata": {"hubspot_id": "1", "hs_meeting_outcome": "COMPLETED", "hubspot_owner_id": "5"},
            "created_at": "T1", "source": "hubspot",
        }
        assert out[1]["created_at"] == "C2" and out[1]["title"] == ""
        assert out[2]["created_at"] is None

    def test_limit_from_filters(self, driver, rsps):
        rsps.add(responses.POST, self.SEARCH, json={"results": []})
        assert driver.get_meeting_history("u1", {"limit": "7"}) == []
        assert json_body(rsps.calls[0])["limit"] == 7

    def test_owned_entity_ids_filter(self, driver, rsps):
        rsps.add(responses.POST, self.SEARCH, json={"results": [{"id": "1"}, {"id": 2}, {"id": "3"}]})
        out = driver.get_meeting_history("u1", {"owned_entity_ids": [2, "3", "9"]})
        assert [m["id"] for m in out] == [2, "3"]

    def test_error_is_wrapped(self, driver, rsps):
        rsps.add(responses.POST, self.SEARCH, status=500)
        with pytest.raises(Exception, match="Failed to fetch meeting history from HubSpot"):
            driver.get_meeting_history("u1")


class TestPrepareMeetingHistoryFilters:
    def test_not_restricted_by_default(self, driver):
        assert driver.prepare_meeting_history_filters("u", {"limit": 3}, ["1", "2"]) == {"limit": 3}
        assert driver.prepare_meeting_history_filters("u") == {}

    def test_restricted_via_config(self):
        drv = make_driver(restrict_to_owned_entities=True)
        assert drv.prepare_meeting_history_filters("u", {"limit": 3}, [1, "2"]) == {
            "limit": 3, "owned_entity_ids": ["1", "2"],
        }

    def test_restricted_via_filters_overrides_config(self):
        drv = make_driver(restrict_to_owned_entities=True)
        assert drv.prepare_meeting_history_filters("u", {"restrict_to_owned_entities": False}, ["1"]) == {
            "restrict_to_owned_entities": False,
        }
        plain = make_driver()
        assert plain.prepare_meeting_history_filters("u", {"restrict_to_owned_entities": True}, ["1"])[
            "owned_entity_ids"
        ] == ["1"]

    def test_restricted_without_ids_adds_nothing(self):
        drv = make_driver(restrict_to_owned_entities=True)
        assert drv.prepare_meeting_history_filters("u", {}, []) == {}
        assert drv.prepare_meeting_history_filters("u", {}, None) == {}

    def test_input_filters_not_mutated(self):
        drv = make_driver(restrict_to_owned_entities=True)
        filters = {"limit": 1}
        drv.prepare_meeting_history_filters("u", filters, ["1"])
        assert filters == {"limit": 1}


# -------------------------------------------------------------------- schema
class TestSchema:
    def test_schema_info(self, driver, rsps, run):
        rsps.add(responses.GET, f"{HS}/crm/v3/schemas", json={"results": [
            {"fullyQualifiedName": "p1_custom", "name": "custom", "properties": [
                {"name": "a", "type": "string"},
                {"name": "stage", "type": "enumeration", "enumValues": [{"value": "x"}, {"value": "y"}]},
                {"type": "string"},
            ]},
            {"name": "bare"},
        ]})
        standard = ["contacts", "companies", "deals", "tickets", "calls", "emails", "meetings", "notes", "tasks",
                    "products", "line_items", "quotes"]
        for obj in standard:
            if obj == "tickets":
                rsps.add(responses.GET, f"{HS}/crm/v3/properties/{obj}", status=403)
            elif obj == "deals":
                rsps.add(responses.GET, f"{HS}/crm/v3/properties/{obj}", json={"results": [
                    {"name": "dealstage", "type": "enumeration", "enumValues": [{"value": "won"}]},
                    {"name": "amount", "type": "number"},
                    {"type": "string"},
                    "junk",
                ]})
            else:
                rsps.add(responses.GET, f"{HS}/crm/v3/properties/{obj}", json={"results": [
                    {"name": f"{obj}_prop", "type": "string"},
                ]})
        out = run(driver.get_schema_info())
        names = [t["name"] for t in out["tables"]]
        assert names == ["p1_custom", "bare"] + [o for o in standard if o != "tickets"]
        custom = out["tables"][0]
        assert custom["columns"] == ["a", "stage"]
        assert custom["column_types"] == {"a": "string", "stage": "enumeration"}
        assert custom["enum_values"] == {"stage": ["x", "y"]}
        assert out["tables"][1] == {"name": "bare", "columns": [], "column_types": {}}
        deals = next(t for t in out["tables"] if t["name"] == "deals")
        assert deals["columns"] == ["dealstage", "amount"]
        assert deals["enum_values"] == {"dealstage": ["won"]}
        contacts = next(t for t in out["tables"] if t["name"] == "contacts")
        assert "enum_values" not in contacts

    def test_standard_object_failures_keep_partial_results(self, driver, rsps, run):
        rsps.add(responses.GET, f"{HS}/crm/v3/schemas", json={"results": []})
        rsps.add(responses.GET, f"{HS}/crm/v3/properties/contacts", json={"results": [{"name": "email", "type": "string"}]})
        # every other standard object is unregistered -> ConnectionError -> skipped
        out = run(driver.get_schema_info())
        assert [t["name"] for t in out["tables"]] == ["contacts"]

    def test_schema_endpoint_failure_is_raised(self, driver, rsps, run):
        rsps.add(responses.GET, f"{HS}/crm/v3/schemas", status=401)
        with pytest.raises(requests.exceptions.HTTPError):
            run(driver.get_schema_info())


# ---------------------------------------------------------------------- CRUD
class TestCreateEntity:
    def test_contact_with_mapping_owner_and_associations(self, driver, rsps, run):
        driver.request_owner_id = "Q6"
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/contacts", status=201,
                 json={"id": "c1", "properties": {"firstname": "Ada", "lastname": "L", "email": "a@b.c"}})
        rsps.add(responses.PUT, f"{HS}/crm/v4/objects/contacts/c1/associations/default/companies/9", json={})
        rsps.add(responses.GET, f"{HS}/crm/v4/objects/contacts/c1/associations/contacts", json={"results": []})
        rsps.add(responses.GET, f"{HS}/crm/v4/objects/contacts/c1/associations/companies",
                 json={"results": [{"toObjectId": 9}]})
        payload = {"first_name": "Ada", "email": "a@b.c", "phone": "123", "company_id": "9", "hs_object_id": "ignored",
                   "unmapped": "dropped", "last_name": None}
        out = run(driver.create_entity("contact", payload))
        assert json_body(rsps.calls[0]) == {
            "properties": {"firstname": "Ada", "email": "a@b.c", "phone": "123", "hubspot_owner_id": 6}
        }
        assert out == {
            "id": "c1",
            "linked_associations": 1,
            "associated_contact_ids": [],
            "associated_company_ids": ["9"],
            "visibility_hint": None,  # only activities get a visibility hint
            "source": "hubspot",
            "first_name": "Ada",
            "last_name": "L",
            "email": "a@b.c",
            "full_name": "Ada L",
            "created_at": None,
        }

    def test_explicit_owner_property_is_not_overridden(self, driver, rsps, run):
        driver.request_owner_id = "6"
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/contacts", json={"id": "c1"}, status=201)
        run(driver.create_entity("contact", {"first_name": "A", "hubspot_owner_id": "5"}))
        assert json_body(rsps.calls[0])["properties"]["hubspot_owner_id"] == 5

    def test_deal_alias_columns_and_date_coercion(self, driver, rsps, run):
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/deals", json={"id": "d1"}, status=201)
        run(driver.create_entity("deal", {"deal_name": "Big", "amount": "1500.50", "close_date": "2024-01-31"}))
        props = json_body(rsps.calls[0])["properties"]
        assert props == {
            "dealname": "Big",
            "amount": 1500.5,
            "closedate": epoch_ms(2024, 1, 31),
        }

    def test_activity_entity_uses_activity_builder_and_flags_missing_associations(self, driver, rsps, run):
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/notes", json={"id": "n1", "properties": {"hs_note_body": "T\nS"}},
                 status=201)
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/contacts/search", json={"results": []})
        out = run(driver.create_entity("note", {"title": "T", "summary": "S"}))
        props = json_body(rsps.calls[0])["properties"]
        assert props["hs_note_body"] == "T\nS"
        assert out["id"] == "n1"
        assert out["body"] == "T\nS"
        assert "not linked to a contact/company" in out["visibility_hint"]

    def test_activity_linked_via_email_has_no_hint(self, driver, rsps, run):
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/notes", json={"id": "n1"}, status=201)
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/contacts/search", json={"results": [contact_row("5", "A")]})
        rsps.add(responses.PUT, f"{HS}/crm/v4/objects/notes/n1/associations/default/contacts/5", json={})
        rsps.add(responses.GET, f"{HS}/crm/v4/objects/notes/n1/associations/contacts", json={"results": [{"toObjectId": 5}]})
        out = run(driver.create_entity("note", {"title": "T", "contact_email": "a@b.c"}))
        assert out["linked_associations"] == 1
        assert out["associated_contact_ids"] == ["5"]
        assert out["visibility_hint"] is None

    def test_object_type_falls_back_to_entity_type(self, driver, rsps, run):
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/contacts", json={"id": "c9"}, status=201)
        run(driver.create_entity("customer", {"email": "x@y.z"}))
        assert json_body(rsps.calls[0]) == {"properties": {"email": "x@y.z"}}

    def test_unknown_entity_type(self, driver, rsps, run):
        with pytest.raises(ValueError, match="No schema mapping"):
            run(driver.create_entity("ghost", {"a": 1}))
        assert len(rsps.calls) == 0

    ENUM_ERROR = (
        '{"message":"Property values were not valid: [{\\"error\\":\\"INVALID_OPTION\\"}] '
        'Valid options are: pipelineId=default : [appointmentscheduled, qualifiedtobuy, closedwon]"}'
    )

    def test_enum_validation_error_is_fuzzy_corrected_and_retried(self, driver, rsps, run):
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/deals", status=400, body=self.ENUM_ERROR)
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/deals", status=201,
                 json={"id": "d1", "properties": {"dealstage": "appointmentscheduled"}})
        out = run(driver.create_entity("deal", {"deal_name": "zzzz", "stage": "scheduled"}))
        posts = calls_matching(rsps, "POST", "/crm/v3/objects/deals")
        assert len(posts) == 2
        assert json_body(posts[0])["properties"]["dealstage"] == "scheduled"
        assert json_body(posts[1])["properties"] == {"dealname": "zzzz", "dealstage": "appointmentscheduled"}
        assert out["id"] == "d1"
        assert out["stage"] == "appointmentscheduled"

    def test_enum_retry_failure_raises_original_error(self, driver, rsps, run):
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/deals", status=400, body=self.ENUM_ERROR)
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/deals", status=400, body="still bad")
        with pytest.raises(requests.exceptions.HTTPError) as info:
            run(driver.create_entity("deal", {"stage": "scheduled"}))
        assert "Valid options are" in info.value.response.text  # the first error, not the retry's
        assert len(calls_matching(rsps, "POST", "/crm/v3/objects/deals")) == 2

    def test_enum_error_without_fuzzy_match_is_not_retried(self, driver, rsps, run):
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/deals", status=400,
                 body="Valid options are: stage : [abc, def]")
        with pytest.raises(requests.exceptions.HTTPError):
            run(driver.create_entity("deal", {"stage": "zzzz"}))
        assert len(rsps.calls) == 1

    def test_non_enum_400_is_raised(self, driver, rsps, run):
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/deals", status=400, body="missing required property")
        with pytest.raises(requests.exceptions.HTTPError):
            run(driver.create_entity("deal", {"deal_name": "x"}))
        assert len(rsps.calls) == 1

    @pytest.mark.parametrize("status", [401, 403, 409, 429, 500])
    def test_other_http_errors_are_raised(self, driver, rsps, run, status):
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/deals", status=status)
        with pytest.raises(requests.exceptions.HTTPError):
            run(driver.create_entity("deal", {"deal_name": "x"}))
        assert len(rsps.calls) == 1

    def test_timeout_is_raised(self, driver, rsps, run):
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/deals", body=requests.exceptions.ReadTimeout("slow"))
        with pytest.raises(requests.exceptions.ReadTimeout):
            run(driver.create_entity("deal", {"deal_name": "x"}))


class TestReadEntities:
    def test_read_with_mapping(self, driver, rsps, run):
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/contacts/search", json={"results": [
            {"id": "1", "properties": {"firstname": "Ada", "lastname": "L", "email": "a@b.c", "createdate": "C"}},
            {"id": "2", "properties": {"firstname": "Solo"}},
        ]})
        out = run(driver.read_entities("contact", filters={"limit": "5"}))
        body = json_body(rsps.calls[0])
        assert body["limit"] == 5
        assert body["properties"] == sorted(
            {"firstname", "lastname", "email", "createdate", "phone", "hubspot_owner_id"}
        )
        assert body["sorts"] == [{"propertyName": "createdate", "direction": "DESCENDING"}]
        assert "filterGroups" not in body
        assert out[0] == {
            "id": "1", "source": "hubspot", "first_name": "Ada", "last_name": "L", "email": "a@b.c",
            "full_name": "Ada L", "created_at": "C",
        }
        assert out[1]["full_name"] == "Solo" and out[1]["email"] is None

    def test_read_without_mapping_columns(self, driver, rsps, run):
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/companies/search", json={"results": [{"id": "9"}]})
        out = run(driver.read_entities("company"))
        assert json_body(rsps.calls[0]) == {"limit": 20}
        assert out == [{"id": "9", "source": "hubspot"}]

    def test_read_owned_entity_ids(self, driver, rsps, run):
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/contacts/search", json={"results": [
            {"id": "1", "properties": {}}, {"id": 2, "properties": {}}, {"id": "3", "properties": {}},
        ]})
        out = run(driver.read_entities("contact", filters={"owned_entity_ids": [2, "3", "99"]}))
        assert [r["id"] for r in out] == [2, "3"]

    def test_read_http_error(self, driver, rsps, run):
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/contacts/search", status=500)
        with pytest.raises(requests.exceptions.HTTPError):
            run(driver.read_entities("contact"))

    def test_read_unknown_entity(self, driver, run):
        with pytest.raises(ValueError):
            run(driver.read_entities("ghost"))

    def test_read_object_type_fallback(self, driver, rsps, run):
        rsps.add(responses.POST, f"{HS}/crm/v3/objects/contacts/search", json={"results": []})
        assert run(driver.read_entities("customer")) == []


class TestUpdateEntity:
    def test_update_contact(self, driver, rsps, run):
        driver.request_owner_id = "12"
        rsps.add(responses.PATCH, f"{HS}/crm/v3/objects/contacts/c1",
                 json={"id": "c1", "properties": {"firstname": "Grace", "email": "g@x.y"}})
        out = run(driver.update_entity("contact", "c1", {"first_name": "Grace", "phone": "5"}))
        assert json_body(rsps.calls[0]) == {
            "properties": {"firstname": "Grace", "phone": "5", "hubspot_owner_id": 12}
        }
        assert out["id"] == "c1"
        assert out["first_name"] == "Grace"
        assert out["linked_associations"] == 0
        assert out["source"] == "hubspot"

    def test_update_activity_uses_activity_builder(self, driver, rsps, run):
        rsps.add(responses.PATCH, f"{HS}/crm/v3/objects/meetings/m1", json={"id": "m1", "properties": {}})
        run(driver.update_entity("meeting", "m1", {"title": "Renamed"}))
        props = json_body(rsps.calls[0])["properties"]
        assert props["hs_meeting_title"] == "Renamed"

    def test_association_only_update_skips_patch(self, driver, rsps, run):
        rsps.add(responses.PUT, f"{HS}/crm/v4/objects/contacts/c1/associations/default/companies/9", json={})
        out = run(driver.update_entity("contact", "c1", {"company_id": "9"}))
        assert not calls_matching(rsps, "PATCH")
        assert out["id"] == "c1"
        assert out["linked_associations"] == 1

    def test_update_with_nothing_to_write(self, driver, rsps, run):
        with pytest.raises(ValueError, match="No writable HubSpot properties"):
            run(driver.update_entity("contact", "c1", {"unmapped": 1}))
        assert len(rsps.calls) == 0

    def test_association_failure_after_patch_is_swallowed(self, driver, rsps, run, monkeypatch):
        rsps.add(responses.PATCH, f"{HS}/crm/v3/objects/contacts/c1", json={"id": "c1", "properties": {}})

        def boom(*args, **kwargs):
            raise RuntimeError("assoc exploded")

        monkeypatch.setattr(driver, "_resolve_and_associate", boom)
        out = run(driver.update_entity("contact", "c1", {"first_name": "x"}))
        assert out["linked_associations"] == 0

    def test_update_http_error(self, driver, rsps, run):
        rsps.add(responses.PATCH, f"{HS}/crm/v3/objects/contacts/c1", status=404)
        with pytest.raises(requests.exceptions.HTTPError):
            run(driver.update_entity("contact", "c1", {"first_name": "x"}))

    def test_update_unknown_entity(self, driver, run):
        with pytest.raises(ValueError):
            run(driver.update_entity("ghost", "1", {"a": 1}))


class TestDeleteEntity:
    def test_delete(self, driver, rsps, run):
        rsps.add(responses.DELETE, f"{HS}/crm/v3/objects/contacts/c1", status=204)
        assert run(driver.delete_entity("contact", "c1")) is True

    def test_delete_non_204(self, driver, rsps, run):
        rsps.add(responses.DELETE, f"{HS}/crm/v3/objects/deals/d1", status=200)
        assert run(driver.delete_entity("deal", "d1")) is False

    def test_delete_error(self, driver, rsps, run):
        rsps.add(responses.DELETE, f"{HS}/crm/v3/objects/contacts/c1", status=404)
        with pytest.raises(requests.exceptions.HTTPError):
            run(driver.delete_entity("contact", "c1"))

    def test_delete_unknown_entity(self, driver, run):
        with pytest.raises(ValueError):
            run(driver.delete_entity("ghost", "1"))
