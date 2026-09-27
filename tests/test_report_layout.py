"""The generated report must only reference tables, columns and measures that exist in the model."""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "powerbi"))

import build_report  # noqa: E402

TABLES = ROOT / "powerbi" / "SalesIntelligence.SemanticModel" / "definition" / "tables"


def model_fields() -> dict[str, set[str]]:
    fields: dict[str, set[str]] = {}
    for tmdl in TABLES.glob("*.tmdl"):
        text = tmdl.read_text(encoding="utf-8")
        table = re.search(r"^table (.+)$", text, re.M).group(1).strip("'")
        names = re.findall(r"^\t(?:column|measure) ('[^']+'|\S+)", text, re.M)
        fields[table] = {n.strip("'") for n in names}
    return fields


def referenced(report: dict) -> list[tuple[str, str, str]]:
    refs = []
    for section in report["sections"]:
        for vc in section["visualContainers"]:
            query = json.loads(vc["config"])["singleVisual"].get("prototypeQuery")
            if not query:
                continue
            alias = {f["Name"]: f["Entity"] for f in query["From"]}
            for sel in query["Select"]:
                ((kind, body),) = ((k, v) for k, v in sel.items() if k != "Name")
                refs.append((alias[body["Expression"]["SourceRef"]["Source"]], body["Property"], kind))
    return refs


def test_every_field_exists_in_the_model():
    report = json.loads(build_report.build().read_text(encoding="utf-8"))
    fields = model_fields()
    missing = [(t, p) for t, p, _ in referenced(report) if p not in fields.get(t, set())]
    assert not missing, f"Report references fields not in the model: {missing}"


def test_two_pages_and_theme_registered():
    report = json.loads(build_report.build().read_text(encoding="utf-8"))
    assert [s["displayName"] for s in report["sections"]] == ["Executive Sales Overview", "Customer Churn"]
    theme = build_report.REPORT / "StaticResources" / "RegisteredResources" / build_report.THEME
    assert theme.exists()
    assert json.loads(report["config"])["themeCollection"]["customTheme"]["name"] == build_report.THEME


def test_visuals_fit_on_the_page():
    report = json.loads(build_report.build().read_text(encoding="utf-8"))
    for section in report["sections"]:
        for vc in section["visualContainers"]:
            assert vc["x"] + vc["width"] <= build_report.W
            assert vc["y"] + vc["height"] <= build_report.H
