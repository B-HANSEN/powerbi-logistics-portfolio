#!/bin/bash
# SessionStart hook (compact matcher): compaction keeps the prose summary
# but blurs concrete detail. Reprint the git state — branch, files changed
# but not committed, and the last few commits — so work resumes on the same
# files. Plain stdout is added to context for SessionStart hooks.

project_dir="${CLAUDE_PROJECT_DIR:-$PWD}"
cd "$project_dir" || exit 0
cat >/dev/null   # SessionStart sends JSON on stdin; nothing here needs it

branch=$(git branch --show-current 2>/dev/null)
[ -z "$branch" ] && exit 0   # not a git repo / detached HEAD

changed=$(git status --porcelain 2>/dev/null)
recent=$(git log --oneline -5 2>/dev/null)

printf '## Working state (post-compact)\n\n'
printf 'Branch: %s\n\n' "$branch"

if [ -n "$changed" ]; then
  printf 'Uncommitted changes:\n%s\n\n' "$changed"
else
  printf 'Working tree clean.\n\n'
fi

printf 'Recent commits:\n%s\n' "$recent"
