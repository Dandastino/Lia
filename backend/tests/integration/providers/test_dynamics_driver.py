"""Dynamics 365 driver: all HTTP traffic is mocked with ``responses``."""
from __future__ import annotations

import pytest
import requests
import responses

from app.drivers.dynamics_driver import DynamicsDriver

from .helpers import calls_matching, decoded_url, form_body, json_body, query_params

TENANT = "11111111-2222-3333-4444-555555555555"
ORG = "https://acme.crm.dynamics.com"
TOKEN_URL = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token"
API = f"{ORG}/api/data/v9.2"

MAPPINGS = {
    "contact": {
        "table_name": "contacts",
        "id_column": "contactid",
        "column_mapping": {
            "first_name": "firstname",
            "last_name": "lastname",
            "email": "emailaddress1",
            "created_at": "createdon",
        },
        "table_columns": ["telephone1", "jobtitle"],
    },
    "account": {"table_name": "accounts", "column_mapping": {"name": "name"}},
    "weird": {
        "table_name": "contacts",
        "column_mapping": {"a": "bad field;", "b": "fullname", "created_at": "created on"},
    },
    "badid": {"table_name": "contacts", "id_column": "id eq 1", "column_mapping": {"a": "x"}},
    "unsafe": {"table_name": "contacts)/x", "column_mapping": {"a": "x"}},
    "notable": {"column_mapping": {"a": "x"}},
}


def make_config(**overrides):
    config = {
        "tenant_id": TENANT,
        "client_id": "cid",
        "client_secret": "csecret",
        "dynamics_url": ORG,
        "schema_mappings": MAPPINGS,
    }
    config.update(overrides)
    return config


def add_token(rsps, token="tok-1", **kwargs):  # noqa: S107
    rsps.add(responses.POST, TOKEN_URL, json={"access_token": token}, **kwargs)


@pytest.fixture
def driver(rsps):
    add_token(rsps)
    drv = DynamicsDriver(make_config())
    rsps.calls.reset()
    return drv


# ----------------------------------------------------------------- construction
class TestConstruction:
    def test_client_credentials_token(self, rsps):
        add_token(rsps, token="abc")
        drv = DynamicsDriver(make_config())
        assert drv.access_token == "abc"
        assert len(rsps.calls) == 1
        assert form_body(rsps.calls[0]) == {
            "client_id": "cid",
            "client_secret": "csecret",
            "scope": f"{ORG}/.default",
            "grant_type": "client_credentials",
        }

    def test_headers(self, driver):
        headers = driver._get_headers()
        assert headers["Authorization"] == "Bearer tok-1"
        assert headers["OData-MaxVersion"] == "4.0"
        assert headers["OData-Version"] == "4.0"

    @pytest.mark.parametrize("missing", ["tenant_id", "client_id", "client_secret", "dynamics_url"])
    def test_missing_credentials(self, rsps, missing):
        config = make_config()
        config.pop(missing)
        with pytest.raises(ValueError, match="credentials"):
            DynamicsDriver(config)
        assert len(rsps.calls) == 0

    def test_no_config(self):
        with pytest.raises(ValueError):
            DynamicsDriver(None)

    @pytest.mark.parametrize(
        "tenant",
        ["../evil", "a/b", "a?b=1", "tenant id", "-lead", ".dot", "a" * 300, "tenant#frag", "a\\b"],
    )
    def test_rejects_unsafe_tenant_id(self, rsps, tenant):
        with pytest.raises(ValueError, match="tenant_id is invalid"):
            DynamicsDriver(make_config(tenant_id=tenant))
        assert len(rsps.calls) == 0

    @pytest.mark.parametrize(
        "url",
        [
            "http://acme.crm.dynamics.com",
            "https://evil.example.com",
            "https://dynamics.com.evil.example",
            "https://evildynamics.com",
            "https://localhost",
            "ftp://acme.crm.dynamics.com",
        ],
    )
    def test_rejects_unsafe_dynamics_url(self, rsps, url):
        with pytest.raises(ValueError, match="dynamics_url must be an https URL"):
            DynamicsDriver(make_config(dynamics_url=url))
        assert len(rsps.calls) == 0  # the client secret must not be sent anywhere

    @pytest.mark.parametrize(
        "url",
        [
            "https://acme.crm.dynamics.com",
            "https://acme.crm4.dynamics.com",
            "https://acme.crm.dynamics.cn",
            "https://acme.crm.microsoftdynamics.us",
            "https://acme.crm.microsoftdynamics.de",
        ],
    )
    def test_accepts_dynamics_domains(self, rsps, url):
        add_token(rsps)
        assert DynamicsDriver(make_config(dynamics_url=url)).dynamics_url == url

    def test_accepts_dotted_tenant_domain(self, rsps):
        rsps.add(
            responses.POST,
            "https://login.microsoftonline.com/contoso.onmicrosoft.com/oauth2/v2.0/token",
            json={"access_token": "t"},
        )
        assert DynamicsDriver(make_config(tenant_id="contoso.onmicrosoft.com")).access_token == "t"

    def test_timeout_and_ssl_config(self, rsps):
        add_token(rsps)
        drv = DynamicsDriver(make_config(request_timeout_seconds=3, verify_ssl=False))
        assert drv.request_timeout_seconds == 3.0
        assert drv.verify_ssl is False
        kwargs = rsps.calls[0].request.req_kwargs
        assert kwargs["timeout"] == 3.0
        assert kwargs["verify"] is False

    @pytest.mark.parametrize("raw,expected", [("abc", 20.0), (None, 20.0), (0, 1.0), (-1, 1.0), ("4", 4.0)])
    def test_timeout_normalisation(self, rsps, raw, expected):
        add_token(rsps)
        assert DynamicsDriver(make_config(request_timeout_seconds=raw)).request_timeout_seconds == expected

    def test_defaults(self, rsps):
        add_token(rsps)
        drv = DynamicsDriver(make_config())
        assert drv.request_timeout_seconds == 20.0
        assert drv.verify_ssl is True


# ------------------------------------------------------------------ OAuth errors
class TestOAuth:
    def test_http_error(self, rsps):
        rsps.add(responses.POST, TOKEN_URL, json={"error": "invalid_client"}, status=401)
        with pytest.raises(Exception, match="Failed to obtain Dynamics access token"):
            DynamicsDriver(make_config())

    def test_timeout(self, rsps):
        rsps.add(responses.POST, TOKEN_URL, body=requests.exceptions.ConnectTimeout("slow"))
        with pytest.raises(Exception, match="Failed to obtain Dynamics access token"):
            DynamicsDriver(make_config())

    def test_missing_access_token(self, rsps):
        rsps.add(responses.POST, TOKEN_URL, json={})
        with pytest.raises(ValueError, match="access_token"):
            DynamicsDriver(make_config())


# ---------------------------------------------------------------- request layer
class TestRequest:
    def test_sends_headers_timeout_verify(self, driver, rsps):
        rsps.add(responses.GET, f"{API}/ping", json={})
        driver._request("GET", "/api/data/v9.2/ping")
        call = rsps.calls[0]
        assert call.request.headers["Authorization"] == "Bearer tok-1"
        assert call.request.headers["OData-Version"] == "4.0"
        assert call.request.req_kwargs["timeout"] == 20.0
        assert call.request.req_kwargs["verify"] is True

    def test_absolute_url(self, driver, rsps):
        rsps.add(responses.GET, f"{ORG}/next", json={})
        driver._request("GET", f"{ORG}/next")
        assert rsps.calls[0].request.url == f"{ORG}/next"

    def test_401_refresh_and_single_retry(self, driver, rsps):
        rsps.add(responses.GET, f"{API}/ping", status=401)
        add_token(rsps, token="tok-2")
        rsps.add(responses.GET, f"{API}/ping", json={"ok": 1})
        assert driver._request("GET", "/api/data/v9.2/ping").json() == {"ok": 1}
        assert [c.request.method for c in rsps.calls] == ["GET", "POST", "GET"]
        assert rsps.calls[2].request.headers["Authorization"] == "Bearer tok-2"
        assert driver.access_token == "tok-2"

    def test_second_401_raises(self, driver, rsps):
        rsps.add(responses.GET, f"{API}/ping", status=401)
        add_token(rsps, token="tok-2")
        rsps.add(responses.GET, f"{API}/ping", status=401)
        with pytest.raises(requests.exceptions.HTTPError):
            driver._request("GET", "/api/data/v9.2/ping")
        assert len(rsps.calls) == 3

    def test_retry_disabled(self, driver, rsps):
        rsps.add(responses.GET, f"{API}/ping", status=401)
        with pytest.raises(requests.exceptions.HTTPError):
            driver._request("GET", "/api/data/v9.2/ping", retry_on_401=False)
        assert len(rsps.calls) == 1

    def test_refresh_failure_propagates(self, driver, rsps):
        rsps.add(responses.GET, f"{API}/ping", status=401)
        rsps.add(responses.POST, TOKEN_URL, status=500)
        with pytest.raises(Exception, match="Failed to obtain Dynamics access token"):
            driver._request("GET", "/api/data/v9.2/ping")

    def test_server_error_not_retried(self, driver, rsps):
        rsps.add(responses.GET, f"{API}/ping", status=500)
        with pytest.raises(requests.exceptions.HTTPError):
            driver._request("GET", "/api/data/v9.2/ping")
        assert len(rsps.calls) == 1

    def test_timeout_propagates(self, driver, rsps):
        rsps.add(responses.GET, f"{API}/ping", body=requests.exceptions.ReadTimeout("slow"))
        with pytest.raises(requests.exceptions.ReadTimeout):
            driver._request("GET", "/api/data/v9.2/ping")


# --------------------------------------------------------------------- helpers
class TestHelpers:
    @pytest.mark.parametrize("raw,expected", [(5, 5), ("9", 9), (0, 1), (-2, 1), (999, 200), ("x", 20), (None, 20)])
    def test_normalize_limit(self, raw, expected):
        assert DynamicsDriver._normalize_limit(raw) == expected

    def test_normalize_limit_default(self):
        assert DynamicsDriver._normalize_limit("zzz", default=200) == 200

    @pytest.mark.parametrize(
        "value,ok",
        [("contacts", True), ("new_thing", True), ("_x", True), ("1a", False), ("a b", False), ("a)b", False),
         ("", False), (None, False), ("a'b", False)],
    )
    def test_is_safe_identifier(self, value, ok):
        assert DynamicsDriver._is_safe_identifier(value) is ok

    def test_escape_odata_string(self):
        assert DynamicsDriver._escape_odata_string("O'Brien") == "O''Brien"
        assert DynamicsDriver._escape_odata_string("''") == "''''"
        assert DynamicsDriver._escape_odata_string("plain") == "plain"

    def test_compact_http_error(self):
        resp = requests.Response()
        resp.status_code = 404
        resp._content = b"not\nfound " + b"y" * 600
        err = requests.exceptions.HTTPError("x", response=resp)
        msg = DynamicsDriver._compact_http_error(err)
        assert msg.startswith("HTTP 404: not found yyy")
        assert len(msg) <= len("HTTP 404: ") + 400
        assert DynamicsDriver._compact_http_error(RuntimeError("plain")) == "plain"

    @pytest.mark.parametrize(
        "header,expected",
        [
            (f"{API}/contacts(abc-123)", "abc-123"),
            ("", ""),
            (None, ""),
            ("  ", ""),
            ("https://x/contacts", "https://x/contacts"),
            ("weird(", "weird("),
        ],
    )
    def test_extract_entity_id(self, header, expected):
        resp = requests.Response()
        if header is not None:
            resp.headers["OData-EntityId"] = header
        assert DynamicsDriver._extract_entity_id(resp) == expected

    def test_collect_mapped_fields(self, driver):
        out = driver._collect_mapped_fields(
            {
                "first_name": "Ada",
                "email": None,
                "telephone1": "1",
                "jobtitle": None,
                "unknown": "x",
                "metadata": {"a": 1},
                "participants": [],
                "related_entities": {},
            },
            {"first_name": "firstname", "email": "emailaddress1", "bad": ["x"]},
            {"telephone1", "jobtitle", "metadata", "participants", "related_entities"},
        )
        assert out == {"firstname": "Ada", "telephone1": "1"}


# ------------------------------------------------------------------- meetings
class TestMeetings:
    def test_save_meeting(self, driver, rsps):
        rsps.add(responses.POST, f"{API}/phonecalls", status=204, headers={"OData-EntityId": f"{API}/phonecalls(pc-1)"})
        out = driver.save_meeting("u1", {"title": "Kickoff", "summary": "Notes", "participants": ["p"]})
        assert json_body(rsps.calls[0]) == {"subject": "Kickoff", "description": "Notes"}
        assert out == {
            "id": "pc-1",
            "title": "Kickoff",
            "summary": "Notes",
            "participants": ["p"],
            "metadata": {"dynamics_id": "pc-1"},
            "source": "dynamics",
        }

    def test_save_meeting_defaults(self, driver, rsps):
        rsps.add(responses.POST, f"{API}/phonecalls", status=204, headers={"OData-EntityId": f"{API}/phonecalls(pc-2)"})
        out = driver.save_meeting("u1", {"metadata": {"k": 1}})
        assert json_body(rsps.calls[0]) == {"subject": "Meeting", "description": ""}
        assert out["metadata"] == {"k": 1}

    def test_save_meeting_error(self, driver, rsps):
        rsps.add(responses.POST, f"{API}/phonecalls", body="denied", status=403)
        with pytest.raises(Exception, match="Failed to save meeting to Dynamics: HTTP 403: denied"):
            driver.save_meeting("u1", {"title": "x"})

    def test_save_meeting_401_retry(self, driver, rsps):
        rsps.add(responses.POST, f"{API}/phonecalls", status=401)
        add_token(rsps, token="tok-2")
        rsps.add(responses.POST, f"{API}/phonecalls", status=204, headers={"OData-EntityId": f"{API}/phonecalls(pc-3)"})
        assert driver.save_meeting("u1", {"title": "x"})["id"] == "pc-3"

    def test_history(self, driver, rsps):
        rsps.add(responses.GET, f"{API}/phonecalls", json={"value": [
            {"phonecallid": "p1", "subject": "s1", "description": "d1", "createdon": "2024-01-01"},
            {"phonecallid": "p2", "subject": "s2", "createdon": "2024-01-02"},
        ]})
        out = driver.get_meeting_history("u1")
        assert decoded_url(rsps.calls[0]) == (
            f"{API}/phonecalls?$select=phonecallid,subject,description,createdon&$top=20&$orderby=createdon desc"
        )
        assert out[0] == {
            "id": "p1", "title": "s1", "summary": "d1", "participants": [],
            "metadata": {"dynamics_id": "p1"}, "created_at": "2024-01-01", "source": "dynamics",
        }
        assert out[1]["summary"] == ""

    @pytest.mark.parametrize("raw,expected", [(3, 3), ("bad", 20), (5000, 200), (0, 1)])
    def test_history_limit(self, driver, rsps, raw, expected):
        rsps.add(responses.GET, f"{API}/phonecalls", json={"value": []})
        driver.get_meeting_history("u1", {"limit": raw})
        assert query_params(rsps.calls[0])["$top"] == str(expected)

    def test_history_owned_entity_ids(self, driver, rsps):
        rsps.add(responses.GET, f"{API}/phonecalls", json={"value": [
            {"phonecallid": "p1"}, {"phonecallid": "p2"}, {"phonecallid": "p3"},
        ]})
        out = driver.get_meeting_history("u1", {"owned_entity_ids": ["p3", "p1"]})
        assert [m["id"] for m in out] == ["p1", "p3"]

    def test_history_empty_owned_ids(self, driver, rsps):
        rsps.add(responses.GET, f"{API}/phonecalls", json={"value": [{"phonecallid": "p1"}]})
        assert len(driver.get_meeting_history("u1", {"owned_entity_ids": []})) == 1

    def test_history_error(self, driver, rsps):
        rsps.add(responses.GET, f"{API}/phonecalls", status=500, body="oops")
        with pytest.raises(Exception, match="Failed to retrieve meeting history from Dynamics: HTTP 500: oops"):
            driver.get_meeting_history("u1")

    def test_prepare_meeting_history_filters(self, driver):
        assert driver.prepare_meeting_history_filters("u", {"limit": 2}, [5]) == {
            "limit": 2, "owned_entity_ids": ["5"],
        }
        assert driver.prepare_meeting_history_filters("u") == {}


# --------------------------------------------------------------------- schema
class TestSchema:
    def test_schema_with_pagination(self, driver, rsps, run):
        rsps.add(responses.GET, f"{API}/$metadata", body="<edmx/>")
        rsps.add(responses.GET, f"{API}/EntityDefinitions", json={
            "value": [{"LogicalName": "account"}, {"LogicalName": "bad name"}],
            "@odata.nextLink": f"{API}/EntityDefinitions?$skiptoken=2",
        })
        rsps.add(responses.GET, f"{API}/EntityDefinitions", json={
            "value": [{"LogicalName": "contact"}, {"LogicalName": 7}, {"LogicalName": "broken"}],
        })
        rsps.add(responses.GET, f"{API}/EntityDefinitions(LogicalName='account')/Attributes", json={"value": [
            {"LogicalName": "accountid", "AttributeType": "Uniqueidentifier"},
            {"LogicalName": "name", "AttributeType": "String"},
        ]})
        rsps.add(responses.GET, f"{API}/EntityDefinitions(LogicalName='contact')/Attributes", json={"value": []})
        rsps.add(responses.GET, f"{API}/EntityDefinitions(LogicalName='broken')/Attributes", status=500)
        out = run(driver.get_schema_info())
        assert out == {"tables": [
            {
                "name": "account",
                "columns": ["accountid", "name"],
                "column_types": {"accountid": "Uniqueidentifier", "name": "String"},
            },
            {"name": "contact", "columns": [], "column_types": {}},
        ]}
        assert not calls_matching(rsps, contains="bad name")
        assert len(calls_matching(rsps, "GET", "/EntityDefinitions?")) == 2
        assert "$skiptoken=2" in decoded_url(calls_matching(rsps, "GET", "/EntityDefinitions?")[1])

    def test_schema_max_objects_stops_paging(self, rsps, run):
        add_token(rsps)
        drv = DynamicsDriver(make_config(schema_max_objects=1))
        rsps.add(responses.GET, f"{API}/$metadata", body="<edmx/>")
        rsps.add(responses.GET, f"{API}/EntityDefinitions", json={
            "value": [{"LogicalName": "account"}, {"LogicalName": "contact"}],
            "@odata.nextLink": f"{API}/EntityDefinitions?$skiptoken=2",
        })
        rsps.add(responses.GET, f"{API}/EntityDefinitions(LogicalName='account')/Attributes", json={"value": []})
        out = run(drv.get_schema_info())
        assert [t["name"] for t in out["tables"]] == ["account"]
        assert len(calls_matching(rsps, "GET", "/EntityDefinitions?")) == 1

    def test_schema_non_dict_payload(self, driver, rsps, run):
        rsps.add(responses.GET, f"{API}/$metadata", body="<edmx/>")
        rsps.add(responses.GET, f"{API}/EntityDefinitions", json=["unexpected"])
        assert run(driver.get_schema_info()) == {"tables": []}

    def test_schema_non_list_value(self, driver, rsps, run):
        rsps.add(responses.GET, f"{API}/$metadata", body="<edmx/>")
        rsps.add(responses.GET, f"{API}/EntityDefinitions", json={"value": "nope"})
        assert run(driver.get_schema_info()) == {"tables": []}

    def test_schema_metadata_failure_raises(self, driver, rsps, run):
        rsps.add(responses.GET, f"{API}/$metadata", status=500)
        with pytest.raises(requests.exceptions.HTTPError):
            run(driver.get_schema_info())


# ------------------------------------------------------------------------ CRUD
class TestCreate:
    def test_create(self, driver, rsps, run):
        rsps.add(responses.POST, f"{API}/contacts", status=204, headers={"OData-EntityId": f"{API}/contacts(c-1)"})
        payload = {"first_name": "Ada", "email": "a@b.c", "telephone1": "5", "unknown": 1, "metadata": {}, "x": None}
        out = run(driver.create_entity("contact", payload))
        assert json_body(rsps.calls[0]) == {"firstname": "Ada", "emailaddress1": "a@b.c", "telephone1": "5"}
        assert out == {"id": "c-1", **payload, "source": "dynamics"}

    def test_create_requires_fields(self, driver, rsps, run):
        with pytest.raises(ValueError, match="No writable Dynamics fields"):
            run(driver.create_entity("contact", {"nothing": 1}))
        assert len(rsps.calls) == 0

    def test_create_unknown_entity(self, driver, run):
        with pytest.raises(ValueError, match="No schema mapping"):
            run(driver.create_entity("ghost", {"a": 1}))

    @pytest.mark.parametrize("entity", ["unsafe", "notable"])
    def test_create_unsafe_entity_name(self, driver, rsps, run, entity):
        with pytest.raises(ValueError, match="Unsafe Dynamics entity name"):
            run(driver.create_entity(entity, {"a": 1}))
        assert len(rsps.calls) == 0

    def test_create_http_error(self, driver, rsps, run):
        rsps.add(responses.POST, f"{API}/contacts", status=400, json={"error": {"message": "bad"}})
        with pytest.raises(requests.exceptions.HTTPError):
            run(driver.create_entity("contact", {"first_name": "Ada"}))

    def test_create_after_token_expiry(self, driver, rsps, run):
        rsps.add(responses.POST, f"{API}/contacts", status=401)
        add_token(rsps, token="tok-2")
        rsps.add(responses.POST, f"{API}/contacts", status=204, headers={"OData-EntityId": f"{API}/contacts(c-2)"})
        assert run(driver.create_entity("contact", {"first_name": "A"}))["id"] == "c-2"

    def test_owner_attributes_do_not_break_create(self, driver, rsps, run):
        # Dynamics does not consume request_owner_*; scoping is enforced via owned_entity_ids on reads.
        driver.request_owner_id = "owner-guid"
        driver.request_owner_column = "ownerid"
        rsps.add(responses.POST, f"{API}/contacts", status=204, headers={"OData-EntityId": f"{API}/contacts(c-3)"})
        run(driver.create_entity("contact", {"first_name": "Ada"}))
        assert json_body(rsps.calls[0]) == {"firstname": "Ada"}


class TestRead:
    def test_read_builds_odata_query(self, driver, rsps, run):
        rsps.add(responses.GET, f"{API}/contacts", json={"value": [
            {"contactid": "c1", "firstname": "Ada", "lastname": "L", "emailaddress1": "a@b.c", "createdon": "d"},
        ]})
        out = run(driver.read_entities("contact", filters={"limit": 5}))
        assert decoded_url(rsps.calls[0]) == (
            f"{API}/contacts?$select=contactid,firstname,lastname,emailaddress1,createdon&$top=5&$orderby=createdon desc"
        )
        assert out == [{
            "id": "c1", "first_name": "Ada", "last_name": "L", "email": "a@b.c", "created_at": "d",
            "source": "dynamics",
        }]

    def test_read_default_id_column(self, driver, rsps, run):
        rsps.add(responses.GET, f"{API}/accounts", json={"value": [{"accountsid": "a1", "name": "Acme"}]})
        out = run(driver.read_entities("account"))
        assert decoded_url(rsps.calls[0]) == f"{API}/accounts?$select=accountsid,name&$top=20"
        assert out == [{"id": "a1", "name": "Acme", "source": "dynamics"}]

    def test_read_skips_unsafe_fields(self, driver, rsps, run):
        rsps.add(responses.GET, f"{API}/contacts", json={"value": []})
        run(driver.read_entities("weird"))
        assert decoded_url(rsps.calls[0]) == f"{API}/contacts?$select=contactsid,fullname&$top=20"

    def test_read_owner_scope_filter(self, driver, rsps, run):
        rsps.add(responses.GET, f"{API}/contacts", json={"value": []})
        run(driver.read_entities("contact", filters={"owned_entity_ids": ["g1", 22]}))
        url = decoded_url(rsps.calls[0])
        assert url.endswith("&$filter=contactid eq 'g1' or contactid eq '22'")

    def test_read_odata_injection_is_escaped(self, driver, rsps, run):
        rsps.add(responses.GET, f"{API}/contacts", json={"value": []})
        run(driver.read_entities("contact", filters={"owned_entity_ids": ["x' or contactid ne '"]}))
        assert query_params(rsps.calls[0])["$filter"] == "contactid eq 'x'' or contactid ne '''"

    def test_read_owner_filter_special_chars_stay_in_one_param(self, driver, rsps, run):
        rsps.add(responses.GET, f"{API}/contacts", json={"value": []})
        run(driver.read_entities("contact", filters={"owned_entity_ids": ["a&$top=9999"]}))
        params = query_params(rsps.calls[0])
        # an '&' inside the id must be percent-encoded, otherwise it would forge a new query option
        assert params["$top"] == "20"
        assert params["$filter"] == "contactid eq 'a&$top=9999'"

    @pytest.mark.parametrize("raw,expected", [(1000, 200), ("nope", 20), (0, 1)])
    def test_read_limit_normalised(self, driver, rsps, run, raw, expected):
        rsps.add(responses.GET, f"{API}/contacts", json={"value": []})
        run(driver.read_entities("contact", filters={"limit": raw}))
        assert query_params(rsps.calls[0])["$top"] == str(expected)

    @pytest.mark.parametrize("entity,message", [
        ("unsafe", "Unsafe Dynamics entity name"),
        ("notable", "Unsafe Dynamics entity name"),
        ("badid", "Unsafe Dynamics id column"),
    ])
    def test_read_rejects_unsafe_identifiers(self, driver, rsps, run, entity, message):
        with pytest.raises(ValueError, match=message):
            run(driver.read_entities(entity))
        assert len(rsps.calls) == 0

    def test_read_unknown_entity(self, driver, run):
        with pytest.raises(ValueError):
            run(driver.read_entities("ghost"))

    def test_read_http_error(self, driver, rsps, run):
        rsps.add(responses.GET, f"{API}/contacts", status=500)
        with pytest.raises(requests.exceptions.HTTPError):
            run(driver.read_entities("contact"))


class TestUpdateDelete:
    def test_update(self, driver, rsps, run):
        rsps.add(responses.PATCH, f"{API}/contacts(c-1)", status=204)
        out = run(driver.update_entity("contact", "c-1", {"first_name": "G", "telephone1": "9", "zzz": 1}))
        assert json_body(rsps.calls[0]) == {"firstname": "G", "telephone1": "9"}
        assert out == {"id": "c-1", "first_name": "G", "telephone1": "9", "zzz": 1, "source": "dynamics"}

    def test_update_requires_fields(self, driver, rsps, run):
        with pytest.raises(ValueError, match="No writable Dynamics fields"):
            run(driver.update_entity("contact", "c-1", {"nothing": 1}))
        assert len(rsps.calls) == 0

    def test_update_unsafe_entity(self, driver, run):
        with pytest.raises(ValueError, match="Unsafe Dynamics entity name"):
            run(driver.update_entity("unsafe", "1", {"a": 1}))

    def test_update_and_delete_encode_entity_id(self, driver, rsps, run):
        rsps.add(responses.PATCH, f"{API}/contacts(..%2F..%2Fother%3Fx%3D1)", status=204)
        rsps.add(responses.DELETE, f"{API}/contacts(..%2F..%2Fother%3Fx%3D1)", status=204)
        run(driver.update_entity("contact", "../../other?x=1", {"first_name": "x"}))
        assert run(driver.delete_entity("contact", "../../other?x=1")) is True
        for call in rsps.calls:
            assert call.request.url.endswith("/contacts(..%2F..%2Fother%3Fx%3D1)")

    def test_update_not_found(self, driver, rsps, run):
        rsps.add(responses.PATCH, f"{API}/contacts(missing)", status=404)
        with pytest.raises(requests.exceptions.HTTPError):
            run(driver.update_entity("contact", "missing", {"first_name": "x"}))

    def test_delete(self, driver, rsps, run):
        rsps.add(responses.DELETE, f"{API}/contacts(c-1)", status=204)
        assert run(driver.delete_entity("contact", "c-1")) is True

    def test_delete_non_204(self, driver, rsps, run):
        rsps.add(responses.DELETE, f"{API}/contacts(c-1)", status=200)
        assert run(driver.delete_entity("contact", "c-1")) is False

    def test_delete_not_found(self, driver, rsps, run):
        rsps.add(responses.DELETE, f"{API}/contacts(c-1)", status=404)
        with pytest.raises(requests.exceptions.HTTPError):
            run(driver.delete_entity("contact", "c-1"))

    def test_delete_unsafe_entity(self, driver, rsps, run):
        with pytest.raises(ValueError, match="Unsafe Dynamics entity name"):
            run(driver.delete_entity("unsafe", "1"))
        assert len(rsps.calls) == 0
