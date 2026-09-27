"""Run the SQL ETL (staging -> star schema), quality checks, and export the gold layer.

The gold CSVs in ``data/gold/`` are what the Power BI semantic model imports
(``DataFolder`` parameter in ``powerbi/SalesIntelligence.SemanticModel``).
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SQL = ROOT / "sql"
GOLD_TABLES = ["dim_date", "dim_customer", "dim_store", "dim_product", "fact_sales"]
# Demo mapping for dynamic row-level security (role "Country Manager").
SECURITY = [
    ("india.manager@example.com", "India"),
    ("uae.manager@example.com", "United Arab Emirates"),
    ("sg.manager@example.com", "Singapore"),
    ("apac.head@example.com", "India"),
    ("apac.head@example.com", "Singapore"),
]


class QualityCheckError(RuntimeError):
    pass


def run(
    raw: Path = ROOT / "data" / "raw" / "order_lines.csv",
    db: Path = ROOT / "data" / "sales.duckdb",
    gold: Path = ROOT / "data" / "gold",
) -> pd.DataFrame:
    """Build the star schema and return the quality-check results."""
    db.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db))
    con.execute("SET VARIABLE raw_path = ?", [str(raw)])
    for script in ["01_staging.sql", "02_dimensions.sql", "03_fact.sql"]:
        con.execute((SQL / script).read_text())
    checks = con.execute((SQL / "04_quality_checks.sql").read_text()).df()
    if (checks["failures"] > 0).any():
        raise QualityCheckError(checks.to_string(index=False))
    gold.mkdir(parents=True, exist_ok=True)
    for t in GOLD_TABLES:
        con.execute(f"COPY {t} TO '{gold / (t + '.csv')}' (HEADER)")
    pd.DataFrame(SECURITY, columns=["user_email", "country"]).to_csv(
        gold / "security_user_country.csv", index=False
    )
    con.close()
    return checks


if __name__ == "__main__":
    print(run().to_string(index=False))
