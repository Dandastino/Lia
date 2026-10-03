"""Salesforce driver: all HTTP traffic is mocked with ``responses``."""
from __future__ import annotations

import pytest
import requests
import responses

from app.drivers.salesforce_driver import SalesforceDriver

from .helpers import calls_matching, form_body, json_body, query_params

INSTANCE = "https://acme.my.salesforce.com"
TOKEN_URL = f"{INSTANCE}/services/oauth2/token"
API = f"{INSTANCE}/services/data/v60.0"

MAPPINGS = {
    "contact": {
        "table_name": "Contact",
        "column_mapping": {
            "first_name": "FirstName",
            "last_name": "LastName",
            "email": "Email",
            "created_at": "CreatedDate",
        },
        "table_columns": ["Phone", "Title"],
    },
    "weird": {
        "table_name": "Contact",
        "column_mapping": {"a": "Bad Field;", "b": "Name", "created_at": "Created Date"},
    },
    "unsafe": {"table_name": "Contact; DROP", "column_mapping": {"a": "Name"}},
    "notable": {"column_mapping": {"a": "Name"}},
    "nomap": {"table_name": "Account"},
}


def make_config(**overrides):
    config = {
        "instance_url": INSTANCE,
        "client_id": "cid",
        "client_secret": "csecret",
        "username": "user@acme.test",
        "password": "pw",
        "schema_mappings": MAPPINGS,
    }
    config.update(overrides)
    return config


def add_token(rsps, token="tok-1", **kwargs):  # noqa: S107
    rsps.add(responses.POST, TOKEN_URL, json={"access_token": token}, **kwargs)


@pytest.fixture
def driver(rsps):
    add_token(rsps)
    drv = SalesforceDriver(make_config())
    rsps.calls.reset()
    return drv


# ----------------------------------------------------------------- construction
class TestConstruction:
    def test_obtains_token_with_password_grant(self, rsps):
        add_token(rsps, token="abc")
        drv = SalesforceDriver(make_config())
        assert drv.access_token == "abc"
        assert len(rsps.calls) == 1
        assert form_body(rsps.calls[0]) == {
            "grant_type": "password",
            "client_id": "cid",
            "client_secret": "csecret",
            "username": "user@acme.test",
            "password": "pw",
        }
        assert drv._get_headers()["Authorization"] == "Bearer abc"

    @pytest.mark.parametrize("missing", ["instance_url", "client_id", "client_secret", "username", "password"])
    def test_missing_credentials(self, rsps, missing):
        config = make_config()
        config.pop(missing)
        with pytest.raises(ValueError, match="credentials"):
            SalesforceDriver(config)
        assert len(rsps.calls) == 0

    def test_no_config_at_all(self, rsps):
        with pytest.raises(ValueError):
            SalesforceDriver(None)

    @pytest.mark.parametrize(
        "url",
        [
            "http://acme.my.salesforce.com",  # not https
            "https://evil.example.com",
            "https://salesforce.com.evil.example",
            "https://evilsalesforce.com",
            "ftp://acme.my.salesforce.com",
            "https://localhost",
        ],
    )
    def test_rejects_unsafe_instance_url(self, rsps, url):
        with pytest.raises(ValueError, match="instance_url"):
            SalesforceDriver(make_config(instance_url=url))
        assert len(rsps.calls) == 0  # credentials must never be posted to a rejected host

    @pytest.mark.parametrize(
        "url",
        [
            "https://acme.my.salesforce.com",
            "https://acme--sandbox.sandbox.my.salesforce.com",
            "https://acme.force.com",
            "https://acme.salesforce.mil",
        ],
    )
    def test_accepts_salesforce_domains(self, rsps, url):
        rsps.add(responses.POST, f"{url}/services/oauth2/token", json={"access_token": "t"})
        assert SalesforceDriver(make_config(instance_url=url)).access_token == "t"

    def test_extra_host_suffix_from_env(self, rsps, monkeypatch):
        monkeypatch.setenv("SALESFORCE_EXTRA_HOST_SUFFIXES", ".sfdc.example.org")
        rsps.add(responses.POST, "https://crm.sfdc.example.org/services/oauth2/token", json={"access_token": "t"})
        assert SalesforceDriver(make_config(instance_url="https://crm.sfdc.example.org")).access_token == "t"

    def test_timeout_and_ssl_config(self, rsps):
        add_token(rsps)
        drv = SalesforceDriver(make_config(request_timeout_seconds=7, verify_ssl=False))
        assert drv.request_timeout_seconds == 7.0
        assert drv.verify_ssl is False
        kwargs = rsps.calls[0].request.req_kwargs
        assert kwargs["timeout"] == 7.0
        assert kwargs["verify"] is False

    @pytest.mark.parametrize("raw,expected", [("abc", 20.0), (None, 20.0), (0, 1.0), (-5, 1.0), ("2.5", 2.5)])
    def test_timeout_normalisation(self, rsps, raw, expected):
        add_token(rsps)
        assert SalesforceDriver(make_config(request_timeout_seconds=raw)).request_timeout_seconds == expected

    def test_default_timeout_and_verify(self, rsps):
        add_token(rsps)
        drv = SalesforceDriver(make_config())
        assert drv.request_timeout_seconds == 20.0
        assert drv.verify_ssl is True


# ------------------------------------------------------------------ OAuth errors
class TestOAuth:
    def test_token_http_error(self, rsps):
        rsps.add(responses.POST, TOKEN_URL, json={"error": "invalid_grant"}, status=400)
        with pytest.raises(Exception, match="Failed to obtain Salesforce access token"):
            SalesforceDriver(make_config())

    def test_token_timeout(self, rsps):
        rsps.add(responses.POST, TOKEN_URL, body=requests.exceptions.ConnectTimeout("too slow"))
        with pytest.raises(Exception, match="Failed to obtain Salesforce access token"):
            SalesforceDriver(make_config())

    def test_token_response_without_access_token(self, rsps):
        rsps.add(responses.POST, TOKEN_URL, json={"foo": "bar"})
        with pytest.raises(ValueError, match="access_token"):
            SalesforceDriver(make_config())


# ---------------------------------------------------------------- request layer
class TestRequest:
    def test_bearer_header_timeout_and_verify(self, driver, rsps):
        rsps.add(responses.GET, f"{API}/ping", json={})
        driver._request("GET", "/services/data/v60.0/ping")
        call = rsps.calls[0]
        assert call.request.headers["Authorization"] == "Bearer tok-1"
        assert call.request.req_kwargs["timeout"] == 20.0
        assert call.request.req_kwargs["verify"] is True

    def test_absolute_url_is_used_as_is(self, driver, rsps):
        rsps.add(responses.GET, f"{INSTANCE}/abs", json={})
        driver._request("GET", f"{INSTANCE}/abs")
        assert rsps.calls[0].request.url == f"{INSTANCE}/abs"

    def test_401_refreshes_token_and_retries_once(self, driver, rsps):
        rsps.add(responses.GET, f"{API}/ping", status=401)
        add_token(rsps, token="tok-2")
        rsps.add(responses.GET, f"{API}/ping", json={"ok": True})
        resp = driver._request("GET", "/services/data/v60.0/ping")
        assert resp.json() == {"ok": True}
        assert [c.request.method for c in rsps.calls] == ["GET", "POST", "GET"]
        assert rsps.calls[0].request.headers["Authorization"] == "Bearer tok-1"
        assert rsps.calls[2].request.headers["Authorization"] == "Bearer tok-2"
        assert driver.access_token == "tok-2"

    def test_second_401_is_raised_not_looped(self, driver, rsps):
        rsps.add(responses.GET, f"{API}/ping", status=401)
        add_token(rsps, token="tok-2")
        rsps.add(responses.GET, f"{API}/ping", status=401)
        with pytest.raises(requests.exceptions.HTTPError):
            driver._request("GET", "/services/data/v60.0/ping")
        assert len(rsps.calls) == 3

    def test_retry_disabled(self, driver, rsps):
        rsps.add(responses.GET, f"{API}/ping", status=401)
        with pytest.raises(requests.exceptions.HTTPError):
            driver._request("GET", "/services/data/v60.0/ping", retry_on_401=False)
        assert len(rsps.calls) == 1

    def test_refresh_failure_during_retry_propagates(self, driver, rsps):
        rsps.add(responses.GET, f"{API}/ping", status=401)
        rsps.add(responses.POST, TOKEN_URL, status=500)
        with pytest.raises(Exception, match="Failed to obtain Salesforce access token"):
            driver._request("GET", "/services/data/v60.0/ping")

    def test_server_error_raises(self, driver, rsps):
        rsps.add(responses.GET, f"{API}/ping", status=503)
        with pytest.raises(requests.exceptions.HTTPError):
            driver._request("GET", "/services/data/v60.0/ping")
        assert len(rsps.calls) == 1  # no retry for non-401

    def test_timeout_propagates(self, driver, rsps):
        rsps.add(responses.GET, f"{API}/ping", body=requests.exceptions.ReadTimeout("slow"))
        with pytest.raises(requests.exceptions.ReadTimeout):
            driver._request("GET", "/services/data/v60.0/ping")


# --------------------------------------------------------------------- helpers
class TestHelpers:
    @pytest.mark.parametrize(
        "raw,expected",
        [(5, 5), ("7", 7), (0, 1), (-3, 1), (10_000, 200), (200, 200), ("x", 20), (None, 20), (3.9, 3)],
    )
    def test_normalize_limit(self, raw, expected):
        assert SalesforceDriver._normalize_limit(raw) == expected

    def test_normalize_limit_custom_default(self):
        assert SalesforceDriver._normalize_limit("zzz", default=200) == 200

    @pytest.mark.parametrize(
        "value,ok",
        [("Contact", True), ("My_Obj__c", True), ("_x", True), ("1abc", False), ("a b", False),
         ("a;b", False), ("", False), (None, False), ("a'b", False)],
    )
    def test_is_safe_identifier(self, value, ok):
        assert SalesforceDriver._is_safe_identifier(value) is ok

    def test_escape_soql_string(self):
        assert SalesforceDriver._escape_soql_string("O'Brien") == "O\\'Brien"
        assert SalesforceDriver._escape_soql_string("a\\b") == "a\\\\b"
        # backslash is escaped first so a trailing backslash cannot neutralise the quote escape
        assert SalesforceDriver._escape_soql_string("\\'") == "\\\\\\'"

    def test_compact_http_error(self):
        resp = requests.Response()
        resp.status_code = 400
        resp._content = b"line1\n" + b"x" * 500
        err = requests.exceptions.HTTPError("boom", response=resp)
        msg = SalesforceDriver._compact_http_error(err)
        assert msg.startswith("HTTP 400: line1 xxx")
        assert len(msg) <= len("HTTP 400: ") + 400
        assert SalesforceDriver._compact_http_error(ValueError("plain")) == "plain"

    def test_collect_mapped_fields(self, driver):
        out = driver._collect_mapped_fields(
            {
                "first_name": "Ada",
                "email": None,
                "Phone": "123",
                "Title": None,
                "Unknown": "dropped",
                "metadata": {"a": 1},
                "participants": [],
                "related_entities": {},
            },
            {"first_name": "FirstName", "email": "Email", "bad": ["list"]},
            {"Phone", "Title", "metadata", "participants", "related_entities"},
        )
        assert out == {"FirstName": "Ada", "Phone": "123"}


# ------------------------------------------------------------------- meetings
class TestMeetings:
    def test_save_meeting(self, driver, rsps):
        rsps.add(responses.POST, f"{API}/sobjects/Task", json={"id": "00T1", "success": True}, status=201)
        out = driver.save_meeting("u1", {"title": "Kickoff", "summary": "Notes", "participants": ["a"]})
        assert json_body(rsps.calls[0]) == {
            "Subject": "Kickoff",
            "Description": "Notes",
            "Status": "Completed",
            "Priority": "Normal",
        }
        assert out == {
            "id": "00T1",
            "title": "Kickoff",
            "summary": "Notes",
            "participants": ["a"],
            "metadata": {"salesforce_id": "00T1"},
            "source": "salesforce",
        }

    def test_save_meeting_defaults_and_metadata(self, driver, rsps):
        rsps.add(responses.POST, f"{API}/sobjects/Task", json={"id": "00T2"}, status=201)
        out = driver.save_meeting("u1", {"metadata": {"k": "v"}})
        assert json_body(rsps.calls[0])["Subject"] == "Meeting"
        assert out["metadata"] == {"k": "v"}

    def test_save_meeting_http_error(self, driver, rsps):
        rsps.add(responses.POST, f"{API}/sobjects/Task", body="bad field", status=400)
        with pytest.raises(Exception, match="Failed to save meeting to Salesforce: HTTP 400: bad field"):
            driver.save_meeting("u1", {"title": "x"})

    def test_save_meeting_retries_after_401(self, driver, rsps):
        rsps.add(responses.POST, f"{API}/sobjects/Task", status=401)
        add_token(rsps, token="tok-2")
        rsps.add(responses.POST, f"{API}/sobjects/Task", json={"id": "00T3"}, status=201)
        assert driver.save_meeting("u1", {"title": "x"})["id"] == "00T3"

    def test_history(self, driver, rsps):
        rsps.add(
            responses.GET,
            f"{API}/query",
            json={"records": [
                {"Id": "A1", "Subject": "s1", "Description": "d1", "CreatedDate": "2024-01-01"},
                {"Id": "A2", "Subject": "s2", "CreatedDate": "2024-01-02"},
            ]},
        )
        out = driver.get_meeting_history("u1")
        assert query_params(rsps.calls[0])["q"] == (
            "SELECT Id, Subject, Description, Status, CreatedDate FROM Task ORDER BY CreatedDate DESC LIMIT 20"
        )
        assert [m["id"] for m in out] == ["A1", "A2"]
        assert out[0] == {
            "id": "A1", "title": "s1", "summary": "d1", "participants": [],
            "metadata": {"salesforce_id": "A1"}, "created_at": "2024-01-01", "source": "salesforce",
        }
        assert out[1]["summary"] == ""

    @pytest.mark.parametrize("raw,expected", [(5, 5), ("abc", 20), (99999, 200), (0, 1)])
    def test_history_limit_normalised(self, driver, rsps, raw, expected):
        rsps.add(responses.GET, f"{API}/query", json={"records": []})
        driver.get_meeting_history("u1", {"limit": raw})
        assert query_params(rsps.calls[0])["q"].endswith(f"LIMIT {expected}")

    def test_history_owned_entity_ids_filter(self, driver, rsps):
        rsps.add(responses.GET, f"{API}/query", json={"records": [{"Id": "A1"}, {"Id": "A2"}, {"Id": "A3"}]})
        out = driver.get_meeting_history("u1", {"owned_entity_ids": ["A2", "A3", "ZZ"]})
        assert [m["id"] for m in out] == ["A2", "A3"]

    def test_history_empty_owned_ids_means_unfiltered(self, driver, rsps):
        rsps.add(responses.GET, f"{API}/query", json={"records": [{"Id": "A1"}]})
        assert len(driver.get_meeting_history("u1", {"owned_entity_ids": []})) == 1

    def test_history_http_error(self, driver, rsps):
        rsps.add(responses.GET, f"{API}/query", json=[{"errorCode": "X"}], status=400)
        with pytest.raises(Exception, match="Failed to retrieve meeting history from Salesforce: HTTP 400"):
            driver.get_meeting_history("u1")

    def test_prepare_meeting_history_filters(self, driver):
        # Salesforce keeps the base-class behaviour: owned ids are always passed through as strings.
        assert driver.prepare_meeting_history_filters("u1", {"limit": 3}, [1, "2"]) == {
            "limit": 3,
            "owned_entity_ids": ["1", "2"],
        }
        assert driver.prepare_meeting_history_filters("u1", None, None) == {}


# --------------------------------------------------------------------- schema
class TestSchema:
    def test_schema_info(self, driver, rsps, run):
        rsps.add(responses.GET, f"{API}/sobjects", json={"sobjects": [
            {"name": "Account"}, {"name": "Bad Name"}, {"name": 5}, {"name": "Lead"}, {"name": "Broken"},
        ]})
        rsps.add(responses.GET, f"{API}/sobjects/Account/describe",
                 json={"fields": [{"name": "Id", "type": "id"}, {"name": "Name", "type": "string"}]})
        rsps.add(responses.GET, f"{API}/sobjects/Lead/describe", json={"fields": []})
        rsps.add(responses.GET, f"{API}/sobjects/Broken/describe", status=403)
        out = run(driver.get_schema_info())
        assert out == {"tables": [
            {"name": "Account", "columns": ["Id", "Name"], "column_types": {"Id": "id", "Name": "string"}},
            {"name": "Lead", "columns": [], "column_types": {}},
        ]}
        # unsafe object names are never requested
        assert not calls_matching(rsps, contains="Bad")

    def test_schema_max_objects(self, rsps, run):
        add_token(rsps)
        drv = SalesforceDriver(make_config(schema_max_objects=1))
        rsps.add(responses.GET, f"{API}/sobjects", json={"sobjects": [{"name": "A"}, {"name": "B"}]})
        rsps.add(responses.GET, f"{API}/sobjects/A/describe", json={"fields": []})
        assert [t["name"] for t in run(drv.get_schema_info())["tables"]] == ["A"]

    def test_schema_failure_is_raised(self, driver, rsps, run):
        rsps.add(responses.GET, f"{API}/sobjects", status=500)
        with pytest.raises(requests.exceptions.HTTPError):
            run(driver.get_schema_info())


# ------------------------------------------------------------------------ CRUD
class TestCreate:
    def test_create_maps_fields(self, driver, rsps, run):
        rsps.add(responses.POST, f"{API}/sobjects/Contact", json={"id": "003X"}, status=201)
        payload = {
            "first_name": "Ada", "email": "a@b.c", "Phone": "1", "Unknown": "x", "metadata": {"m": 1}, "title": None,
        }
        out = run(driver.create_entity("contact", payload))
        assert json_body(rsps.calls[0]) == {"FirstName": "Ada", "Email": "a@b.c", "Phone": "1"}
        assert out == {"id": "003X", **payload, "source": "salesforce"}

    def test_create_requires_writable_fields(self, driver, rsps, run):
        with pytest.raises(ValueError, match="No writable Salesforce fields"):
            run(driver.create_entity("contact", {"nothing": 1}))
        assert len(rsps.calls) == 0

    def test_create_unknown_entity(self, driver, run):
        with pytest.raises(ValueError, match="No schema mapping"):
            run(driver.create_entity("ghost", {"a": 1}))

    @pytest.mark.parametrize("entity", ["unsafe", "notable"])
    def test_create_rejects_unsafe_object_name(self, driver, rsps, run, entity):
        with pytest.raises(ValueError, match="Unsafe Salesforce object name"):
            run(driver.create_entity(entity, {"a": 1}))
        assert len(rsps.calls) == 0

    def test_create_http_error(self, driver, rsps, run):
        rsps.add(responses.POST, f"{API}/sobjects/Contact", json=[{"message": "REQUIRED_FIELD_MISSING"}], status=400)
        with pytest.raises(requests.exceptions.HTTPError):
            run(driver.create_entity("contact", {"first_name": "Ada"}))

    def test_create_survives_token_expiry(self, driver, rsps, run):
        rsps.add(responses.POST, f"{API}/sobjects/Contact", status=401)
        add_token(rsps, token="tok-2")
        rsps.add(responses.POST, f"{API}/sobjects/Contact", json={"id": "003Y"}, status=201)
        assert run(driver.create_entity("contact", {"first_name": "Ada"}))["id"] == "003Y"

    def test_owner_attributes_do_not_break_create(self, driver, rsps, run):
        # Salesforce does not consume request_owner_*; scoping is enforced by owned_entity_ids.
        driver.request_owner_id = "005OWNER"
        driver.request_owner_column = "OwnerId"
        rsps.add(responses.POST, f"{API}/sobjects/Contact", json={"id": "1"}, status=201)
        run(driver.create_entity("contact", {"first_name": "Ada"}))
        assert json_body(rsps.calls[0]) == {"FirstName": "Ada"}


class TestRead:
    def test_read_builds_soql(self, driver, rsps, run):
        rsps.add(responses.GET, f"{API}/query", json={"records": [
            {"Id": "1", "FirstName": "Ada", "LastName": "L", "Email": "a@b.c", "CreatedDate": "d"},
        ]})
        out = run(driver.read_entities("contact", filters={"limit": 5}))
        assert query_params(rsps.calls[0])["q"] == (
            "SELECT Id, FirstName, LastName, Email, CreatedDate FROM Contact ORDER BY CreatedDate DESC LIMIT 5"
        )
        assert out == [{
            "id": "1", "first_name": "Ada", "last_name": "L", "email": "a@b.c", "created_at": "d",
            "source": "salesforce",
        }]

    def test_read_defaults_without_mapping_columns(self, driver, rsps, run):
        rsps.add(responses.GET, f"{API}/query", json={"records": [{"Id": "9"}]})
        out = run(driver.read_entities("nomap"))
        assert query_params(rsps.calls[0])["q"] == "SELECT Id FROM Account LIMIT 20"
        assert out == [{"id": "9", "source": "salesforce"}]

    def test_read_skips_unsafe_fields_and_order_column(self, driver, rsps, run):
        rsps.add(responses.GET, f"{API}/query", json={"records": []})
        run(driver.read_entities("weird"))
        assert query_params(rsps.calls[0])["q"] == "SELECT Id, Name FROM Contact LIMIT 20"

    def test_read_owner_scope_uses_where_in(self, driver, rsps, run):
        rsps.add(responses.GET, f"{API}/query", json={"records": []})
        run(driver.read_entities("contact", filters={"owned_entity_ids": ["a1", 22]}))
        q = query_params(rsps.calls[0])["q"]
        assert " WHERE Id IN ('a1', '22') ORDER BY CreatedDate DESC LIMIT 20" in q

    def test_read_soql_injection_in_owned_ids_is_escaped(self, driver, rsps, run):
        rsps.add(responses.GET, f"{API}/query", json={"records": []})
        evil = "x') OR Name != '"
        run(driver.read_entities("contact", filters={"owned_entity_ids": [evil, "back\\slash'"]}))
        q = query_params(rsps.calls[0])["q"]
        assert "WHERE Id IN ('x\\') OR Name != \\'', 'back\\\\slash\\'')" in q
        # every quote inside the literals is escaped: removing escaped quotes leaves 4 delimiters
        literal_part = q.split("WHERE Id IN (", 1)[1].split(") ORDER BY", 1)[0]
        assert literal_part.replace("\\\\", "").replace("\\'", "").count("'") == 4

    @pytest.mark.parametrize("raw,expected", [(1000, 200), ("nope", 20), (0, 1), (-1, 1)])
    def test_read_limit_normalised(self, driver, rsps, run, raw, expected):
        rsps.add(responses.GET, f"{API}/query", json={"records": []})
        run(driver.read_entities("contact", filters={"limit": raw}))
        assert query_params(rsps.calls[0])["q"].endswith(f"LIMIT {expected}")

    @pytest.mark.parametrize("entity", ["unsafe", "notable"])
    def test_read_rejects_unsafe_object(self, driver, rsps, run, entity):
        with pytest.raises(ValueError, match="Unsafe Salesforce object name"):
            run(driver.read_entities(entity))
        assert len(rsps.calls) == 0

    def test_read_unknown_entity(self, driver, run):
        with pytest.raises(ValueError):
            run(driver.read_entities("ghost"))

    def test_read_http_error(self, driver, rsps, run):
        rsps.add(responses.GET, f"{API}/query", status=500)
        with pytest.raises(requests.exceptions.HTTPError):
            run(driver.read_entities("contact"))


class TestUpdateDelete:
    def test_update(self, driver, rsps, run):
        rsps.add(responses.PATCH, f"{API}/sobjects/Contact/003X", status=204)
        out = run(driver.update_entity("contact", "003X", {"first_name": "Grace", "Phone": "5", "zzz": 1}))
        assert json_body(rsps.calls[0]) == {"FirstName": "Grace", "Phone": "5"}
        assert out == {"id": "003X", "first_name": "Grace", "Phone": "5", "zzz": 1, "source": "salesforce"}

    def test_update_requires_fields(self, driver, rsps, run):
        with pytest.raises(ValueError, match="No writable Salesforce fields"):
            run(driver.update_entity("contact", "003X", {"nothing": 1}))
        assert len(rsps.calls) == 0

    def test_update_unsafe_object(self, driver, run):
        with pytest.raises(ValueError, match="Unsafe Salesforce object name"):
            run(driver.update_entity("unsafe", "1", {"a": 1}))

    def test_update_and_delete_encode_entity_id(self, driver, rsps, run):
        rsps.add(responses.PATCH, f"{API}/sobjects/Contact/..%2F..%2Fother%3Fx%3D1", status=204)
        rsps.add(responses.DELETE, f"{API}/sobjects/Contact/..%2F..%2Fother%3Fx%3D1", status=204)
        run(driver.update_entity("contact", "../../other?x=1", {"first_name": "x"}))
        assert run(driver.delete_entity("contact", "../../other?x=1")) is True
        for call in rsps.calls:
            assert call.request.url.endswith("/sobjects/Contact/..%2F..%2Fother%3Fx%3D1")

    def test_update_not_found(self, driver, rsps, run):
        rsps.add(responses.PATCH, f"{API}/sobjects/Contact/nope", status=404)
        with pytest.raises(requests.exceptions.HTTPError):
            run(driver.update_entity("contact", "nope", {"first_name": "x"}))

    def test_delete(self, driver, rsps, run):
        rsps.add(responses.DELETE, f"{API}/sobjects/Contact/003X", status=204)
        assert run(driver.delete_entity("contact", "003X")) is True

    def test_delete_non_204_is_false(self, driver, rsps, run):
        rsps.add(responses.DELETE, f"{API}/sobjects/Contact/003X", status=200)
        assert run(driver.delete_entity("contact", "003X")) is False

    def test_delete_not_found_raises(self, driver, rsps, run):
        rsps.add(responses.DELETE, f"{API}/sobjects/Contact/003X", status=404)
        with pytest.raises(requests.exceptions.HTTPError):
            run(driver.delete_entity("contact", "003X"))

    def test_delete_unsafe_object(self, driver, rsps, run):
        with pytest.raises(ValueError, match="Unsafe Salesforce object name"):
            run(driver.delete_entity("unsafe", "1"))
        assert len(rsps.calls) == 0
