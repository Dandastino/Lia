from datetime import datetime
from uuid import uuid4

from app.utils import MeetingFormatter, QueryFilterBuilder, normalize_user_id, parse_json_metadata


def test_normalize_user_id_variants():
    raw = uuid4()
    assert normalize_user_id(str(raw)) == str(raw)
    assert normalize_user_id(f"User_{raw}") == str(raw)
    assert normalize_user_id(None) is None
    assert normalize_user_id("") is None
    assert normalize_user_id("User_not-a-uuid") is None
    assert normalize_user_id("garbage") is None


def test_parse_json_metadata():
    assert parse_json_metadata('{"a": 1}') == {"a": 1}
    assert parse_json_metadata("{bad json") == {}
    assert parse_json_metadata({"a": 1}) == {"a": 1}
    assert parse_json_metadata(None) == {}


def test_meeting_formatter_datetime_and_defaults():
    now = datetime(2024, 5, 1, 12, 0, 0)
    result = MeetingFormatter.format_meeting_response(12, "T", "S", None, None, now, "src")
    assert result == {
        "id": "12",
        "title": "T",
        "summary": "S",
        "participants": [],
        "metadata": {},
        "created_at": now.isoformat(),
        "source": "src",
    }


def test_meeting_formatter_string_and_missing_dates():
    out = MeetingFormatter.format_meeting_response(None, None, "S", ["a"], {"k": 1}, "2024-01-01", "s")
    assert out["created_at"] == "2024-01-01"
    out = MeetingFormatter.format_meeting_response(None, None, "S", ["a"], {"k": 1}, None, "s")
    assert out["created_at"] is None and out["id"] is None


def test_filter_defaults_and_clamping():
    assert QueryFilterBuilder.parse_filters(None)["limit"] == 20
    assert QueryFilterBuilder.parse_filters({"limit": 1000})["limit"] == 50
    assert QueryFilterBuilder.parse_filters({"limit": -5})["limit"] == 1
    assert QueryFilterBuilder.parse_filters({"user_only": False})["user_only"] is False


def test_apply_date_filters():
    class Query:
        def __init__(self):
            self.calls = []

        def filter(self, expr):
            self.calls.append(expr)
            return self

    class Col:
        def __ge__(self, other):
            return ("ge", other)

        def __le__(self, other):
            return ("le", other)

    q = QueryFilterBuilder.apply_date_filters(Query(), {"start_date": "a", "end_date": "b"}, Col())
    assert q.calls == [("ge", "a"), ("le", "b")]
    q = QueryFilterBuilder.apply_date_filters(Query(), {}, Col())
    assert q.calls == []
