---
name: message-discipline
description: Use before sending ANY message to another agent/peer/subagent/teammate, in any role and at any point in a message chain -- starting a thread, replying to one, a lead notifying workers, or a worker reporting to whoever dispatched it. Gates on whether the message adds coordination or informational value and whether sending is required right now, not on recipient count. Trigger before a routine status update, a bare acknowledgment, a "got it, working on it" placeholder, a restatement of something already known, or any message in a notification fan-out. A message carrying a real finding, blocker, decision, or requested receipt still gets sent -- this only suppresses the ones that don't.
---

# Message discipline

## Why this exists

Every message between agents costs tokens to write and deliver, and -- when the chain eventually reaches the user's own session -- arrives as a mid-turn interruption that breaks into whatever they're doing. Agents routinely send messages that don't earn that cost: bare acknowledgments, "got it, starting now" placeholders, restating something the recipient already knows, or chiming in on a notification just to confirm receipt. This isn't about hierarchy -- a worker reporting up with a pure ack wastes exactly as much as a lead broadcasting down to workers who all ack back.

## The gate

Send only when the message adds informational or coordination value, or when an explicit receipt/status is required right now. Otherwise stay silent. If no reply is needed from the recipient, say so in the message.

Ask two questions before sending:

1. **Does this message carry substantive value?** A request, an assignment, a decision, a handoff, a cancellation, a blocker, a verified negative result ("not reproduced," "no conflict found" -- genuinely new evidence, not a guess), or a finding the recipient doesn't already have. It does NOT include a bare acknowledgment, a restatement of something the recipient already told you, a reflexive "still working on it" nobody asked for, or a pure transport receipt/heartbeat with no content of its own -- an explicitly requested receipt is question 2's job, not this one's.
2. **Is sending required right now?** Objective triggers: an immediate ack/status was explicitly requested, dependent work is actually blocked on your response right now, there's a deadline that needs an update now, it's a safety-stop, the messaging mechanism itself requires acknowledgment (a callback, a read receipt, or whatever that feature is called in the tool you're using), or there's observable evidence that silence would cause duplicate work or reassignment -- the sender stated they're waiting, a tool timeout/reassignment policy applies, or another task has an explicit dependency on hearing from you. Mere worry about seeming unresponsive doesn't count. Being asked a question obligates an eventual answer, not an immediate status -- it only makes sending required now once you actually have that answer; don't send "still looking into it" just because time has passed since you were asked. Ordinary completion of dispatched work is not, by itself, required-now -- see the Yes/No row. The absence of all of these means sending is not required right now, regardless of how the conversation feels.

A real blocker means the assigned work cannot proceed, even after reasonable local investigation, without the recipient's information, decision, access, or action. A real deadline is explicit or externally imposed, and sending now (rather than later) can actually change the outcome. A merely possible future dependency, a preference, or a wish for reassurance is neither -- don't treat those as required-now triggers.

| Value? | Required now? | Action |
|---|---|---|
| Yes | Yes | Send now. Covers an answer now owed, an active blocker, a request blocking dependent work, a handoff needed now, or time-sensitive evidence -- not every finding or request qualifies, see the Yes/No row. |
| Yes | No | Send if it completes requested work or materially changes the recipient's plan, decision, or awareness; otherwise batch it with your next substantive update instead of sending it alone. Ordinary task completions and verified-check results normally land here, not in Yes/Yes, unless a direct answer is now owed, dependent work is blocked, or a real deadline applies. |
| No | Yes | Send ONE minimal receipt/status -- do not hold an explicitly requested ack until the task is actually complete. Keep it to a line; this is not permission to narrate progress. |
| No | No | Stay silent. This covers acknowledging a notify, confirming you received an instruction with nothing yet to report, or replying to a broadcast just to say "acknowledged." |

## How to signal this to others

When you send a message that doesn't require a reply, say so explicitly so the recipient doesn't manufacture an ack out of politeness: "No need to reply unless this changes something or you're blocked by it." When you're on the receiving end of such a message, take that literally -- remain silent unless a later message carries substantive value (either Yes row above) or an immediate receipt/status becomes operationally required (No/Yes). Silence is correct only for No/No.

## Limitation

This is a judgment-based practice, not a technical interceptor -- nothing stops a messaging tool from sending regardless of whether this skill got consulted first. Skill/prompt discovery alone can't guarantee it fires before every send; if you want it applied every session without relying on discovery, reference it from whatever standing instruction file your harness reads on startup (CLAUDE.md, AGENTS.md, a system prompt, or equivalent) or from whatever mechanism actually dispatches the message.

## Examples

- **Pure ack** -- received a policy notification, nothing to add: stay silent (No/No).
- **Explicitly requested ack** -- sender said "confirm receipt, this one's safety-relevant": send one line confirming receipt (No/Yes).
- **Long task, no interim request** -- dispatched an investigation, no deadline pressure, nobody asked for a status: stay silent while working (No/No), then send the result once you have it -- ordinarily Yes/No (it completes the request), escalating to Yes/Yes only if a direct answer is now owed, dependent work is blocked on it, or a real deadline applies.
- **Outbound question** -- you need the recipient to make a decision before you can proceed: send it (Yes/Yes -- the request itself is the value, and dependent work is blocked on their answer).
- **Blocker** -- you hit something that stops progress: send it immediately (Yes/Yes).
- **Verified no-change** -- you were asked to check something and confirmed nothing's wrong ("no conflict found," "not reproduced"): send it -- this is genuine evidence, not a reflexive confirmation. Normally Yes/No (it completes the request); Yes/Yes only if the check was itself blocking someone or under a real deadline.
