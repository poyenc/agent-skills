#!/usr/bin/env bash
set -euo pipefail

# PreToolUse hook for the Agent tool.
# If the Agent call includes a team_name, prepend the team's
# initial-context.md to the prompt so teammates receive session
# context automatically.

INPUT=$(cat)

TEAM_NAME=$(printf '%s' "$INPUT" | jq -r '.tool_input.team_name // empty')
[[ -z "$TEAM_NAME" ]] && exit 0

CONTEXT_FILE="${CLAUDE_PROJECT_DIR}/.claude/teams/${TEAM_NAME}/initial-context.md"
[[ ! -f "$CONTEXT_FILE" ]] && exit 0

CONTEXT=$(cat "$CONTEXT_FILE")

# Rebuild tool_input with context prepended to prompt.
# updatedInput replaces the ENTIRE input object, so pass all fields through.
UPDATED=$(printf '%s' "$INPUT" | jq --arg ctx "$CONTEXT" \
  '.tool_input | .prompt = ($ctx + "\n\n---\n\n" + .prompt)')

printf '%s' "$UPDATED" | jq '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "allow",
    updatedInput: .
  }
}'
