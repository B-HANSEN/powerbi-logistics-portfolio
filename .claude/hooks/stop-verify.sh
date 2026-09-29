#!/bin/bash
# Stop hook: run the test suite when code or schema changed this session, so
# a turn that edited scripts/, sql/ or tests/ doesn't end on faith. A turn
# with only doc/DAX edits exits immediately (nothing here can test
# those — they're verified in Power BI by the user).

project_dir="${CLAUDE_PROJECT_DIR:-$PWD}"
cd "$project_dir" || exit 0

# Stop hooks receive session JSON on stdin; nothing in it is needed here.
cat >/dev/null

tracked_changed=$(git diff --name-only HEAD 2>/dev/null)
untracked=$(git ls-files --others --exclude-standard 2>/dev/null)
changed=$(printf '%s\n%s\n' "$tracked_changed" "$untracked" | sed '/^$/d' | sort -u)

printf '%s\n' "$changed" | grep -Eq '^(scripts/|sql/|tests/|requirements\.txt)' || exit 0

py="$project_dir/.venv/bin/python"
[ -x "$py" ] || py=python3

if ! out=$("$py" -m pytest -q tests/ 2>&1); then
  printf '## pytest failed\n%s\n' "$out" | tail -c 6000 >&2
  exit 2
fi

exit 0
