# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

A liner-shipping controlling data model with three KPIs (Unit Cost per TEU, Budget vs. Actual, Deficit Planning): a SQLite star schema filled with synthetic data by Python, exported as CSVs for Power BI (DAX measures) and Qlik Sense (load script + expressions), plus a rule-based month-end commentary script with an optional Claude polish step. See `README.md` for the data story and import steps. `TODO.md` is a local, git-ignored work list.

The repo is public and must stay **personally and company-wise anonymous**: no personal names, employer names, career background, internal company terms, or "portfolio/interview/demo my skills" framing — in code, comments, docs, or commit messages.

## Commands

- Create/refresh the venv: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` (core scripts are stdlib-only and also run on plain `python3` ≥ 3.9; `anthropic` is only for `--llm`)
- Generate data: `.venv/bin/python scripts/generate_data.py` → `output/shipping_kpis.db` + `output/*.csv`
- Commentary: `.venv/bin/python scripts/ai_reporting_workflow.py [--month YYYYMM] [--llm]` → `output/monthly_commentary.md`
- Tests: `.venv/bin/python -m pytest tests/` (single test: `.venv/bin/python -m pytest tests/test_pipeline.py::test_row_counts`)

Power BI Desktop and Qlik Sense can't be run from here — DAX (`dax/measures.md`) and Qlik expressions (`qlik/`) are unverified until the user checks them in the real tool. Say so rather than claiming they work.

## Architecture

- **`sql/schema.sql` is the single source of the model.** `generate_data.py` executes it, then inserts rows; the CSV exports mirror the tables 1:1. A column added to the schema must also be inserted by the generator, and checked against `dax/measures.md`, `qlik/load_script.qvs` and `qlik/expressions.md`.
- **Grain trap:** `fact_actual` / `fact_budget` are at trade × month × cost-category grain, but `teu_volume` / `teu_volume_budget` are trade × month values repeated on every category row. Never `SUM` TEU across categories — take it once per trade/month (`MAX` in SQL, `SUMX(SUMMARIZE(...))` in DAX, `Aggr(Max(...))` in Qlik).
- **Months:** `dim_month` has one row per month (no daily calendar), so DAX built-in time intelligence doesn't apply; rolling windows use `month_seq` (1..N), prior year uses `month_id - 100`.
- **Deficit logic is defined three times** — `DEFICIT_FLAG_PCT` / `DEFICIT_WINDOW_MONTHS` in `ai_reporting_workflow.py`, `Deficit Flag` in DAX, and in Qlik. Keep thresholds and window in sync.
- **Numbers are deterministic** (`random.seed(42)`); the LLM step only rewrites finished findings into prose and must never compute or change figures. Tests in `tests/test_pipeline.py` pin the data story (deficit lanes, TEU grain, row counts) — a generator change that breaks them changes the story, not just the test.
- `output/` is generated and git-ignored.

## Git

-  git push only directly after a commit the user asked for and approved (a hook lets it through within 3 minutes of that commit); any other push needs an explicit request.
- `git commit` only when the current user message explicitly asks for it (a hook asks for confirmation every time).

## Commit messages

Use Conventional Commits: `<type>(<scope>): <description>`.

- `type` is one of `feat`, `fix`, `refactor`, `chore`, `docs`, `test`, `style`, `build`, `ci`, `perf`.
- `scope` is optional and names the area touched (e.g. `sql`, `dax`, `qlik`, `commentary`, `data`) — omit it if the change is repo-wide.
- `description` is lowercase, imperative mood, no trailing period (e.g. `fix(dax): count teu once per trade and month`).
- Add a body only when the _why_ isn't obvious from the diff; wrap at ~72 chars.
- Breaking changes get a `!` after the type/scope (`feat(sql)!: split teu into fact_volume`) plus a `BREAKING CHANGE:` footer explaining the migration (e.g. regenerate data, re-import in Power BI).

## Conventions

- Python: stdlib-first — don't add a dependency (e.g. pandas) for something `sqlite3`/`csv` already do. Keep `anthropic` a lazy, optional import.
- SQL stays in the SQLite dialect; keep `snake_case` names and the `dim_` / `fact_` / `v_` prefixes.
- Any change to generated data or KPI logic gets a test in `tests/`, and the README's data-story section updated if the story changes.
- Keep functions small and single-purpose; extract a helper before a function passes ~40 lines.
