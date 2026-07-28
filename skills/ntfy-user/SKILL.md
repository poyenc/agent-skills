---
name: ntfy-user
description: >
  Send an ntfy.sh push notification to the user's phone when you are blocked on information only
  the user can provide and cannot continue without it. Use this skill immediately before asking
  the user a question in any long-running or AFK session — so the notification reaches them while
  they are away. Only invoke after you have already exhausted what you can find autonomously
  (code, docs, search, tests). Do NOT use for progress updates, task-complete summaries, or
  decisions you can reasonably make yourself.
---

## When to invoke

Invoke only when all three are true:

1. You need specific information to continue — a fact or constraint only the user knows
   (e.g. intended behavior, missing credential, business rule, ambiguous requirement).
2. You cannot find it autonomously — you have already checked the code, docs, tests, and git history.
3. You are about to ask the user — this notification is the side-channel ping that accompanies that question.

**Do NOT invoke for:**
- Decisions you can make with reasonable judgment and then report
- Progress updates or task-complete summaries
- Risky action approvals — those go through the permission system, not this skill

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
topic before using this skill. Subscribe to that topic in the ntfy iOS/Android app.

## Message content

- **Title:** Always `Claude needs input` — consistent so the user can set an iOS focus filter on it
- **Body:** One sentence, the actual question with enough context to answer without switching back.
  - Good: `What should the fallback behavior be when the config file is missing — error out or use defaults?`
  - Bad: `I need your help with something.`

## After sending

Present the question in the conversation immediately after. The notification is a side-channel
ping only — it does not replace the in-conversation question.
