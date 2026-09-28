# DAX Measures — Container Shipping KPIs

Paste these into Power BI Desktop after importing the star schema (`output/*.csv`
or `output/shipping_kpis.db`). Assumes tables named as in the CSV exports:
`fact_actual`, `fact_budget`, `dim_trade`, `dim_month`, `dim_cost_category`
(relate on `trade_id`, `month_id`, `cost_category_id`).

If you'd rather import the single flat view instead of the star schema for a
quick demo, `v_actual_vs_budget` already has most of these pre-calculated —
the measures below are the "do it properly in Power BI" version.

---

## Base measures

```DAX
Actual Cost =
SUM ( fact_actual[cost_actual_usd] )

Budget Cost =
SUM ( fact_budget[cost_budget_usd] )

-- teu_volume is stored at trade × month grain but repeated on every
-- cost-category row, so a plain SUM would count each TEU 7 times.
-- Take it once per trade/month instead.
Actual TEU =
SUMX (
    SUMMARIZE ( fact_actual, fact_actual[trade_id], fact_actual[month_id] ),
    CALCULATE ( MAX ( fact_actual[teu_volume] ) )
)

Budget TEU =
SUMX (
    SUMMARIZE ( fact_budget, fact_budget[trade_id], fact_budget[month_id] ),
    CALCULATE ( MAX ( fact_budget[teu_volume_budget] ) )
)
```

> Unit cost per TEU by cost category works the same way: filtering to one
> category still divides that category's cost by the lane's full TEU volume.

## Unit Cost per TEU

```DAX
Unit Cost per TEU (Actual) =
DIVIDE ( [Actual Cost], [Actual TEU] )

Unit Cost per TEU (Budget) =
DIVIDE ( [Budget Cost], [Budget TEU] )

Unit Cost Variance per TEU =
[Unit Cost per TEU (Actual)] - [Unit Cost per TEU (Budget)]

Unit Cost Variance per TEU % =
DIVIDE ( [Unit Cost Variance per TEU], [Unit Cost per TEU (Budget)] )
```

## Budget vs. Actual

```DAX
Cost Variance USD =
[Actual Cost] - [Budget Cost]

Cost Variance % =
DIVIDE ( [Cost Variance USD], [Budget Cost] )

Cost Variance Status =
VAR pct = [Cost Variance %]
RETURN
    SWITCH (
        TRUE (),
        ISBLANK ( pct ), "n/a",
        pct > 0.05, "Over Budget",
        pct < -0.05, "Under Budget",
        "On Track"
    )
```

## Deficit Planning (structural / run-rate view)

```DAX
-- Rolling 3-month variance (cost-weighted), to separate one-off noise from a
-- structural deficit trend (the kind of lane that needs a re-forecast).
-- Uses dim_month[month_seq] instead of built-in time intelligence, because
-- dim_month holds one row per month and can't be marked as a date table.
Cost Variance 3M Avg =
VAR CurSeq = MAX ( dim_month[month_seq] )
RETURN
    CALCULATE (
        [Cost Variance %],
        REMOVEFILTERS ( dim_month ),
        dim_month[month_seq] > CurSeq - 3,
        dim_month[month_seq] <= CurSeq
    )

Deficit Flag =
IF ( [Cost Variance 3M Avg] >= 0.08, "⚠ Structural Deficit", "OK" )

-- Full-year run-rate projection based on YTD actual pace, useful for
-- "if this continues, where do we land vs. annual budget" commentary.
Full Year Run Rate (Actual) =
VAR MonthsElapsed =
    DISTINCTCOUNT ( fact_actual[month_id] )
VAR MonthlyAvg =
    DIVIDE ( [Actual Cost], MonthsElapsed )
RETURN
    MonthlyAvg * 12
```

## Time intelligence helpers

```DAX
-- month_id is YYYYMM, so the same month last year is month_id - 100.
Actual Cost PY =
CALCULATE (
    [Actual Cost],
    REMOVEFILTERS ( dim_month ),
    TREATAS (
        SELECTCOLUMNS ( VALUES ( dim_month[month_id] ), "py", dim_month[month_id] - 100 ),
        dim_month[month_id]
    )
)

Actual Cost YoY % =
DIVIDE ( [Actual Cost] - [Actual Cost PY], [Actual Cost PY] )
```

---

### Suggested report pages

1. **Executive Overview** — card visuals for Actual vs. Budget cost, Unit
   Cost per TEU (actual vs. budget), overall variance %; trend line of
   monthly Actual vs. Budget cost.
2. **Budget vs. Actual by Trade Lane** — matrix (trade × cost category)
   with `Cost Variance %` conditional formatting (heatmap), so over-budget
   lanes jump out the way a standard-cost variance report would.
3. **Deficit Planning** — table filtered to `Deficit Flag = "⚠ Structural
   Deficit"`, with `Cost Variance 3M Avg` and `Full Year Run Rate (Actual)`
   next to the annual budget, to drive the re-forecast conversation.
4. **AI Commentary** — a text box pasting in `output/monthly_commentary.md`
   (rule-based bullets, or the LLM-polished section when run with `--llm`) as the
   narrative companion to the numbers — this is the "AI-assisted reporting
   workflow" demo piece.
