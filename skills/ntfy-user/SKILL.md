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

Configure via `~/.claude/settings.json`:

```json
{
  "env": {
    "NTFY_TOPIC": "your-private-topic-name",
    "NTFY_TITLE": "Agent needs input",
    "NTFY_PRIORITY": "default",
    "NTFY_URL": "https://ntfy.sh"
  }
}
```

| Variable | Default | Notes |
|----------|---------|-------|
| `NTFY_TOPIC` | `agent-notify-topic` | **Required.** The placeholder is public — set your own private topic. |
| `NTFY_TITLE` | `Agent needs input` | Notification title. Keep it consistent so you can set a filter on it. |
| `NTFY_PRIORITY` | `default` | ntfy priority: `min`, `low`, `default`, `high`, `urgent` |
| `NTFY_URL` | `https://ntfy.sh` | Base URL. Override for self-hosted ntfy instances. |
| `NTFY_TOKEN` | _(unset)_ | Bearer token for authenticated topics. Leave unset for public topics. |

Subscribe to your topic via the ntfy service (app or web UI).

Then send the notification before asking your question:

```bash
bash "<skill_base_dir>/scripts/ntfy.sh" "YOUR_QUESTION_HERE"
```

Replace `<skill_base_dir>` with the base directory shown at the top of this skill when it was loaded.

The script (`ntfy.sh`) reads all `NTFY_*` env vars and handles the curl invocation.

## Message content

- **Body:** One sentence, the actual question with enough context to answer without switching back.
  - Good: `What should the fallback behavior be when the config file is missing — error out or use defaults?`
  - Bad: `I need your help with something.`

## After sending

Present the question in the conversation immediately after. The notification is a side-channel
ping only — it does not replace the in-conversation question.
