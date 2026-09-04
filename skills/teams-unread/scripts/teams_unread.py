#!/usr/bin/env python3
"""Teams Unread CLI — list unread Teams chats and retrieve full message
history from a specific chat, by reading the Teams desktop app's UI
Automation (UIA) accessibility tree.

Windows-only. Requires pywinauto and a running Teams desktop app.
"""

from __future__ import annotations

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
