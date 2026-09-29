---
description: Pre-commit review, scaled to the size of the change — diff captured once and handed to each subagent, correctness always, simplification for non-trivial diffs.
---

Run a pre-commit review of the current uncommitted changes (staged and unstaged), scaled to how big and what kind of a change it is. Do not run more subagents than the change warrants, and do not let each subagent independently re-derive the diff — capture it once yourself and hand it over.

1. Run `git status`, `git diff --stat`, and the full `git diff` (and `git diff --staged` if anything is staged) yourself. This is the one canonical snapshot every subagent below will review — capturing it once, here, means two subagents don't each spend a tool round-trip re-deriving the same thing, and guarantees they're all reviewing the identical snapshot rather than whatever the working tree looks like microseconds later.

2. Decide which agents are warranted:
   - **Trivial diff** (roughly under ~15 changed lines, and no logic change — e.g. a config tweak, a copy/text edit, a comment, a version bump): skip subagents entirely. Review it yourself, inline, in a couple of sentences. Stop here.
   - Otherwise, **correctness-reviewer** always runs — it's the cheapest insurance against a real bug slipping into a commit.
   - **simplification-reviewer** runs whenever the diff is more than a trivial tweak (i.e., whenever you didn't stop at the bullet above).

3. Build each subagent's prompt with the diff already embedded, instead of telling it to go fetch one:
   - For **correctness-reviewer** and **simplification-reviewer**: paste in the full diff from step 1 verbatim, and say so explicitly ("here is the diff already captured — do not re-run `git diff`").
   - In every case, remind the subagent it can still `Read` files beyond what's in the diff for surrounding context (e.g. to check existing conventions, or code outside the hunk) — you're only sparing it the redundant `git diff` call, not restricting what it can look at.

4. Invoke whichever agents you selected in a single message, in parallel, via the Agent tool — never sequentially. If only one agent qualifies, it's fine to invoke just that one.

5. Wait for all invoked agents to report back. Each reports through the `ReportFindings` tool.

6. Present the combined results grouped by agent, most-severe findings first within each group. If an invoked agent reported zero findings, say so briefly. Mention which agents you skipped and why (one line), so the user knows the review wasn't silently incomplete.

7. Do not apply any fixes yourself unless the user asks you to — this command is a review, not an auto-fix pass.
