"""Sanity checks: the generated data tells the intended story, and the
commentary logic flags what it should."""

import os
import sqlite3
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import ai_reporting_workflow as wf  # noqa: E402
import generate_data  # noqa: E402


@pytest.fixture(scope="module")
def conn():
    generate_data.build_database()
    c = sqlite3.connect(generate_data.DB_PATH)
    yield c
    c.close()


def scalar(conn, sql, *args):
    return conn.execute(sql, args).fetchone()[0]


def test_row_counts(conn):
    n = len(generate_data.TRADES) * generate_data.N_MONTHS * len(generate_data.COST_CATEGORIES)
    assert scalar(conn, "SELECT COUNT(*) FROM fact_actual") == n
    assert scalar(conn, "SELECT COUNT(*) FROM fact_budget") == n
    assert scalar(conn, "SELECT COUNT(*) FROM v_actual_vs_budget") == n


def test_month_seq_is_contiguous(conn):
    seqs = [r[0] for r in conn.execute("SELECT month_seq FROM dim_month ORDER BY month_id")]
    assert seqs == list(range(1, generate_data.N_MONTHS + 1))


def test_teu_constant_across_categories(conn):
    # TEU lives at trade x month grain; every cost-category row must carry the same value
    assert scalar(conn, """
        SELECT COUNT(*) FROM (
            SELECT trade_id, month_id FROM fact_actual
            GROUP BY trade_id, month_id HAVING COUNT(DISTINCT teu_volume) > 1
        )""") == 0


def test_deficit_trades_structurally_over_budget(conn):
    for code in generate_data.DEFICIT_TRADES:
        pct = scalar(conn, """
            SELECT (SUM(cost_actual_usd) - SUM(cost_budget_usd)) / SUM(cost_budget_usd)
            FROM v_actual_vs_budget v JOIN dim_month m ON m.month_id = v.month_id
            WHERE trade_code = ? AND m.month_seq > 6""", code)
        assert pct > wf.DEFICIT_FLAG_PCT, code


def test_commentary_flags_only_deficit_trades(conn):
    # off-peak month: in Aug-Oct the volume effect pushes most lanes over the
    # threshold too (total-cost variance doesn't separate volume from price yet)
    month_id = 202604
    rows = wf.fetch_variance_rows(conn, month_id)
    summary = wf.fetch_trade_summary(conn, month_id)
    window = wf.fetch_trade_summary(conn, month_id, wf.DEFICIT_WINDOW_MONTHS)
    findings, _, _ = wf.build_rule_based_findings(rows, summary, window, month_id)

    flagged = {f.split(":")[1].split("(")[0].strip() for f in findings if f.startswith("DEFICIT FLAG")}
    names = {code: name for code, name, _, _ in generate_data.TRADES}
    assert flagged == {names[c] for c in generate_data.DEFICIT_TRADES}


def test_trade_summary_counts_teu_once(conn):
    month_id = wf.get_latest_month(conn)
    teu = {t["trade_name"]: t["teu"] for t in wf.fetch_trade_summary(conn, month_id)}
    expected = dict(conn.execute("""
        SELECT t.trade_name, MAX(a.teu_volume) FROM fact_actual a
        JOIN dim_trade t ON t.trade_id = a.trade_id
        WHERE a.month_id = ? GROUP BY t.trade_name""", (month_id,)).fetchall())
    assert teu == expected
