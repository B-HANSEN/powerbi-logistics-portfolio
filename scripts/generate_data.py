"""
generate_data.py
-----------------
Generates a realistic synthetic container-shipping controlling dataset
(trade lanes x months x standard cost categories) and writes it into a
SQLite database plus flat CSV exports for Power BI import.

Grain matches Hapag-Lloyd-style Operations/Controlling reporting:
- dim_trade:           trade lanes / services, grouped by region & head office
- dim_month:            24 months of history
- dim_cost_category:    standard liner cost buckets (Bunker, THC, Equipment, ...)
- fact_actual:          actual TEU volume + cost per trade/month/category
- fact_budget:          budget/standard-cost plan at the same grain

The synthetic data is designed to produce plausible, story-tellable patterns:
- Bunker costs trend up with a mild fuel-price shock mid-period
- Two Middle East lanes (Indian Subcontinent, East Africa) run a structural
  deficit vs. budget from month 7 onward (-> "Deficit Planning" narrative)
- Peak-season volume bump (Aug-Oct) against a flat TEU budget
- Equipment costs show seasonal repositioning spikes

Run:  python3 scripts/generate_data.py
Output: output/shipping_kpis.db, output/*.csv
"""

import sqlite3
import random
import csv
import os
from datetime import date

random.seed(42)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_PATH = os.path.join(ROOT, "sql", "schema.sql")
DB_PATH = os.path.join(ROOT, "output", "shipping_kpis.db")
OUT_DIR = os.path.join(ROOT, "output")

# ---------------------------------------------------------------------------
# Master data
# ---------------------------------------------------------------------------

TRADES = [
    # trade_code, trade_name, region, head_office
    ("FE-NE",  "Far East - North Europe",              "Asia-Europe",       "Hamburg"),
    ("FE-MED", "Far East - Mediterranean",              "Asia-Europe",       "Hamburg"),
    ("TA-3",   "Transatlantic",                         "Transatlantic",     "Hamburg"),
    ("TP-2",   "Transpacific",                          "Transpacific",      "Singapore"),
    ("ME-IS",  "Middle East - Indian Subcontinent",     "Middle East",       "Dubai"),
    ("ME-EAF", "Middle East - East Africa",             "Middle East",       "Dubai"),
    ("INTRA-ME","Intra-Middle East Feeder",             "Middle East",       "Dubai"),
]

COST_CATEGORIES = [
    # cost_category, cost_group
    ("Bunker",          "Ocean Cost"),
    ("Vessel Charter",  "Ocean Cost"),
    ("Port Charges",    "Terminal & Handling"),
    ("THC",             "Terminal & Handling"),
    ("Equipment",       "Equipment & Repositioning"),
    ("Feeder",          "Equipment & Repositioning"),
    ("Documentation",   "Admin"),
]

MONTH_NAMES = ["January","February","March","April","May","June",
               "July","August","September","October","November","December"]

N_MONTHS = 24
START_YEAR, START_MONTH = 2024, 10  # Oct 2024 .. Sep 2026

# Base monthly TEU volume per trade (approximate relative scale)
BASE_TEU = {
    "FE-NE": 42000, "FE-MED": 31000, "TA-3": 24000, "TP-2": 38000,
    "ME-IS": 15000, "ME-EAF": 9000, "INTRA-ME": 6000,
}

# Base unit cost (USD/TEU) per cost category (rough liner-industry order of magnitude)
BASE_UNIT_COST = {
    "Bunker": 145, "Vessel Charter": 210, "Port Charges": 58,
    "THC": 96, "Equipment": 47, "Feeder": 33, "Documentation": 9,
}

# Trades that are intentionally run "tight"/over-budget for the deficit-planning story
DEFICIT_TRADES = {"ME-IS", "ME-EAF"}


def month_sequence():
    months = []
    y, m = START_YEAR, START_MONTH
    for i in range(N_MONTHS):
        months.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def bunker_shock_factor(month_index):
    """Mild fuel-price shock ramping up around month 10-16 (Red Sea / Hormuz-style
    rerouting cost pressure), then partially easing off."""
    if month_index < 8:
        return 1.0 + 0.005 * month_index
    elif month_index < 16:
        return 1.04 + 0.012 * (month_index - 8)
    else:
        return 1.136 - 0.006 * (month_index - 16)


def seasonal_factor(month_num):
    """Peak-season volume bump (Aug-Oct restock for Western retail) and
    Chinese New Year dip (Jan-Feb)."""
    if month_num in (8, 9, 10):
        return 1.10
    if month_num in (1, 2):
        return 0.90
    return 1.0


def equipment_repositioning_spike(month_num):
    """Extra equipment cost around Chinese New Year (empty repositioning)."""
    return 1.35 if month_num in (1, 2, 12) else 1.0


def build_database():
    os.makedirs(OUT_DIR, exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    with open(SCHEMA_PATH, "r") as f:
        cur.executescript(f.read())

    # ---- dim_trade ----
    trade_ids = {}
    for i, (code, name, region, ho) in enumerate(TRADES, start=1):
        cur.execute(
            "INSERT INTO dim_trade (trade_id, trade_code, trade_name, region, head_office) VALUES (?,?,?,?,?)",
            (i, code, name, region, ho),
        )
        trade_ids[code] = i

    # ---- dim_cost_category ----
    cat_ids = {}
    for i, (cat, group) in enumerate(COST_CATEGORIES, start=1):
        cur.execute(
            "INSERT INTO dim_cost_category (cost_category_id, cost_category, cost_group) VALUES (?,?,?)",
            (i, cat, group),
        )
        cat_ids[cat] = i

    # ---- dim_month ----
    months = month_sequence()
    month_ids = {}
    for idx, (y, m) in enumerate(months, start=1):
        month_id = y * 100 + m
        period_date = date(y, m, 1).isoformat()
        quarter = f"Q{((m - 1) // 3) + 1}"
        cur.execute(
            "INSERT INTO dim_month (month_id, period_date, year, month, month_name, quarter, month_seq) "
            "VALUES (?,?,?,?,?,?,?)",
            (month_id, period_date, y, m, MONTH_NAMES[m - 1], quarter, idx),
        )
        month_ids[(y, m)] = month_id

    # ---- fact_budget & fact_actual ----
    for month_index, (y, m) in enumerate(months):
        month_id = month_ids[(y, m)]
        season = seasonal_factor(m)
        bunker_factor = bunker_shock_factor(month_index)
        equip_factor = equipment_repositioning_spike(m)

        for code, name, region, ho in TRADES:
            trade_id = trade_ids[code]
            base_teu = BASE_TEU[code]

            # budget volume grows ~2% over the horizon; actuals add seasonality + noise
            teu_budget = int(base_teu * (1.0 + 0.02 * (month_index / N_MONTHS)))
            teu_actual = int(teu_budget * season * random.uniform(0.94, 1.06))

            for cat, group in COST_CATEGORIES:
                cat_id = cat_ids[cat]
                base_unit = BASE_UNIT_COST[cat]

                # --- Budget (standard cost, stable plan set at year start) ---
                unit_budget = base_unit
                if cat == "Bunker":
                    unit_budget = base_unit * 1.08  # budget assumed a modest bunker increase
                cost_budget = round(unit_budget * teu_budget, 2)

                # --- Actual (reacts to fuel shocks, seasonality, deficit trades) ---
                unit_actual = base_unit
                if cat == "Bunker":
                    unit_actual = base_unit * bunker_factor
                elif cat == "Equipment":
                    unit_actual = base_unit * equip_factor
                elif cat == "Feeder" and code == "INTRA-ME":
                    unit_actual = base_unit * 1.15  # feeder-heavy intra-regional trade

                unit_actual *= random.uniform(0.96, 1.05)

                # structural deficit trades run persistently over standard cost
                if code in DEFICIT_TRADES and month_index >= 6:
                    unit_actual *= 1.10

                cost_actual = round(unit_actual * teu_actual, 2)

                cur.execute(
                    "INSERT INTO fact_budget (trade_id, month_id, cost_category_id, teu_volume_budget, cost_budget_usd) "
                    "VALUES (?,?,?,?,?)",
                    (trade_id, month_id, cat_id, teu_budget, cost_budget),
                )
                cur.execute(
                    "INSERT INTO fact_actual (trade_id, month_id, cost_category_id, teu_volume, cost_actual_usd) "
                    "VALUES (?,?,?,?,?)",
                    (trade_id, month_id, cat_id, teu_actual, cost_actual),
                )

    conn.commit()

    # ---- export CSVs (for direct Power BI "Get Data > Text/CSV" import) ----
    export_table_csv(conn, "dim_trade", "dim_trade.csv")
    export_table_csv(conn, "dim_month", "dim_month.csv")
    export_table_csv(conn, "dim_cost_category", "dim_cost_category.csv")
    export_table_csv(conn, "fact_actual", "fact_actual.csv")
    export_table_csv(conn, "fact_budget", "fact_budget.csv")
    export_view_csv(conn, "v_actual_vs_budget", "v_actual_vs_budget.csv")

    conn.close()
    print(f"Database built: {DB_PATH}")
    print(f"CSV exports written to: {OUT_DIR}")


def export_table_csv(conn, table, filename):
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table}")
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    path = os.path.join(OUT_DIR, filename)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)


def export_view_csv(conn, view, filename):
    export_table_csv(conn, view, filename)


if __name__ == "__main__":
    build_database()
