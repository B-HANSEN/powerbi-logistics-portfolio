# Power BI / SQL Portfolio — Container Shipping KPIs

A small, self-contained portfolio project built to demo Controlling/Operations
reporting skills (Unit Cost per TEU, Budget-vs-Actual, Deficit Planning) plus
an AI-assisted reporting workflow, in an interview-shareable form.

Background: 14 years at Hapag-Lloyd in Operations/Controlling (incl. Region
Middle East), modeled here on typical liner-shipping standard-cost /
TRACO-style reporting logic — rebuilt with synthetic data so nothing here is
Hapag-Lloyd's real data or IP.

## What's in here

```
sql/
  schema.sql               star-schema DDL + v_actual_vs_budget view (SQLite dialect)
scripts/
  generate_data.py         builds the SQLite DB + CSV exports from synthetic data
  ai_reporting_workflow.py generates month-end variance commentary (rule-based,
                            optional LLM-polish step)
dax/
  measures.md               DAX measures to paste into Power BI Desktop
qlik/
  load_script.qvs           Qlik Sense load script (same data model)
  expressions.md            Qlik master-measure expressions (DAX counterparts)
tests/
  test_pipeline.py          sanity checks on generated data + commentary logic
output/                     generated on demand (git-ignored) — DB, CSVs, commentary.md
```

## Data model

Star schema:
- `dim_trade` — 7 trade lanes across Asia-Europe, Transatlantic, Transpacific
  and Middle East regions (mirroring a Region Middle East-style setup)
- `dim_month` — 24 months of history
- `dim_cost_category` — standard liner cost buckets: Bunker, Vessel Charter,
  Port Charges, THC, Equipment, Feeder, Documentation
- `fact_actual` / `fact_budget` — actual and budget/standard cost + TEU
  volume at trade × month × cost-category grain
- `v_actual_vs_budget` — a flat, ready-to-import view combining both facts
  with variance and unit-cost-per-TEU already calculated, for a fast Power BI
  demo without building the star-schema relationships by hand

The synthetic data is written to tell a specific, explainable story:
- a **peak-season volume effect** (Aug–Oct) that widens Budget-vs-Actual
  variance across nearly all lanes — a realistic "volume vs. flat budget"
  pattern
- a **structural deficit** on the two Middle East lanes (Indian Subcontinent,
  East Africa) that persists even outside peak season — the kind of pattern
  a Deficit Planning report is meant to catch and flag for re-forecast
- a **mild bunker cost shock** trending up mid-period (a stand-in for a
  Red Sea/Hormuz-style rerouting cost effect), partially offset by the
  budget already assuming some fuel increase

## Quickstart

The core scripts use only the Python standard library (`sqlite3`, `csv`), so
plain `python3` works. The optional `--llm` step needs the `anthropic` package:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # only needed for --llm (and pytest for tests)

python3 scripts/generate_data.py
# -> output/shipping_kpis.db, output/*.csv

python3 scripts/ai_reporting_workflow.py --month 202604
# -> prints + writes output/monthly_commentary.md
# (omit --month to use the latest month; add --llm to polish the narrative
#  with Claude if ANTHROPIC_API_KEY is set in your environment — never
#  required, the rule-based text works standalone)

python3 -m pytest tests/
# -> sanity checks on the generated data and the commentary logic
```

## Opening it in Power BI Desktop (free, no org account needed)

1. Run `generate_data.py` once to produce `output/*.csv`.
2. In Power BI Desktop: **Get Data → Text/CSV**, import the CSVs from
   `output/` (or **Get Data → SQLite database** pointing at
   `output/shipping_kpis.db` if you have a SQLite ODBC/connector set up —
   the CSV route is simpler and needs nothing extra installed).
3. For the star-schema route: import `dim_trade`, `dim_month`,
   `dim_cost_category`, `fact_actual`, `fact_budget` and set relationships
   on `trade_id`, `month_id`, `cost_category_id` (Model view).
   For the quick-demo route: just import `v_actual_vs_budget` — a single
   flat table with variance and unit-cost already computed.
4. Paste the measures from `dax/measures.md` into a new table
   (**Modeling → New Measure**).
5. Build report pages per the suggestions at the bottom of `dax/measures.md`
   (Executive Overview, Budget vs. Actual by Trade Lane, Deficit Planning,
   AI Commentary).

## Alternative: Qlik Sense (runs in the browser, works on macOS)

The same CSVs load into Qlik Cloud Analytics (30-day free trial, browser-based):

1. Run `generate_data.py`, upload `output/*.csv` to the **DataFiles** space.
2. Create an app, paste [`qlik/load_script.qvs`](qlik/load_script.qvs) into
   the **Data load editor**, reload. The script joins actual + budget into one
   fact table to avoid a synthetic key, and fixes the decimal separator.
3. Add the master measures from [`qlik/expressions.md`](qlik/expressions.md)
   and build the same four sheets.

## The "AI-assisted reporting workflow" piece

`scripts/ai_reporting_workflow.py` queries the latest (or a given) month,
flags variances above threshold, and writes management-ready commentary —
by default fully rule-based/deterministic (no API dependency, safe to run
and demo anywhere), with an optional `--llm` flag that hands the same
findings to Claude for a more polished narrative if an API key is present.
This is the piece to talk through in an interview as the "AI in the
reporting workflow" demo: the KPIs and variance detection are deterministic
and auditable (as Controlling numbers must be), and AI is used narrowly to
turn structured findings into readable prose — not to touch the numbers
themselves.

## Notes

- All data is synthetic, generated with a fixed random seed (`42`) for
  reproducibility — none of it is real Hapag-Lloyd data.
- `output/` is git-ignored; regenerate it any time with `generate_data.py`.
- Built and tested with Python 3.9+ — core scripts are standard library only;
  `anthropic` is needed just for the optional `--llm` step.
