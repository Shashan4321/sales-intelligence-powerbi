"""Generate the Power BI report layout (PBIP, report.json) from code.

Two pages on the SalesIntelligence semantic model:

* Executive Sales Overview: KPI cards, monthly revenue trend, Country > State > City
  matrix, channel mix and category revenue, with a fiscal-year slicer.
* Customer Churn: churn KPIs, customers by risk band and RFM segment, cohort
  retention heatmap and the highest-risk customers.

Run ``python powerbi/build_report.py`` then open ``powerbi/SalesIntelligence.pbip`` in
Power BI Desktop and click Refresh. Layout lives in code so it can be reviewed in a diff.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

REPORT = Path(__file__).parent / "SalesIntelligence.Report"
THEME = "portfolio-theme.json"
THEME_SOURCE = Path(__file__).parent / "theme" / THEME
W, H = 1280, 720
NAVY, TEAL, WHITE = "#1F4E79", "#00A3A1", "#FFFFFF"

_ALIAS = {
    "fact_sales": "f",
    "dim_date": "d",
    "dim_store": "s",
    "dim_product": "p",
    "customer_scores": "c",
    "cohort_retention": "r",
}


def lit(value: str | bool | int) -> dict:
    """A literal for visual formatting properties."""
    if isinstance(value, bool):
        v = "true" if value else "false"
    elif isinstance(value, (int, float)):
        v = f"{value}D"
    else:
        v = f"'{value}'"
    return {"expr": {"Literal": {"Value": v}}}


def field(table: str, name: str, measure: bool = False) -> dict:
    kind = "Measure" if measure else "Column"
    return {
        "ref": f"{table}.{name}",
        "table": table,
        "select": {
            kind: {"Expression": {"SourceRef": {"Source": _ALIAS[table]}}, "Property": name},
            "Name": f"{table}.{name}",
        },
    }


def M(table: str, name: str) -> dict:  # noqa: N802
    return field(table, name, measure=True)


def C(table: str, name: str) -> dict:  # noqa: N802
    return field(table, name)


def visual(
    name: str,
    vtype: str,
    x: int,
    y: int,
    w: int,
    h: int,
    roles: dict[str, list[dict]] | None = None,
    title: str | None = None,
    objects: dict | None = None,
    order_by: tuple[dict, str] | None = None,
) -> dict:
    roles = roles or {}
    fields = [f for fs in roles.values() for f in fs]
    unique = list({f["ref"]: f for f in fields}.values())
    single: dict = {"visualType": vtype, "drillFilterOtherVisuals": True}
    if unique:
        tables = sorted({f["table"] for f in unique})
        query: dict = {
            "Version": 2,
            "From": [{"Name": _ALIAS[t], "Entity": t, "Type": 0} for t in tables],
            "Select": [f["select"] for f in unique],
        }
        if order_by:
            f, direction = order_by
            expr = {k: v for k, v in f["select"].items() if k != "Name"}
            query["OrderBy"] = [{"Direction": 1 if direction == "asc" else 2, "Expression": expr}]
        single["prototypeQuery"] = query
        single["projections"] = {role: [{"queryRef": f["ref"]} for f in fs] for role, fs in roles.items()}
    if objects:
        single["objects"] = objects
    vc_objects: dict = {}
    if title:
        vc_objects["title"] = [{"properties": {"show": lit(True), "text": lit(title)}}]
    if vc_objects:
        single["vcObjects"] = vc_objects
    config = {
        "name": name,
        "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": 0, "width": w, "height": h}}],
        "singleVisual": single,
    }
    return {
        "x": x,
        "y": y,
        "z": 0,
        "width": w,
        "height": h,
        "config": json.dumps(config),
        "filters": "[]",
    }


def textbox(name: str, x: int, y: int, w: int, h: int, runs: list[tuple[str, dict]]) -> dict:
    paragraphs = [{"textRuns": [{"value": text, "textStyle": style}]} for text, style in runs]
    v = visual(name, "textbox", x, y, w, h, objects={"general": [{"properties": {"paragraphs": paragraphs}}]})
    config = json.loads(v["config"])
    config["singleVisual"]["vcObjects"] = {
        "background": [{"properties": {"show": lit(False)}}],
        "dropShadow": [{"properties": {"show": lit(False)}}],
    }
    v["config"] = json.dumps(config)
    return v


def header(prefix: str, title: str, question: str) -> dict:
    return textbox(
        f"{prefix}_title",
        20,
        4,
        980,
        76,
        [
            (title, {"fontSize": "20pt", "fontWeight": "bold", "color": NAVY}),
            (question, {"fontSize": "11pt", "color": "#605E5C"}),
        ],
    )


def card(name: str, x: int, measure: dict, label: str, y: int = 86) -> dict:
    # The visual title carries the label, so the card's own category label is hidden.
    objects = {"categoryLabels": [{"properties": {"show": lit(False)}}]}
    return visual(name, "card", x, y, 300, 94, {"Values": [measure]}, title=label, objects=objects)


def fy_slicer(name: str, default_fy: int) -> dict:
    """Fiscal-year dropdown, pre-selected so YoY compares one full year with the previous one."""
    fy = {"Column": {"Expression": {"SourceRef": {"Source": "d"}}, "Property": "fiscal_year"}}
    selection = {
        "Version": 2,
        "From": [{"Name": "d", "Entity": "dim_date", "Type": 0}],
        "Where": [
            {
                "Condition": {
                    "In": {"Expressions": [fy], "Values": [[{"Literal": {"Value": f"{default_fy}L"}}]]}
                }
            }
        ],
    }
    return visual(
        name,
        "slicer",
        1040,
        14,
        220,
        60,
        {"Values": [C("dim_date", "fiscal_year")]},
        objects={
            "data": [{"properties": {"mode": lit("Dropdown")}}],
            "header": [{"properties": {"show": lit(False)}}],
            "general": [{"properties": {"filter": {"filter": selection}}}],
        },
        title="Fiscal year (Apr-Mar)",
    )


def heatmap(measure_ref: str) -> dict:
    """Background colour scale for matrix values (white -> navy)."""
    return {
        "values": [
            {
                "properties": {
                    "backColor": {
                        "solid": {
                            "color": {
                                "expr": {
                                    "FillRule": {
                                        "Input": {
                                            "Measure": {
                                                "Expression": {"SourceRef": {"Entity": "cohort_retention"}},
                                                "Property": measure_ref,
                                            }
                                        },
                                        "FillRule": {
                                            "linearGradient2": {
                                                "min": {"color": {"Literal": {"Value": "'#FFFFFF'"}}},
                                                "max": {"color": {"Literal": {"Value": f"'{NAVY}'"}}},
                                                "nullColoringStrategy": {
                                                    "strategy": {"Literal": {"Value": "'asZero'"}}
                                                },
                                            }
                                        },
                                    }
                                }
                            }
                        }
                    }
                },
                "selector": {
                    "data": [{"dataViewWildcard": {"matchingOption": 1}}],
                    "metadata": f"cohort_retention.{measure_ref}",
                },
            }
        ]
    }


def overview_page() -> dict:
    revenue = M("fact_sales", "Total Revenue")
    visuals = [
        header(
            "ov",
            "Executive Sales Overview",
            "Are we growing, where, and through which channel? Showing FY2025 (Apr-24 to Mar-25).",
        ),
        fy_slicer("ov_fy", default_fy=2025),
        card("ov_rev", 20, revenue, "Net revenue"),
        card("ov_orders", 333, M("fact_sales", "Orders"), "Orders"),
        card("ov_aov", 646, M("fact_sales", "Avg Order Value"), "Average order value"),
        card("ov_yoy", 960, M("fact_sales", "Revenue YoY %"), "Revenue YoY %"),
        visual(
            "ov_trend",
            "lineChart",
            20,
            190,
            820,
            260,
            {"Category": [C("dim_date", "year_month")], "Y": [revenue, M("fact_sales", "Revenue PY")]},
            title="Monthly net revenue vs last year",
            order_by=(C("dim_date", "year_month"), "asc"),
        ),
        visual(
            "ov_geo",
            "pivotTable",
            860,
            190,
            400,
            512,
            {
                "Rows": [C("dim_store", "country"), C("dim_store", "state"), C("dim_store", "city")],
                "Values": [revenue, M("fact_sales", "Revenue Share of Parent")],
            },
            title="Country > State > City (expand to drill down)",
        ),
        visual(
            "ov_channel",
            "donutChart",
            20,
            464,
            400,
            238,
            {"Category": [C("fact_sales", "channel")], "Y": [revenue]},
            title="Channel mix",
        ),
        visual(
            "ov_category",
            "clusteredBarChart",
            440,
            464,
            400,
            238,
            {"Category": [C("dim_product", "category")], "Y": [revenue]},
            title="Net revenue by category",
            order_by=(revenue, "desc"),
        ),
    ]
    return section("overview", "Executive Sales Overview", visuals)


def churn_page() -> dict:
    scored = M("customer_scores", "Customers Scored")
    visuals = [
        header(
            "ch",
            "Customer Churn",
            "Who is about to stop buying, and how much revenue is at risk? (snapshot 30-Jun-2025)",
        ),
        card("ch_scored", 20, scored, "Active customers scored"),
        card("ch_high", 333, M("customer_scores", "High Risk %"), "High churn risk"),
        card("ch_rev", 646, M("customer_scores", "Revenue at Risk"), "Revenue at risk (12-month spend)"),
        card("ch_obs", 960, M("customer_scores", "Observed Churn %"), "Observed churn, Jul-Dec 2025"),
        visual(
            "ch_risk",
            "clusteredColumnChart",
            20,
            190,
            400,
            250,
            {"Category": [C("customer_scores", "churn_risk")], "Y": [scored]},
            title="Customers by predicted risk band",
        ),
        visual(
            "ch_segment",
            "clusteredBarChart",
            440,
            190,
            400,
            250,
            {
                "Category": [C("customer_scores", "segment")],
                "Y": [M("customer_scores", "Observed Churn %")],
            },
            title="Observed churn by RFM segment",
            order_by=(M("customer_scores", "Observed Churn %"), "desc"),
        ),
        visual(
            "ch_top",
            "tableEx",
            860,
            190,
            400,
            512,
            {
                "Values": [
                    C("customer_scores", "customer_id"),
                    C("customer_scores", "segment"),
                    C("customer_scores", "churn_probability"),
                    C("customer_scores", "recency_days"),
                    C("customer_scores", "monetary"),
                ]
            },
            title="Highest-risk customers (sorted by churn probability)",
            order_by=(C("customer_scores", "churn_probability"), "desc"),
        ),
        visual(
            "ch_cohort",
            "pivotTable",
            20,
            454,
            820,
            248,
            {
                "Rows": [C("cohort_retention", "cohort")],
                "Columns": [C("cohort_retention", "months_since_first")],
                "Values": [M("cohort_retention", "Retention %")],
            },
            title="Cohort retention: % of each quarter's new customers still buying N months later",
            objects=heatmap("Retention %"),
        ),
    ]
    return section("churn", "Customer Churn", visuals)


def section(name: str, display: str, visuals: list[dict]) -> dict:
    return {
        "name": name,
        "displayName": display,
        "displayOption": 1,
        "width": W,
        "height": H,
        "config": "{}",
        "filters": "[]",
        "visualContainers": visuals,
    }


def build() -> Path:
    # A custom theme is a registered resource: package type 1, item type 201 (202 is a base theme).
    resources = REPORT / "StaticResources" / "RegisteredResources"
    resources.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(THEME_SOURCE, resources / THEME)
    config = {
        "version": "5.55",
        "themeCollection": {"customTheme": {"name": THEME, "version": "5.55", "type": 1}},
        "activeSectionIndex": 0,
    }
    report = {
        "config": json.dumps(config),
        "layoutOptimization": 0,
        "resourcePackages": [
            {
                "resourcePackage": {
                    "name": "RegisteredResources",
                    "type": 1,
                    "items": [{"type": 201, "path": THEME, "name": THEME}],
                    "disabled": False,
                }
            }
        ],
        "sections": [overview_page(), churn_page()],
        "filters": "[]",
    }
    out = REPORT / "report.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    print(f"Report layout written to {build()}")
