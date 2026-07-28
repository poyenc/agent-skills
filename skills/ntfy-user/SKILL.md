---
name: ntfy-user
description: >
  Notify the user that their input is needed when you cannot continue without a decision or answer.
  Use this skill proactively in any long-running or AFK session whenever you are about to ask the
  user a question, need a decision between approaches, need approval for a risky action, or are
  blocked waiting for input. Invoke it BEFORE presenting the question so the notification reaches
  them while they are away. Do NOT use for informational updates or task-complete summaries —
  only when you genuinely need a response to continue.
---

## When to invoke

Use this skill immediately before any turn where you would otherwise ask the user something:

- You need to choose between two approaches and the decision is theirs
- You are blocked on a missing piece of information you cannot find yourself
- You need approval before a risky or irreversible action
- You have exhausted autonomous investigation and must escalate

Do NOT invoke for task-complete summaries, progress updates, or informational output.

## Backends

### ntfy (default)

ntfy.sh is a free push notification service with an iOS/Android app. Subscribe to your topic
in the ntfy app, then set `NTFY_TOPIC` in your environment.

```bash
TOPIC="${NTFY_TOPIC:-agent-notify-topic}"
curl -s \
  -H "Title: Claude needs input" \
  -H "Priority: high" \
  -H "Tags: bell" \
  -d "YOUR_QUESTION_HERE" \
  "https://ntfy.sh/${TOPIC}"
```

The default topic `agent-notify-topic` is **public** — anyone who knows it can read your
notifications. Set your own private topic:

```json
{ "env": { "NTFY_TOPIC": "your-private-topic-name" } }
```

### Adding other backends

To add Slack, Pushover, email, etc. — extend this skill with a new `##` section describing
the curl command for that backend, and add a detection condition (e.g. `if [ -n "$SLACK_WEBHOOK" ]`).
The `if/elif` pattern lets this skill automatically pick the right backend based on which env
vars are set.

**Detection order (implement in this order):**
1. `NTFY_TOPIC` → ntfy.sh
2. `SLACK_WEBHOOK` → Slack incoming webhook
3. `PUSHOVER_TOKEN` + `PUSHOVER_USER` → Pushover
4. (add yours here)

## Message content guidelines

- **Title/subject:** Always `Claude needs input` — consistent so the user can set a focus filter on it
- **Body:** The actual question in one sentence. Be specific — the user is away and needs enough
  context to answer without switching back to read the full conversation.
  - Good: `Should I force-push the branch or create a new one? Current branch has unpushed commits.`
  - Bad: `I need your help with something.`

## After sending

Proceed immediately to present the question in the conversation as normal. The notification is a
side-channel ping — it does not replace the in-conversation question.
