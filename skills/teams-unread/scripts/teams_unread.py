#!/usr/bin/env python3
"""Teams Unread CLI — list unread Teams chats and retrieve full message
history from a specific chat, by reading the Teams desktop app's UI
Automation (UIA) accessibility tree.

Windows-only. Requires pywinauto and a running Teams desktop app.
"""

from __future__ import annotations

import datetime as dt
import re

_PRESENCE_VALUES = (
    "Available",
    "Away",
    "Offline",
    "Busy",
    "Do not disturb",
    "Be right back",
    "Unknown",
)

_CHAT_TYPE_PREFIXES = ("Group chat ", "Meeting chat ", "Chat ")

_TRAILING_TIMESTAMP_RE = re.compile(
    r"( (AM|PM) \d{1,2}:\d{2}| \d{1,2}/\d{1,2})$"
)


def parse_chat_item(raw: str) -> dict:
    """Parse one chat-list TreeItem's accessible name into a structured
    record. Raises ValueError if the string doesn't match the expected
    shape (chat type prefix + "Last message" marker + trailing timestamp)."""
    text = raw

    unread = text.startswith("Unread message ")
    if unread:
        text = text[len("Unread message "):]

    chat_type = None
    for prefix in _CHAT_TYPE_PREFIXES:
        if text.startswith(prefix):
            chat_type = prefix.strip()
            text = text[len(prefix):]
            break
    if chat_type is None:
        raise ValueError(f"Unrecognized chat type in: {raw!r}")

    if " Last message " not in text:
        raise ValueError(f"Missing 'Last message' marker in: {raw!r}")
    header, message_part = text.split(" Last message ", 1)

    ts_match = _TRAILING_TIMESTAMP_RE.search(message_part)
    if not ts_match:
        raise ValueError(f"Missing trailing timestamp in: {raw!r}")
    timestamp_raw = ts_match.group(0).strip()
    message_part = message_part[: ts_match.start()]

    muted = message_part.endswith(" Muted")
    if muted:
        message_part = message_part[: -len(" Muted")]

    if ": " in message_part:
        last_sender, last_message = message_part.split(": ", 1)
    else:
        last_sender, last_message = "", message_part

    pinned = header.endswith(" Has pinned messages")
    if pinned:
        header = header[: -len(" Has pinned messages")]

    presence = ""
    if chat_type == "Chat":
        for p in _PRESENCE_VALUES:
            suffix = " " + p
            if header.endswith(suffix):
                presence = p
                header = header[: -len(suffix)]
                break
            if header == p:
                presence = p
                header = ""
                break

    return {
        "chat_type": chat_type,
        "name": header.strip(),
        "presence": presence,
        "pinned": pinned,
        "muted": muted,
        "unread": unread,
        "last_sender": last_sender,
        "last_message": last_message.strip(),
        "timestamp_raw": timestamp_raw,
    }


_BARE_TIME_RE = re.compile(r"^(AM|PM) (\d{1,2}):(\d{2})$")
_YESTERDAY_RE = re.compile(r"^Yesterday(?: at)? (AM|PM) (\d{1,2}):(\d{2})\.?$")
_TODAY_RE = re.compile(r"^Today(?: at)? (AM|PM) (\d{1,2}):(\d{2})\.?$")
_MONTH_DAY_RE = re.compile(r"^(\d{1,2})/(\d{1,2})$")


def _combine_date_and_ampm_time(date, ampm: str, hour: str, minute: str) -> str:
    h = int(hour) % 12
    if ampm == "PM":
        h += 12
    return dt.datetime.combine(date, dt.time(h, int(minute))).isoformat()


def resolve_timestamp(raw: str, now: dt.datetime) -> str:
    """Normalize a Teams relative timestamp label to absolute ISO 8601,
    using ``now`` as the anchor for "today"/"yesterday". Raises ValueError
    for any format not recognized — never guesses."""
    raw = raw.strip()

    m = _BARE_TIME_RE.match(raw)
    if m:
        return _combine_date_and_ampm_time(now.date(), *m.groups())

    m = _YESTERDAY_RE.match(raw)
    if m:
        date = (now - dt.timedelta(days=1)).date()
        return _combine_date_and_ampm_time(date, *m.groups())

    m = _TODAY_RE.match(raw)
    if m:
        return _combine_date_and_ampm_time(now.date(), *m.groups())

    m = _MONTH_DAY_RE.match(raw)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        return dt.date(now.year, month, day).isoformat()

    raise ValueError(f"Unrecognized timestamp format: {raw!r}")


def filter_muted(records: list, exclude_muted: bool) -> list:
    if not exclude_muted:
        return records
    return [r for r in records if not r["muted"]]


def sort_records_newest_first(records: list) -> list:
    return sorted(records, key=lambda r: r["timestamp_iso"], reverse=True)


def format_preview_line(record: dict) -> str:
    flags = []
    if record["pinned"]:
        flags.append("Pinned")
    if record["muted"]:
        flags.append("Muted")
    flags_str = ",".join(flags) if flags else "-"
    sender = record["last_sender"] or "(unknown)"
    return (
        f"{record['timestamp_iso']}\t{record['chat_type']}\t{record['name']}\t"
        f"{flags_str}\t{sender}: {record['last_message']}"
    )
