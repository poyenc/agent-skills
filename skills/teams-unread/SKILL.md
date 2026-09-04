---
name: teams-unread
description: >
  List unread Microsoft Teams 1:1/group chats, or pull recent message
  history from a specific chat, by reading the Teams desktop app's
  accessibility tree. Use this skill when the user asks: "check unread
  Teams messages", "any unread chats", "what's new in Teams", "show me
  my Teams chat with X", "read the <chat name> chat", or similar.
  Requires the Teams desktop app to be running on Windows.
---

# Teams Unread

## Prerequisites
- Windows, with the Microsoft Teams desktop app running and signed in
- Python 3 with `pywinauto` installed

## Modes

### `preview` — list unread chats (read-only, safe to call anytime)

```
python <skill-dir>/scripts/teams_unread.py preview [--json] [--exclude-muted]
```

Does not open any chat or mark anything as read. Use this first, always,
before deciding whether to `retrieve` a specific chat.

Text output is one line per chat, tab-separated:
`<timestamp_iso>\t<chat_type>\t<name>\t<flags>\t<sender>: <last_message>`

### `retrieve` — pull full recent messages from one chat

```
python <skill-dir>/scripts/teams_unread.py retrieve --chat "<name substring>" [--last N] [--json]
```

**Caveat — this marks the chat as read in Teams.** Only call this once
you've decided (from `preview` output) that you actually want to open a
specific chat. Don't call it speculatively for every unread chat.

`--chat` matches by substring against the `name` field from `preview`. If
it matches zero or more than one chat, the script exits non-zero with an
error listing what it found — it will not guess.

Text output is one line per message, tab-separated, oldest first:
`<timestamp_iso>\t<sender>\t<flags>\t<body>`

## Known limitations

- Only 1:1/group/meeting chats — Teams channel posts are out of scope.
- No unread *count* is available, only a boolean unread flag per chat
  (Teams' accessibility tree doesn't expose a badge count).
- `retrieve`'s message parsing can commingle quoted-reply content into a
  message's body — Teams' accessibility tree doesn't cleanly separate a
  quote from the new message text in all cases.
- Depends on Teams' English-locale UI text; may break if Teams changes
  its accessibility labels or the client's display language changes.
- Older messages (more than a day old) can occasionally leave a stray
  trailing word (a date-divider like "Wednesday"/"Today"/"Yesterday", or
  a stray reaction-count number) tacked onto a message's `body` in
  `retrieve` mode — a cosmetic parsing artifact, not a functional break.
- On Windows, `preview`/`retrieve` output is forced to UTF-8 regardless
  of the console's default encoding, since real chat content (emoji, CJK,
  etc.) would otherwise crash on Windows' default cp1252 console encoding.
- Timestamps for messages older than yesterday resolve correctly only when
  Teams provides the message's absolute "YYYY M D AM/PM H:MM" form
  alongside the human-readable one — this is the form actually used, not
  weekday names, so this should be reliable, but is worth knowing if you
  ever see an unexpectedly empty timestamp in `retrieve` output.

## Presenting output

For `preview`, summarize unread chats grouped by whether they look
worth opening (unmuted, pinned, or from a person vs. a large group) —
don't just dump the raw lines unless the user asked for raw output.

For `retrieve`, present messages as a conversation, in the order returned
(oldest first).
