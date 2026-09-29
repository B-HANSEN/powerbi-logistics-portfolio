#!/bin/bash
# PreToolUse hook (Bash matcher):
# - `git commit` always requires an explicit confirmation, so a commit can't
#   ride through on loosely-inferred "session intent" from an earlier turn.
# - `git push` passes without a second prompt only if it directly follows a
#   `git commit` approved and run in this session within the last few
#   minutes (marker written by git-commit-marker.sh, a PostToolUse hook);
#   any other push asks first.
# - Both are denied outright if the test suite fails.

input=$(cat)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')
session=$(printf '%s' "$input" | jq -r '.session_id // "nosession"')

# git's global options may take a value (`git -C dir push`, `git -c k=v commit`)
opts='([[:space:]]+-[^[:space:]]+([[:space:]]+[^-[:space:]][^[:space:]]*)?)*'
commit_re="(^|[;&|]|[[:space:]])git${opts}[[:space:]]+commit([[:space:]]|\$)"
push_re="(^|[;&|]|[[:space:]])git${opts}[[:space:]]+push([[:space:]]|\$)"
# `gh repo create --push` / `gh repo sync` push too, without calling `git push`
gh_push_re='(^|[;&|]|[[:space:]])gh[[:space:]]+repo[[:space:]]+(sync|[^;&|]*[[:space:]]--push)([[:space:]]|$)'

marker="${TMPDIR:-/tmp}/claude-git-commit-approved-${session}"
# How long an approved `git commit` lets a following `git push` ride
# through without its own prompt, in seconds.
window=180

decide() {
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"%s","permissionDecisionReason":%s}}' \
    "$1" "$(printf '%s' "$2" | jq -Rs .)"
}

# Denies (and exits) if pytest fails on the current working tree.
require_tests() {
  local project_dir="${CLAUDE_PROJECT_DIR:-$PWD}"
  local py="$project_dir/.venv/bin/python"
  [ -x "$py" ] || py=python3
  local out
  if ! out=$(cd "$project_dir" && "$py" -m pytest -q tests/ 2>&1); then
    decide deny "$(printf 'git %s blocked: pytest failed on the current working tree. Fix it, then try again.\n\n%s' "$1" "$(printf '%s' "$out" | tail -c 4000)")"
    exit 0
  fi
}

if printf '%s' "$cmd" | grep -Eq "$commit_re"; then
  require_tests commit
  decide ask 'git commit always requires explicit confirmation. Did the CURRENT user message explicitly ask for a commit — not an earlier turn, not "same session momentum"? If not, stop and ask the user first instead of proceeding.'
  exit 0
fi

if printf '%s' "$cmd" | grep -Eq "$push_re|$gh_push_re"; then
  require_tests push
  if [ -f "$marker" ]; then
    mtime=$(stat -f %m "$marker" 2>/dev/null || stat -c %Y "$marker" 2>/dev/null || echo 0)
    if [ "$(( $(date +%s) - mtime ))" -lt "$window" ]; then
      # A commit was approved and run in this session moments ago — let the
      # push proceed through the normal permission flow (no second prompt).
      exit 0
    fi
  fi
  decide ask 'git push requires explicit confirmation unless it directly follows a git commit approved in this session. Did the CURRENT user message explicitly ask for a push? If not, stop and ask the user first.'
  exit 0
fi
