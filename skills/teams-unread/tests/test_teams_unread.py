import sys
from pathlib import Path
import datetime as dt
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import teams_unread as tu


def test_parse_chat_item_one_on_one_with_presence():
    raw = "Chat Bob Example Away Last message Done 9/2"
    result = tu.parse_chat_item(raw)
    assert result == {
        "chat_type": "Chat",
        "name": "Bob Example",
        "presence": "Away",
        "pinned": False,
        "muted": False,
        "unread": False,
        "last_sender": "",
        "last_message": "Done",
        "timestamp_raw": "9/2",
    }


def test_parse_chat_item_meeting_chat_no_muted_no_pinned():
    raw = "Meeting chat Standup Last message Carol Example: See you at 9 PM 08:47"
    result = tu.parse_chat_item(raw)
    assert result["chat_type"] == "Meeting chat"
    assert result["name"] == "Standup"
    assert result["muted"] is False
    assert result["pinned"] is False
    assert result["last_sender"] == "Carol Example"
    assert result["last_message"] == "See you at 9"
    assert result["timestamp_raw"] == "PM 08:47"


def test_parse_chat_item_unrecognized_raises():
    with pytest.raises(ValueError):
        tu.parse_chat_item("Some completely different string")


def test_parse_chat_item_group_chat_unread_pinned_muted():
    raw = (
        "Unread message Group chat Widgets Team Has pinned messages "
        "Last message Alice Example: Deploy is done Muted AM 10:52"
    )
    result = tu.parse_chat_item(raw)
    assert result == {
        "chat_type": "Group chat",
        "name": "Widgets Team",
        "presence": "",
        "pinned": True,
        "muted": True,
        "unread": True,
        "last_sender": "Alice Example",
        "last_message": "Deploy is done",
        "timestamp_raw": "AM 10:52",
    }


def test_resolve_timestamp_bare_time_today():
    now = dt.datetime(2026, 9, 4, 15, 0, 0)
    assert tu.resolve_timestamp("AM 10:52", now) == "2026-09-04T10:52:00"


def test_resolve_timestamp_bare_time_pm():
    now = dt.datetime(2026, 9, 4, 15, 0, 0)
    assert tu.resolve_timestamp("PM 12:23", now) == "2026-09-04T12:23:00"


def test_resolve_timestamp_yesterday():
    now = dt.datetime(2026, 9, 4, 15, 0, 0)
    assert tu.resolve_timestamp("Yesterday at AM 11:45.", now) == "2026-09-03T11:45:00"


def test_resolve_timestamp_today_with_at():
    now = dt.datetime(2026, 9, 4, 15, 0, 0)
    assert tu.resolve_timestamp("Today at PM 12:21.", now) == "2026-09-04T12:21:00"


def test_resolve_timestamp_month_day():
    now = dt.datetime(2026, 9, 4, 15, 0, 0)
    assert tu.resolve_timestamp("9/3", now) == "2026-09-03"


def test_resolve_timestamp_unrecognized_raises():
    now = dt.datetime(2026, 9, 4, 15, 0, 0)
    with pytest.raises(ValueError):
        tu.resolve_timestamp("not a timestamp", now)
