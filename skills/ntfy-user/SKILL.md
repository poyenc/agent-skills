---
name: ntfy-user
description: >
  Send an ntfy.sh notification to the user when you need to ask them a question.
  Use this skill immediately before asking the user anything in a long-running or AFK session —
  so the notification reaches them while they are away. Do NOT use for progress updates or
  task-complete summaries.
---

## When to invoke

Invoke whenever you are about to ask the user a question — any question that requires their input
to continue. This is the side-channel ping that accompanies that question.

**Do NOT invoke for:**
- Progress updates or task-complete summaries
- Anything that does not involve asking the user a question

## How to send

Set your private topic in `~/.claude/settings.json`:

```json
{ "env": { "NTFY_TOPIC": "your-private-topic-name" } }
```

Then send the notification before asking your question:

```bash
TOPIC="${NTFY_TOPIC:-agent-notify-topic}"
curl -s \
  -H "Title: Claude needs input" \
  -H "Priority: high" \
  -H "Tags: bell" \
  -d "YOUR_QUESTION_HERE" \
  "https://ntfy.sh/${TOPIC}"
```

The placeholder topic `agent-notify-topic` is **public** — set `NTFY_TOPIC` to your own private
topic before using this skill. Subscribe to that topic via the ntfy service (app or web UI).

## Message content

- **Title:** Always `Claude needs input` — consistent so the user can set a notification filter on it
- **Body:** One sentence, the actual question with enough context to answer without switching back.
  - Good: `What should the fallback behavior be when the config file is missing — error out or use defaults?`
  - Bad: `I need your help with something.`

## After sending

Present the question in the conversation immediately after. The notification is a side-channel
ping only — it does not replace the in-conversation question.
