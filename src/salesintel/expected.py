"""Compute expected values for the Power BI measures directly in SQL.

After refreshing the semantic model, put these filters on a card/table and compare.
If DAX and SQL agree, the measure logic (return exclusion, FY boundaries, YoY) is right.
Writes ``reports/expected_measure_values.md``.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]

KEEP = "NOT f.is_returned"
BASE = "FROM fact_sales f JOIN dim_date d USING (date_key)"

CHECKS = [
    ("Total Revenue", "year = 2025", f"SELECT SUM(net_revenue) {BASE} WHERE {KEEP} AND d.year = 2025", "inr"),
    ("Total Revenue", "year = 2024", f"SELECT SUM(net_revenue) {BASE} WHERE {KEEP} AND d.year = 2024", "inr"),
    (
        "Revenue YoY %",
        "year = 2025",
        "SELECT SUM(net_revenue) FILTER (WHERE d.year = 2025) "
        f"/ SUM(net_revenue) FILTER (WHERE d.year = 2024) - 1 {BASE} WHERE {KEEP}",
        "pct",
    ),
    (
        "Orders",
        "year = 2025",
        f"SELECT COUNT(DISTINCT order_id) {BASE} WHERE {KEEP} AND d.year = 2025",
        "int",
    ),
    (
        "Avg Order Value",
        "year = 2025",
        f"SELECT SUM(net_revenue) / COUNT(DISTINCT order_id) {BASE} WHERE {KEEP} AND d.year = 2025",
        "inr",
    ),
    (
        "Gross Margin %",
        "year = 2025",
        f"SELECT (SUM(net_revenue) - SUM(cost)) / SUM(net_revenue) {BASE} WHERE {KEEP} AND d.year = 2025",
        "pct",
    ),
    (
        "Return Rate %",
        "year = 2025",
        f"SELECT AVG(CASE WHEN is_returned THEN 1 ELSE 0 END) {BASE} WHERE d.year = 2025",
        "pct2",
    ),
    (
        "Active Customers",
        "year = 2025",
        f"SELECT COUNT(DISTINCT customer_key) {BASE} WHERE {KEEP} AND d.year = 2025",
        "int",
    ),
    (
        "Revenue FYTD",
        "last date of FY2025 (31-Mar-2025)",
        f"SELECT SUM(net_revenue) {BASE} WHERE {KEEP} AND d.fiscal_year = 2025",
        "inr",
    ),
    (
        "Revenue YTD",
        "30-Jun-2025",
        f"SELECT SUM(net_revenue) {BASE} WHERE {KEEP} AND d.date BETWEEN '2025-01-01' AND '2025-06-30'",
        "inr",
    ),
    (
        "Category Rank = 1",
        "year = 2025",
        f"SELECT p.category {BASE} JOIN dim_product p USING (product_key) WHERE {KEEP} AND d.year = 2025 "
        "GROUP BY 1 ORDER BY SUM(net_revenue) DESC LIMIT 1",
        "text",
    ),
    (
        "Total Revenue (RLS: India Only)",
        "year = 2025",
        f"SELECT SUM(net_revenue) {BASE} JOIN dim_store s USING (store_key) "
        f"WHERE {KEEP} AND d.year = 2025 AND s.country = 'India'",
        "inr",
    ),
]


def fmt(v, kind: str) -> str:
    if kind == "inr":
        return f"₹ {float(v):,.0f}"
    if kind == "pct":
        return f"{float(v) * 100:.1f}%"
    if kind == "pct2":
        return f"{float(v) * 100:.2f}%"
    if kind == "int":
        return f"{int(v):,}"
    return str(v)


def run(db: Path = ROOT / "data" / "sales.duckdb") -> list[tuple[str, str, str]]:
    con = duckdb.connect(str(db), read_only=True)
    rows = [(m, ctx, fmt(con.execute(sql).fetchone()[0], k)) for m, ctx, sql, k in CHECKS]
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    lines = [
        "# Expected measure values (computed in SQL)",
        "",
        "Refresh the Power BI model, apply the filter context, and compare.",
        "",
        "| Measure | Filter context | Expected |",
        "|---|---|---:|",
    ]
    lines += [f"| {m} | {c} | {v} |" for m, c, v in rows]
    (out / "expected_measure_values.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rows


if __name__ == "__main__":
    for r in run():
        print(" | ".join(r))
