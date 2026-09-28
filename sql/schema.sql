-- ============================================================================
-- Container Shipping KPI Portfolio – Star Schema
-- Author: Björn Hansen
-- Purpose: Demo data model for Power BI (Unit Cost per TEU, Budget vs Actual,
--          Deficit Planning) modeled on Hapag-Lloyd-style Operations/
--          Controlling reporting (TRACO / Standardkosten logic).
-- ============================================================================

-- ---------------------------------------------------------------------------
-- DIMENSION: Trade Lane / Service
-- ---------------------------------------------------------------------------
CREATE TABLE dim_trade (
    trade_id        INTEGER PRIMARY KEY,
    trade_code      TEXT NOT NULL,          -- e.g. 'FE-NE', 'TA-3', 'ME-IS'
    trade_name      TEXT NOT NULL,          -- e.g. 'Far East - North Europe'
    region          TEXT NOT NULL,          -- e.g. 'Asia-Europe', 'Middle East', 'Transatlantic'
    head_office     TEXT NOT NULL           -- controlling head-office, e.g. 'Hamburg', 'Dubai', 'Singapore'
);

-- ---------------------------------------------------------------------------
-- DIMENSION: Calendar / Month
-- ---------------------------------------------------------------------------
CREATE TABLE dim_month (
    month_id        INTEGER PRIMARY KEY,   -- YYYYMM, e.g. 202501
    period_date     TEXT NOT NULL,         -- ISO date of month start, 'YYYY-MM-01'
    year            INTEGER NOT NULL,
    month           INTEGER NOT NULL,      -- 1-12
    month_name      TEXT NOT NULL,         -- 'January'
    quarter         TEXT NOT NULL,         -- 'Q1'
    month_seq       INTEGER NOT NULL       -- 1..N running month index (for rolling-window DAX)
);

-- ---------------------------------------------------------------------------
-- DIMENSION: Cost Category (liner-shipping standard cost buckets)
-- ---------------------------------------------------------------------------
CREATE TABLE dim_cost_category (
    cost_category_id   INTEGER PRIMARY KEY,
    cost_category       TEXT NOT NULL,      -- 'Bunker', 'THC', 'Equipment', 'Feeder', 'Port Charges', 'Documentation'
    cost_group          TEXT NOT NULL       -- 'Ocean Cost', 'Terminal & Handling', 'Equipment & Repositioning', 'Admin'
);

-- ---------------------------------------------------------------------------
-- FACT: Actuals (per trade / month / cost category)
-- ---------------------------------------------------------------------------
CREATE TABLE fact_actual (
    fact_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id            INTEGER NOT NULL REFERENCES dim_trade(trade_id),
    month_id            INTEGER NOT NULL REFERENCES dim_month(month_id),
    cost_category_id    INTEGER NOT NULL REFERENCES dim_cost_category(cost_category_id),
    teu_volume          INTEGER NOT NULL,       -- lifted TEU per trade/month; repeated on every
                                                --   cost-category row, so never SUM it across categories
    cost_actual_usd     REAL NOT NULL           -- actual cost in USD for this category/period/trade
);

-- ---------------------------------------------------------------------------
-- FACT: Budget / Plan (same grain as actuals, for Budget-vs-Actual & Deficit Planning)
-- ---------------------------------------------------------------------------
CREATE TABLE fact_budget (
    fact_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id            INTEGER NOT NULL REFERENCES dim_trade(trade_id),
    month_id            INTEGER NOT NULL REFERENCES dim_month(month_id),
    cost_category_id    INTEGER NOT NULL REFERENCES dim_cost_category(cost_category_id),
    teu_volume_budget   INTEGER NOT NULL,       -- planned TEU (same trade/month repetition as above)
    cost_budget_usd     REAL NOT NULL           -- planned/standard cost in USD
);

CREATE INDEX idx_actual_trade_month  ON fact_actual(trade_id, month_id);
CREATE INDEX idx_budget_trade_month  ON fact_budget(trade_id, month_id);

-- ---------------------------------------------------------------------------
-- Convenience view: combined actual vs budget at trade/month grain (TEU + cost)
-- This is the natural import view for Power BI if a single flat table is
-- preferred over the star schema for a quick demo.
-- ---------------------------------------------------------------------------
CREATE VIEW v_actual_vs_budget AS
SELECT
    m.month_id,
    t.trade_code,
    t.trade_name,
    t.region,
    t.head_office,
    m.period_date,
    m.year,
    m.month,
    m.quarter,
    c.cost_category,
    c.cost_group,
    a.teu_volume,
    a.cost_actual_usd,
    b.teu_volume_budget,
    b.cost_budget_usd,
    (a.cost_actual_usd - b.cost_budget_usd)                                   AS cost_variance_usd,
    CASE WHEN b.cost_budget_usd = 0 THEN NULL
         ELSE (a.cost_actual_usd - b.cost_budget_usd) / b.cost_budget_usd END AS cost_variance_pct,
    CASE WHEN a.teu_volume = 0 THEN NULL ELSE a.cost_actual_usd / a.teu_volume END       AS unit_cost_per_teu_actual,
    CASE WHEN b.teu_volume_budget = 0 THEN NULL ELSE b.cost_budget_usd / b.teu_volume_budget END AS unit_cost_per_teu_budget
FROM fact_actual a
JOIN fact_budget b
  ON a.trade_id = b.trade_id AND a.month_id = b.month_id AND a.cost_category_id = b.cost_category_id
JOIN dim_trade t ON t.trade_id = a.trade_id
JOIN dim_month m ON m.month_id = a.month_id
JOIN dim_cost_category c ON c.cost_category_id = a.cost_category_id;
