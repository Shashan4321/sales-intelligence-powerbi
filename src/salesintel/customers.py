"""Customer analytics on the gold star schema: cohorts, RFM and a churn model.

Churn definition (documented so the business can challenge it):
    snapshot = 2025-06-30. A customer is *active* if they bought in the 365 days
    before the snapshot. An active customer *churned* if they made no purchase in
    the 183 days after it (2025-07-01..2025-12-31).

Outputs: ``docs/img/*.png`` and ``reports/customer_analytics.md``.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingClassifier  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import average_precision_score, roc_auc_score  # noqa: E402
from sklearn.model_selection import train_test_split  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = pd.Timestamp("2025-06-30")
HORIZON_END = pd.Timestamp("2025-12-31")
SEED = 42

LINES_SQL = """
SELECT c.customer_id, c.segment, d.date AS order_date, f.order_id, f.channel,
       f.net_revenue, f.discount_pct, f.is_returned, p.category
FROM fact_sales f
JOIN dim_customer c USING (customer_key)
JOIN dim_date d USING (date_key)
JOIN dim_product p USING (product_key)
"""


def load(db: Path = ROOT / "data" / "sales.duckdb") -> pd.DataFrame:
    con = duckdb.connect(str(db), read_only=True)
    df = con.execute(LINES_SQL).df()
    con.close()
    df["order_date"] = pd.to_datetime(df["order_date"])
    return df


# ---------------------------------------------------------------- cohorts
def cohort_retention(lines: pd.DataFrame, max_months: int = 12) -> pd.DataFrame:
    """% of each first-purchase quarter cohort still buying N months later."""
    orders = lines.drop_duplicates("order_id")[["customer_id", "order_date"]].copy()
    orders["month"] = orders["order_date"].dt.to_period("M")
    first = orders.groupby("customer_id")["month"].min().rename("cohort_month")
    orders = orders.join(first, on="customer_id")
    orders["cohort"] = orders["cohort_month"].dt.asfreq("Q").astype(str)
    orders["age"] = (orders["month"] - orders["cohort_month"]).apply(lambda x: x.n)
    active = orders[orders["age"] <= max_months].groupby(["cohort", "age"])["customer_id"].nunique()
    size = orders.groupby("cohort")["customer_id"].nunique()
    table = (active.unstack("age").div(size, axis=0) * 100).round(1)
    last_full = (HORIZON_END.to_period("M") - max_months).asfreq("Q")
    return table.loc[[c for c in table.index if pd.Period(c) <= last_full]]


# ---------------------------------------------------------------- features
def features(lines: pd.DataFrame, snapshot: pd.Timestamp = SNAPSHOT) -> pd.DataFrame:
    hist = lines[lines["order_date"] <= snapshot]
    g = hist.groupby("customer_id")
    orders = hist.drop_duplicates("order_id")
    og = orders.groupby("customer_id")
    f = pd.DataFrame(
        {
            "recency_days": (snapshot - g["order_date"].max()).dt.days,
            "tenure_days": (snapshot - g["order_date"].min()).dt.days,
            "frequency": og.size(),
            "monetary": g["net_revenue"].sum(),
            "avg_order_value": g["net_revenue"].sum() / og.size(),
            "avg_discount": g["discount_pct"].mean(),
            "online_share": og["channel"].apply(lambda s: (s == "Online").mean()),
            "n_categories": g["category"].nunique(),
            "return_rate": g["is_returned"].mean(),
            "orders_last_90d": orders[orders["order_date"] > snapshot - pd.Timedelta(days=90)]
            .groupby("customer_id")
            .size(),
            "is_corporate": g["segment"].first().eq("Corporate").astype(int),
        }
    ).fillna({"orders_last_90d": 0})
    f["orders_per_month"] = f["frequency"] / (f["tenure_days"] / 30).clip(lower=1)
    return f


def label(lines: pd.DataFrame, feats: pd.DataFrame) -> pd.Series:
    future = lines[(lines["order_date"] > SNAPSHOT) & (lines["order_date"] <= HORIZON_END)]
    buyers = set(future["customer_id"])
    return pd.Series([0 if c in buyers else 1 for c in feats.index], index=feats.index, name="churned")


def rfm(feats: pd.DataFrame) -> pd.DataFrame:
    s = pd.DataFrame(index=feats.index)
    s["R"] = pd.qcut(-feats["recency_days"].rank(method="first"), 4, labels=[1, 2, 3, 4]).astype(int)
    s["F"] = pd.qcut(feats["frequency"].rank(method="first"), 4, labels=[1, 2, 3, 4]).astype(int)
    s["M"] = pd.qcut(feats["monetary"].rank(method="first"), 4, labels=[1, 2, 3, 4]).astype(int)
    conds = [
        (s["R"] >= 3) & (s["F"] >= 3) & (s["M"] >= 3),
        (s["R"] >= 3) & (s["F"] <= 2),
        (s["R"] <= 2) & (s["F"] >= 3),
        (s["R"] <= 2) & (s["F"] <= 2),
    ]
    s["segment"] = np.select(
        conds, ["Champions", "Promising", "At risk", "Hibernating"], default="Needs attention"
    )
    return s


# ---------------------------------------------------------------- model
def train(feats: pd.DataFrame, y: pd.Series) -> dict:
    X_tr, X_te, y_tr, y_te = train_test_split(feats, y, test_size=0.25, stratify=y, random_state=SEED)
    base = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    gbm = GradientBoostingClassifier(
        random_state=SEED, n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8
    )
    out = {"n_customers": len(feats), "churn_rate_pct": round(100 * y.mean(), 1), "test_size": len(X_te)}
    for name, model in [("logistic_regression", base), ("gradient_boosting", gbm)]:
        model.fit(X_tr, y_tr)
        p = model.predict_proba(X_te)[:, 1]
        # lift: churn rate among the 20% highest-risk vs overall
        top = p >= np.quantile(p, 0.8)
        out[name] = {
            "roc_auc": round(roc_auc_score(y_te, p), 3),
            "pr_auc": round(average_precision_score(y_te, p), 3),
            "top20_churn_rate_pct": round(100 * y_te[top].mean(), 1),
            "top20_lift": round(y_te[top].mean() / y_te.mean(), 2),
        }
    out["_gbm"], out["_X_te"] = gbm, X_te
    return out


def shap_plot(model, X: pd.DataFrame, path: Path) -> list[tuple[str, float]]:
    import shap

    sv = shap.TreeExplainer(model).shap_values(X)
    importance = sorted(zip(X.columns, np.abs(sv).mean(0), strict=True), key=lambda t: -t[1])
    plt.figure()
    shap.summary_plot(sv, X, show=False, max_display=10, plot_size=(7, 4.5))
    plt.title("What drives churn risk (SHAP, gradient boosting)", fontsize=10, loc="left")
    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close("all")
    return [(k, round(float(v), 3)) for k, v in importance]


def cohort_plot(table: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 3.8))
    im = ax.imshow(table.values, cmap="Blues", aspect="auto", vmin=0, vmax=100)
    ax.set_xticks(range(table.shape[1]), table.columns)
    ax.set_yticks(range(table.shape[0]), table.index)
    for i in range(table.shape[0]):
        for j in range(table.shape[1]):
            v = table.values[i, j]
            if not np.isnan(v):
                ax.text(
                    j,
                    i,
                    f"{v:.0f}",
                    ha="center",
                    va="center",
                    fontsize=7,
                    color="white" if v > 60 else "#1f2937",
                )
    ax.set_xlabel("Months since first purchase")
    ax.set_title("Customer retention by first-purchase quarter (% still buying)", fontsize=10, loc="left")
    fig.colorbar(im, ax=ax, fraction=0.025)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def export_for_powerbi(
    seg: pd.DataFrame,
    feats: pd.DataFrame,
    model,
    cohorts: pd.DataFrame,
    gold: Path = ROOT / "data" / "gold",
) -> None:
    """Write customer scores and the cohort matrix for the Power BI 'Customer Churn' page.

    churn_probability is the gradient-boosting score at the 2025-06-30 snapshot; risk bands are
    High >= 0.6, Medium >= 0.3, Low otherwise. churned_h2_2025 is the observed outcome.
    """
    gold.mkdir(parents=True, exist_ok=True)
    scores = seg.rename(columns={"churned": "churned_h2_2025"}).join(
        feats[["recency_days", "frequency", "monetary"]]
    )
    scores["churn_probability"] = model.predict_proba(feats[model.feature_names_in_])[:, 1].round(4)
    scores["churn_risk"] = pd.cut(
        scores["churn_probability"],
        [0, 0.3, 0.6, 1],
        labels=["Low", "Medium", "High"],
        include_lowest=True,
    )
    scores.rename_axis("customer_id").reset_index().to_csv(gold / "customer_scores.csv", index=False)
    long = cohorts.stack().rename("retention_pct").reset_index()
    long.columns = ["cohort", "months_since_first", "retention_pct"]
    long.to_csv(gold / "cohort_retention.csv", index=False)


def run() -> dict:
    lines = load()
    img = ROOT / "docs" / "img"
    img.mkdir(parents=True, exist_ok=True)
    cohorts = cohort_retention(lines)
    cohort_plot(cohorts, img / "cohort_retention.png")

    feats = features(lines)
    feats = feats[feats["recency_days"] <= 365]  # active customers only
    y = label(lines, feats)
    seg = rfm(feats).join(y)
    seg_table = seg.groupby("segment").agg(customers=("churned", "size"), churn_rate_pct=("churned", "mean"))
    seg_table["churn_rate_pct"] = (seg_table["churn_rate_pct"] * 100).round(1)

    res = train(feats, y)
    gbm = res.pop("_gbm")
    drivers = shap_plot(gbm, res.pop("_X_te"), img / "shap_summary.png")
    export_for_powerbi(seg, feats, gbm, cohorts)
    res["top_drivers"] = drivers[:5]
    res["rfm_segments"] = seg_table.reset_index().to_dict(orient="records")
    res["month3_retention_pct"] = {k: float(v) for k, v in cohorts[3].dropna().items()}

    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    (out / "customer_analytics.json").write_text(json.dumps(res, indent=2, default=str))
    return res


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
