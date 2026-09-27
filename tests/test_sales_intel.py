"""ETL, data-quality, semantic-model and customer-analytics tests."""

import re
from pathlib import Path

import duckdb
import pytest

from salesintel import customers, etl, generate

ROOT = Path(__file__).resolve().parents[1]
TMDL = ROOT / "powerbi" / "SalesIntelligence.SemanticModel" / "definition"


@pytest.fixture(scope="session")
def built():
    if not (ROOT / "data" / "raw" / "order_lines.csv").exists():
        generate.write(ROOT / "data" / "raw" / "order_lines.csv")
    return etl.run()


def test_quality_checks_all_zero(built):
    assert (built["failures"] == 0).all()


def test_star_schema_grain(built):
    con = duckdb.connect(str(ROOT / "data" / "sales.duckdb"), read_only=True)
    n_fact = con.execute("SELECT COUNT(*) FROM fact_sales").fetchone()[0]
    n_joined = con.execute("""SELECT COUNT(*) FROM fact_sales f
        JOIN dim_date USING (date_key) JOIN dim_customer USING (customer_key)
        JOIN dim_store USING (store_key) JOIN dim_product USING (product_key)""").fetchone()[0]
    assert n_fact == n_joined > 100_000
    fy = con.execute("SELECT fiscal_year FROM dim_date WHERE date = '2025-03-31'").fetchone()[0]
    assert fy == 2025


def test_every_tmdl_column_exists_in_gold(built):
    """The semantic model must match the gold CSV headers exactly."""
    for tmdl in (TMDL / "tables").glob("*.tmdl"):
        text = tmdl.read_text(encoding="utf-8")
        name = re.search(r"^table '?([^'\n]+)'?", text, re.M).group(1)
        csv = ROOT / "data" / "gold" / f"{name}.csv"
        if not csv.exists():
            continue  # calculated tables
        header = csv.read_text().splitlines()[0].split(",")
        cols = re.findall(r"^\tcolumn (\S+)", text, re.M)
        # Columns derived or dropped in the Power Query step are not in the CSV header.
        added = set(re.findall(r'Table\.AddColumn\(\w+, "([^"]+)"', text))
        removed = {
            c
            for group in re.findall(r"Table\.RemoveColumns\(\w+, \{([^}]*)\}", text)
            for c in re.findall(r'"([^"]+)"', group)
        }
        assert set(cols) - added == set(header) - removed, name


def test_measures_reference_existing_columns():
    text = (TMDL / "tables" / "fact_sales.tmdl").read_text(encoding="utf-8")
    text = text.split("\tpartition")[0]  # DAX only, not the Power Query source
    all_cols = set()
    for tmdl in (TMDL / "tables").glob("*.tmdl"):
        t = tmdl.read_text(encoding="utf-8")
        name = re.search(r"^table '?([^'\n]+)'?", t, re.M).group(1)
        all_cols |= {f"{name}[{c.strip(chr(39))}]" for c in re.findall(r"^\tcolumn (.+)$", t, re.M)}
    refs = set(re.findall(r"\b(\w+\[\w+\])", text))
    assert refs <= all_cols, refs - all_cols
    # Power BI Desktop writes single-word names unquoted (measure Orders), others quoted.
    measures = {m.strip("'") for m in re.findall(r"^\tmeasure ('[^']+'|\w+)", text, re.M)}
    used = set(re.findall(r"(?<![\w\]])\[([^\]]+)\]", text)) - {c.split("[")[1][:-1] for c in all_cols}
    assert used <= measures, used - measures


def test_relationships_point_to_real_columns():
    rel = (TMDL / "relationships.tmdl").read_text()
    for col in re.findall(r"Column: (\w+\.\w+)", rel):
        table, c = col.split(".")
        assert f"\tcolumn {c}\n" in (TMDL / "tables" / f"{table}.tmdl").read_text(encoding="utf-8")


def test_churn_model_beats_baseline(built):
    lines = customers.load()
    feats = customers.features(lines)
    feats = feats[feats["recency_days"] <= 365]
    y = customers.label(lines, feats)
    res = customers.train(feats, y)
    assert res["gradient_boosting"]["roc_auc"] > 0.75
    assert res["gradient_boosting"]["top20_lift"] > 1.5


def test_cohort_month0_is_100(built):
    table = customers.cohort_retention(customers.load())
    assert (table[0] == 100).all()
