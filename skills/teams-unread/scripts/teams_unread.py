#!/usr/bin/env python3
"""Teams Unread CLI — list unread Teams chats and retrieve full message
history from a specific chat, by reading the Teams desktop app's UI
Automation (UIA) accessibility tree.

Windows-only. Requires pywinauto and a running Teams desktop app.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time

from pywinauto import Desktop

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
# Message-list timestamps for messages older than yesterday appear as an
# unambiguous "YYYY M D AM/PM H:MM" form (space-separated, no slashes) —
# this is preferred over Teams' bare weekday-name duplicate ("Thursday
# AM 11:03") since it needs no day-of-week arithmetic relative to `now`.
_ABSOLUTE_DATE_TIME_RE = re.compile(r"^(\d{4}) (\d{1,2}) (\d{1,2}) (AM|PM) (\d{1,2}):(\d{2})$")


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

    m = _ABSOLUTE_DATE_TIME_RE.match(raw)
    if m:
        year, month, day, ampm, hour, minute = m.groups()
        date = dt.date(int(year), int(month), int(day))
        return _combine_date_and_ampm_time(date, ampm, hour, minute)

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


_MESSAGE_BOUNDARY_RE = re.compile(r"^.* by (.+)$")
# Teams emits both "Today at AM hh:mm." and a bare duplicate "Today AM hh:mm"
# (no "at", no period) for the same message; both "at" and the trailing
# period are optional here to tolerate either form.
_MESSAGE_TIMESTAMP_RE = re.compile(r"^(Yesterday|Today)(?: at)? (AM|PM) \d{1,2}:\d{2}\.?$")
# Companion to _ABSOLUTE_DATE_TIME_RE (resolve_timestamp): matches the same
# "YYYY M D AM/PM H:MM" node as it appears here, with its trailing period.
_MESSAGE_ABSOLUTE_DATE_RE = re.compile(r"^\d{4} \d{1,2} \d{1,2} (AM|PM) \d{1,2}:\d{2}\.$")
_MARKER = ("Button", "More message options")
_BODY_CONTROL_TYPES = ("Text", "ListItem")


def group_into_messages(nodes: list) -> list:
    """Segment a flat, document-order list of (control_type, text) tuples
    from the Message List UIA subtree into one record per message.

    Message boundaries are detected via the first line of each message
    block, which is always shaped like "<preview...> by <sender>"."""
    boundaries = [
        i for i, (ctype, text) in enumerate(nodes)
        if ctype == "Text" and _MESSAGE_BOUNDARY_RE.match(text)
    ]
    messages = []
    for idx, start in enumerate(boundaries):
        end = boundaries[idx + 1] if idx + 1 < len(boundaries) else len(nodes)
        messages.append(_parse_message_span(nodes[start:end]))
    return messages


def _parse_message_span(span: list) -> dict:
    sender = _MESSAGE_BOUNDARY_RE.match(span[0][1]).group(1)
    timestamp_raw = ""
    edited = False
    has_attachment = False
    body_parts: list = []
    seen_marker = False

    for ctype, text in span:
        if (ctype, text) == _MARKER:
            seen_marker = True
            continue

        if not seen_marker:
            if not timestamp_raw and (
                _MESSAGE_TIMESTAMP_RE.match(text) or _MESSAGE_ABSOLUTE_DATE_RE.match(text)
            ):
                timestamp_raw = text.rstrip(".")
            elif text == "Edited":
                edited = True
            elif "has an attachment" in text:
                has_attachment = True
            continue

        if "has an attachment" in text:
            has_attachment = True
            continue
        if ctype in _BODY_CONTROL_TYPES and text and text not in body_parts:
            body_parts.append(text)

    return {
        "sender": sender,
        "body": " ".join(body_parts),
        "timestamp_raw": timestamp_raw,
        "edited": edited,
        "has_attachment": has_attachment,
    }


def truncate_to_last_n(messages: list, n: int) -> list:
    if n <= 0 or len(messages) <= n:
        return messages
    return messages[-n:]


def format_retrieve_line(message: dict) -> str:
    tags = []
    if message["edited"]:
        tags.append("Edited")
    if message["has_attachment"]:
        tags.append("Attachment")
    tags_str = ",".join(tags) if tags else "-"
    return (
        f"{message['timestamp_iso']}\t{message['sender']}\t{tags_str}\t{message['body']}"
    )


def get_teams_window():
    """Locate the Teams desktop main window. Exits with a clear error if
    Teams isn't running or the window can't be found."""
    try:
        app = Desktop(backend="uia")
        # visible_only=False: pywinauto's visibility check can consider the
        # Teams window "not visible" when it's occluded/not foreground, even
        # though it's a real, running window we can still read from.
        # .wrapper_object() forces resolution now so lookup failures raise
        # here, inside this try block, instead of surfacing later at the
        # first attribute access on a lazy, unresolved WindowSpecification.
        return app.window(title_re=".*Microsoft Teams$", visible_only=False).wrapper_object()
    except Exception as exc:  # pywinauto raises varied COM/UIA exceptions; catch broadly
        print(f"Error: could not find Teams window ({exc})", file=sys.stderr)
        sys.exit(1)


def collect_unread_chat_items(window) -> list:
    """Return the raw accessible-name strings of every TreeItem in the
    chat-list Tree whose name starts with 'Unread message'. Read-only —
    does not select/click anything, so it does not mark anything as read."""
    tree = window.descendants(control_type="Tree")[0]
    items = tree.descendants(control_type="TreeItem")
    results = []
    for it in items:
        text = it.window_text()
        if text.startswith("Unread message"):
            results.append(text)
    return results


def select_chat(window, name_substring: str) -> str:
    """Find the chat-list TreeItem whose name contains name_substring and
    select it. Raises SystemExit with a clear message (listing candidates,
    if any) on zero or multiple matches — never guesses."""
    tree = window.descendants(control_type="Tree")[0]
    items = tree.descendants(control_type="TreeItem")
    matches = [it for it in items if name_substring in it.window_text()]

    if not matches:
        print(f"Error: no chat matched {name_substring!r}", file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        print(f"Error: {name_substring!r} matched multiple chats:", file=sys.stderr)
        for m in matches:
            print(f"  - {m.window_text()}", file=sys.stderr)
        sys.exit(1)

    matched_text = matches[0].window_text()
    matches[0].select()
    return matched_text


def _wait_for_message_list(window, timeout_seconds: float = 5.0):
    """Poll for the Message List group to appear after selecting a chat.
    Bounded wait, per spec — fails loudly rather than retrying forever."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        groups = [
            g for g in window.descendants(control_type="Group")
            if g.window_text() == "Message List"
        ]
        if groups:
            return groups[0]
        time.sleep(0.25)
    print("Error: Message List did not appear after selecting chat", file=sys.stderr)
    sys.exit(1)


def collect_message_list_nodes(window) -> list:
    """Wait for the Message List group to appear, then walk its descendants in
    document order, returning (control_type, text) tuples for every node
    with non-empty accessible text."""
    message_list = _wait_for_message_list(window)
    nodes = []
    for ctrl in message_list.descendants():
        try:
            text = ctrl.window_text()
        except Exception:
            continue
        if text and text.strip():
            nodes.append((ctrl.element_info.control_type, text))
    return nodes


def run_preview(args) -> None:
    window = get_teams_window()
    raw_items = collect_unread_chat_items(window)

    records = []
    for raw in raw_items:
        try:
            record = parse_chat_item(raw)
            record["timestamp_iso"] = resolve_timestamp(record["timestamp_raw"], dt.datetime.now())
        except ValueError as exc:
            print(f"warning: skipping unparseable chat item: {exc}", file=sys.stderr)
            continue
        records.append(record)

    records = filter_muted(records, exclude_muted=args.exclude_muted)
    records = sort_records_newest_first(records)

    if args.json:
        print(json.dumps(records, indent=2, ensure_ascii=False))
    else:
        for r in records:
            print(format_preview_line(r))


def run_retrieve(args) -> None:
    window = get_teams_window()
    select_chat(window, args.chat)
    nodes = collect_message_list_nodes(window)
    messages = group_into_messages(nodes)

    for m in messages:
        m["timestamp_iso"] = (
            resolve_timestamp(m["timestamp_raw"], dt.datetime.now())
            if m["timestamp_raw"] else ""
        )

    messages = truncate_to_last_n(messages, args.last)

    if args.json:
        print(json.dumps(messages, indent=2, ensure_ascii=False))
    else:
        for m in messages:
            print(format_retrieve_line(m))


def _positive_int(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError(f"--last must be a positive integer, got {value}")
    return n


def main() -> None:
    # Windows consoles often default stdout/stderr to cp1252, which can't
    # encode emoji/CJK/other characters that show up in real chat content
    # (including in error messages, e.g. select_chat's multi-match candidate
    # list). Force UTF-8 on both streams so output doesn't crash or mangle
    # on ordinary messages.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="List/retrieve unread Microsoft Teams chats via UI Automation"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_preview = sub.add_parser("preview", help="List unread 1:1/group chats (read-only)")
    p_preview.add_argument("--json", action="store_true")
    p_preview.add_argument("--exclude-muted", action="store_true")

    p_retrieve = sub.add_parser(
        "retrieve", help="Open a chat and pull recent messages (marks it read)"
    )
    p_retrieve.add_argument("--chat", required=True, help="Substring to match a chat name")
    p_retrieve.add_argument("--last", type=_positive_int, default=20, help="Max messages to return")
    p_retrieve.add_argument("--json", action="store_true")

    args = parser.parse_args()

    if args.command == "preview":
        run_preview(args)
    else:
        run_retrieve(args)


if __name__ == "__main__":
    main()
