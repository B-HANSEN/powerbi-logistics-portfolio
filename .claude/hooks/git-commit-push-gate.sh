#!/bin/bash
# PreToolUse hook (Bash matcher):
# - `git push` is always denied: the user pushes themselves.
# - `git commit` always requires an explicit confirmation, so a commit can't
#   ride through on loosely-inferred "session intent" from an earlier turn.
# - `git commit` is denied outright if the test suite fails.

input=$(cat)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')

# git's global options may take a value (`git -C dir push`, `git -c k=v commit`)
opts='([[:space:]]+-[^[:space:]]+([[:space:]]+[^-[:space:]][^[:space:]]*)?)*'
commit_re="(^|[;&|]|[[:space:]])git${opts}[[:space:]]+commit([[:space:]]|\$)"
push_re="(^|[;&|]|[[:space:]])git${opts}[[:space:]]+push([[:space:]]|\$)"

decide() {
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"%s","permissionDecisionReason":%s}}' \
    "$1" "$(printf '%s' "$2" | jq -Rs .)"
}

# `gh repo create --push` / `gh repo sync` push too, without calling `git push`
gh_push_re='(^|[;&|]|[[:space:]])gh[[:space:]]+repo[[:space:]]+(sync|[^;&|]*[[:space:]]--push)([[:space:]]|$)'

if printf '%s' "$cmd" | grep -Eq "$push_re|$gh_push_re"; then
  decide deny 'git push is never run by Claude in this repo — the user pushes themselves. Tell the user the commit is ready to push instead.'
  exit 0
fi

if printf '%s' "$cmd" | grep -Eq "$commit_re"; then
  project_dir="${CLAUDE_PROJECT_DIR:-$PWD}"
  py="$project_dir/.venv/bin/python"
  [ -x "$py" ] || py=python3
  if ! out=$(cd "$project_dir" && "$py" -m pytest -q tests/ 2>&1); then
    decide deny "$(printf 'git commit blocked: pytest failed on the current working tree. Fix it, then commit again.\n\n%s' "$(printf '%s' "$out" | tail -c 4000)")"
    exit 0
  fi
  decide ask 'git commit always requires explicit confirmation. Did the CURRENT user message explicitly ask for a commit — not an earlier turn, not "same session momentum"? If not, stop and ask the user first instead of proceeding.'
  exit 0
fi
