"""
ai_reporting_workflow.py
-------------------------
Demo of an "AI-assisted reporting workflow" on top of the shipping KPI
database: the kind of month-end commentary a Controlling team would attach
to a Budget-vs-Actual / Deficit-Planning report, generated automatically
instead of written by hand.

Two modes:
  1. Rule-based (default, no API key needed) — deterministic narrative
     built from variance thresholds. This is what runs out of the box and
     is what you'd show in an interview if you don't want to depend on
     a live API call.
  2. LLM-assisted (optional) — if ANTHROPIC_API_KEY is set in the
     environment, the rule-based findings are handed to Claude to turn
     into a polished, management-ready narrative. No key is ever
     hardcoded here; the script simply checks os.environ.

Run:  python3 scripts/ai_reporting_workflow.py [--month 202508] [--llm]
Output: output/monthly_commentary.md
"""

import argparse
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "output", "shipping_kpis.db")
OUT_PATH = os.path.join(ROOT, "output", "monthly_commentary.md")

VARIANCE_FLAG_PCT = 0.05   # flag any trade/category combo >5% off budget
DEFICIT_FLAG_PCT = 0.08    # flag trades running structurally over budget
DEFICIT_WINDOW_MONTHS = 3  # "structural" = over threshold on a rolling 3-month basis
                           # (same definition as the `Deficit Flag` DAX measure)


def get_latest_month(conn):
    cur = conn.cursor()
    cur.execute("SELECT MAX(month_id) FROM dim_month")
    return cur.fetchone()[0]


def fetch_variance_rows(conn, month_id):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT trade_name, region, cost_category, cost_group,
               teu_volume, cost_actual_usd, cost_budget_usd,
               cost_variance_usd, cost_variance_pct,
               unit_cost_per_teu_actual, unit_cost_per_teu_budget
        FROM v_actual_vs_budget
        WHERE month_id = ?
        ORDER BY ABS(cost_variance_pct) DESC
        """,
        (month_id,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_trade_summary(conn, month_id, window=1):
    """Trade-level actual vs. budget over the `window` months ending at month_id."""
    cur = conn.cursor()
    # teu_volume repeats on every cost-category row, so take it once per
    # trade/month (MAX) rather than summing it across categories.
    cur.execute(
        """
        SELECT trade_name, region,
               SUM(actual) AS actual, SUM(budget) AS budget, SUM(teu) AS teu
        FROM (
            SELECT trade_name, region, month_id,
                   SUM(cost_actual_usd) AS actual, SUM(cost_budget_usd) AS budget,
                   MAX(teu_volume) AS teu
            FROM v_actual_vs_budget
            WHERE month_id IN (
                SELECT month_id FROM dim_month WHERE month_id <= ?
                ORDER BY month_id DESC LIMIT ?
            )
            GROUP BY trade_name, region, month_id
        )
        GROUP BY trade_name, region
        ORDER BY SUM(actual) - SUM(budget) DESC
        """,
        (month_id, window),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def build_rule_based_findings(rows, trade_summary, trade_summary_window, month_id):
    findings = []

    over_budget_trades = [t for t in trade_summary if t["actual"] > t["budget"]]
    under_budget_trades = [t for t in trade_summary if t["actual"] <= t["budget"]]

    total_actual = sum(t["actual"] for t in trade_summary)
    total_budget = sum(t["budget"] for t in trade_summary)
    total_variance_pct = (total_actual - total_budget) / total_budget if total_budget else 0

    findings.append(
        f"Total cost for {month_id}: USD {total_actual:,.0f} actual vs. USD {total_budget:,.0f} "
        f"budget ({total_variance_pct:+.1%})."
    )

    # Largest trade/category deviations, over or under budget
    flagged = [r for r in rows if abs(r["cost_variance_pct"] or 0) >= VARIANCE_FLAG_PCT]
    flagged.sort(key=lambda r: abs(r["cost_variance_pct"]), reverse=True)

    for r in flagged[:5]:
        direction = "above" if r["cost_variance_pct"] > 0 else "below"
        findings.append(
            f"{r['trade_name']} / {r['cost_category']}: actual USD {r['cost_actual_usd']:,.0f} is "
            f"{abs(r['cost_variance_pct']):.1%} {direction} budget "
            f"(unit cost USD {r['unit_cost_per_teu_actual']:.0f}/TEU vs. budget USD {r['unit_cost_per_teu_budget']:.0f}/TEU)."
        )

    # Deficit planning: trades over budget on a rolling-window basis, not just this month
    month_pct = {
        t["trade_name"]: (t["actual"] - t["budget"]) / t["budget"] if t["budget"] else 0
        for t in trade_summary
    }
    for t in trade_summary_window:
        variance_pct = (t["actual"] - t["budget"]) / t["budget"] if t["budget"] else 0
        if variance_pct >= DEFICIT_FLAG_PCT:
            findings.append(
                f"DEFICIT FLAG: {t['trade_name']} ({t['region']}) is running {variance_pct:.1%} over budget "
                f"on a rolling {DEFICIT_WINDOW_MONTHS}-month basis ({month_pct[t['trade_name']]:+.1%} this month) "
                f"-- recommend reviewing standard cost assumptions or triggering a re-forecast."
            )

    return findings, over_budget_trades, under_budget_trades


def render_rule_based_markdown(month_id, findings):
    lines = [
        f"# Monthly Controlling Commentary -- Period {month_id}",
        "",
        "_Auto-generated from `v_actual_vs_budget` -- rule-based mode (no LLM call)._",
        "",
    ]
    for f in findings:
        prefix = "**" if f.startswith("DEFICIT FLAG") else ""
        suffix = "**" if f.startswith("DEFICIT FLAG") else ""
        lines.append(f"- {prefix}{f}{suffix}")
    lines.append("")
    lines.append("_Next step in a real workflow: attach this to the Power BI report as a narrative page, "
                  "or push as commentary text into the monthly deck._")
    return "\n".join(lines)


def try_llm_narrative(month_id, findings):
    """Optional: if ANTHROPIC_API_KEY is set, ask Claude to turn the rule-based
    findings into a polished management narrative. Falls back to None (caller
    keeps the rule-based text) if no key is present or the call fails."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic  # only imported if a key is actually present
    except ImportError:
        print("anthropic package not installed; run: pip install -r requirements.txt", file=sys.stderr)
        return None

    client = anthropic.Anthropic()
    bullet_text = "\n".join(f"- {f}" for f in findings)
    prompt = (
        "You are a shipping-line Controlling analyst writing a short, management-ready "
        f"monthly commentary for period {month_id}, based on these rule-based findings:\n\n"
        f"{bullet_text}\n\n"
        "Write 4-6 concise sentences, professional tone, no bullet points, "
        "suitable to paste directly into a Budget-vs-Actual report."
    )
    try:
        resp = client.beta.messages.create(
            model="claude-opus-5",
            max_tokens=16000,
            # on a safety-classifier decline, re-run server-side on Anthropic's recommended fallback model
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as e:
        print(f"LLM call failed, falling back to rule-based text: {e}", file=sys.stderr)
        return None
    if resp.stop_reason == "refusal":
        print("LLM declined the request, falling back to rule-based text.", file=sys.stderr)
        return None
    # the response may start with a thinking block, so collect only the text blocks
    text = "".join(block.text for block in resp.content if block.type == "text").strip()
    return text or None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", type=int, default=None, help="month_id, e.g. 202508 (defaults to latest)")
    parser.add_argument("--llm", action="store_true", help="attempt LLM-polished narrative if ANTHROPIC_API_KEY is set")
    args = parser.parse_args()

    if not os.path.exists(DB_PATH):
        sys.exit(f"Database not found at {DB_PATH} -- run scripts/generate_data.py first.")
    conn = sqlite3.connect(DB_PATH)
    month_id = args.month or get_latest_month(conn)

    rows = fetch_variance_rows(conn, month_id)
    if not rows:
        conn.close()
        sys.exit(f"No data for month {month_id} (expected a YYYYMM value present in dim_month).")
    trade_summary = fetch_trade_summary(conn, month_id)
    trade_summary_window = fetch_trade_summary(conn, month_id, DEFICIT_WINDOW_MONTHS)
    findings, over_budget, under_budget = build_rule_based_findings(
        rows, trade_summary, trade_summary_window, month_id
    )

    output_md = render_rule_based_markdown(month_id, findings)

    if args.llm:
        llm_text = try_llm_narrative(month_id, findings)
        if llm_text:
            output_md += "\n\n---\n\n## LLM-polished narrative\n\n" + llm_text

    with open(OUT_PATH, "w") as f:
        f.write(output_md)

    print(output_md)
    print(f"\nWritten to: {OUT_PATH}")
    conn.close()


if __name__ == "__main__":
    main()
