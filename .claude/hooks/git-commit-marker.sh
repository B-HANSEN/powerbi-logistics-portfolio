#!/bin/bash
# PostToolUse hook (Bash matcher): PostToolUse only fires after a tool
# succeeds, so a `git commit` reaching here was approved and actually
# created a commit. Drop a short-lived, session-scoped marker that
# git-commit-push-gate.sh reads to let a following `git push` through
# without a second confirmation.

input=$(cat)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')
session=$(printf '%s' "$input" | jq -r '.session_id // "nosession"')

opts='([[:space:]]+-[^[:space:]]+([[:space:]]+[^-[:space:]][^[:space:]]*)?)*'
commit_re="(^|[;&|]|[[:space:]])git${opts}[[:space:]]+commit([[:space:]]|\$)"

if printf '%s' "$cmd" | grep -Eq "$commit_re"; then
  touch "${TMPDIR:-/tmp}/claude-git-commit-approved-${session}"
fi
