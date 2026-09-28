# Qlik Sense Expressions — Shipping KPI Portfolio

Counterpart to [`dax/measures.md`](../dax/measures.md), for the data model
loaded by [`load_script.qvs`](load_script.qvs). Add them as **Master items →
Measures** so every sheet reuses the same definitions.

> Not yet verified in a live Qlik tenant — see TODO list.

## Base measures

```
Actual Cost        Sum(cost_actual_usd)
Budget Cost        Sum(cost_budget_usd)

// teu_volume repeats on every cost-category row -> take it once per trade/month
Actual TEU         Sum(Aggr(Max(teu_volume), trade_id, month_id))
Budget TEU         Sum(Aggr(Max(teu_volume_budget), trade_id, month_id))
```

## Unit Cost per TEU

```
Unit Cost per TEU (Actual)   Sum(cost_actual_usd) / Sum(Aggr(Max(teu_volume), trade_id, month_id))
Unit Cost per TEU (Budget)   Sum(cost_budget_usd) / Sum(Aggr(Max(teu_volume_budget), trade_id, month_id))
```

## Budget vs. Actual

```
Cost Variance USD    Sum(cost_actual_usd) - Sum(cost_budget_usd)
Cost Variance %      (Sum(cost_actual_usd) - Sum(cost_budget_usd)) / Sum(cost_budget_usd)

Cost Variance Status
If( (Sum(cost_actual_usd) - Sum(cost_budget_usd)) / Sum(cost_budget_usd) >  0.05, 'Over Budget',
If( (Sum(cost_actual_usd) - Sum(cost_budget_usd)) / Sum(cost_budget_usd) < -0.05, 'Under Budget',
    'On Track'))
```

Background color for the heatmap matrix (trade × cost category):

```
ColorMix2(
    RangeMax(-1, RangeMin(1, ((Sum(cost_actual_usd) - Sum(cost_budget_usd)) / Sum(cost_budget_usd)) / 0.15)),
    RGB(46,125,50), RGB(198,40,40), RGB(245,245,245))
```

## Deficit Planning (rolling 3 months)

Two variants, depending on the chart:

**In a table by trade lane** (window = the 3 months up to the latest selected
month; the month-field clears let the window reach outside the selection):

```
Cost Variance 3M
( Sum({<month_seq={">=$(=Max(month_seq)-2)<=$(=Max(month_seq))"},
        month_id=, period_date=, year=, month=, month_name=, quarter=>} cost_actual_usd)
- Sum({<month_seq={">=$(=Max(month_seq)-2)<=$(=Max(month_seq))"},
        month_id=, period_date=, year=, month=, month_name=, quarter=>} cost_budget_usd) )
/ Sum({<month_seq={">=$(=Max(month_seq)-2)<=$(=Max(month_seq))"},
        month_id=, period_date=, year=, month=, month_name=, quarter=>} cost_budget_usd)

Deficit Flag
If( [Cost Variance 3M] >= 0.08, '⚠ Structural Deficit', 'OK')
```

(`[Cost Variance 3M]` works as a column reference inside the same table;
elsewhere repeat the expression or store it as a master measure.)

**In a line chart with `period_date` on the axis** (sorted ascending):

```
RangeSum(Above(Sum(cost_actual_usd) - Sum(cost_budget_usd), 0, 3))
/ RangeSum(Above(Sum(cost_budget_usd), 0, 3))
```

## Run rate & prior year

```
Full Year Run Rate (Actual)
Sum(cost_actual_usd) / Count(DISTINCT month_id) * 12

// single selected month vs. the same month last year
Actual Cost PY
Sum({<month_seq={"$(=Max(month_seq)-12)"},
     month_id=, period_date=, year=, month=, month_name=, quarter=>} cost_actual_usd)

// on a month axis instead:  Above(Sum(cost_actual_usd), 12)
```

## Suggested sheets

Same four as the Power BI version: **Executive Overview** (KPI objects +
line chart), **Budget vs. Actual by Trade Lane** (pivot table with the
heatmap color expression), **Deficit Planning** (table with
`Deficit Flag`, `Cost Variance 3M`, run rate), **AI Commentary** (text
object with `output/monthly_commentary.md`).
