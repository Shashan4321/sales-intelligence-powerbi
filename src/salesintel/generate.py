"""Generate a raw, denormalised order-lines extract (like a POS / e-commerce export).

Customer behaviour is simulated so that customer analytics is meaningful:
each customer has a latent purchase rate and a latent "lifetime". After the
lifetime ends the customer stops buying (churns). Discount-heavy, single-channel
and low-frequency customers churn sooner. The analysis notebook-free scripts then
try to *recover* this behaviour from the data, exactly as they would on real data.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SEED = 2024
START, END = pd.Timestamp("2023-01-01"), pd.Timestamp("2025-12-31")

GEO = {  # country -> state -> cities
    "India": {
        "Haryana": ["Gurugram", "Faridabad"],
        "Delhi": ["New Delhi"],
        "Karnataka": ["Bengaluru", "Mysuru"],
        "Maharashtra": ["Mumbai", "Pune"],
        "Telangana": ["Hyderabad"],
        "Tamil Nadu": ["Chennai"],
        "West Bengal": ["Kolkata"],
        "Uttar Pradesh": ["Noida", "Lucknow"],
    },
    "United Arab Emirates": {"Dubai": ["Dubai"], "Abu Dhabi": ["Abu Dhabi"]},
    "Singapore": {"Singapore": ["Singapore"]},
}
CATALOG = {
    "Electronics": {"Mobiles": (8000, 60000), "Laptops": (35000, 120000), "Audio": (800, 15000)},
    "Home & Kitchen": {"Cookware": (500, 6000), "Appliances": (2500, 40000), "Decor": (300, 5000)},
    "Fashion": {"Men": (400, 5000), "Women": (400, 6000), "Footwear": (700, 8000)},
    "Grocery": {"Staples": (50, 1200), "Beverages": (40, 800), "Snacks": (20, 500)},
    "Sports": {"Fitness": (500, 20000), "Outdoor": (800, 15000)},
}
BRANDS = ["Aurora", "Nimbus", "Vertex", "Kestrel", "Lotus", "Zenith", "Orbit", "Saffron"]


def _stores(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for country, states in GEO.items():
        for state, cities in states.items():
            for city in cities:
                for n in range(1, int(rng.integers(1, 4)) + 1):
                    rows.append(
                        {
                            "store_name": f"{city} Store {n:02d}",
                            "city": city,
                            "state": state,
                            "country": country,
                        }
                    )
    return pd.DataFrame(rows)


def _products(rng: np.random.Generator) -> pd.DataFrame:
    rows, i = [], 1
    for cat, subs in CATALOG.items():
        for sub, (lo, hi) in subs.items():
            for _ in range(10):
                price = round(float(rng.uniform(lo, hi)), -1)
                rows.append(
                    {
                        "sku": f"SKU-{i:05d}",
                        "product_name": f"{rng.choice(BRANDS)} {sub} {i:03d}",
                        "category": cat,
                        "subcategory": sub,
                        "brand": str(rng.choice(BRANDS)),
                        "list_price": price,
                        "unit_cost": round(price * float(rng.uniform(0.55, 0.8)), 2),
                    }
                )
                i += 1
    return pd.DataFrame(rows)


def generate(n_customers: int = 5000) -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    stores, products = _stores(rng), _products(rng)
    span_days = (END - START).days

    segment = rng.choice(["Consumer", "Corporate", "Small Business"], n_customers, p=[0.7, 0.18, 0.12])
    deal_seeker = rng.random(n_customers) < 0.3  # buys mostly on discount
    rate = rng.gamma(2.0, 1 / 60, n_customers)  # orders per day (~1 per month)
    rate *= np.where(segment == "Corporate", 1.6, 1.0)
    signup = START + pd.to_timedelta(rng.integers(0, span_days - 60, n_customers), unit="D")
    # lifetime in days: deal seekers and low-rate customers churn sooner
    mean_life = 500 * np.where(deal_seeker, 0.45, 1.0) * np.clip(rate * 45, 0.4, 2.5)
    lifetime = rng.exponential(mean_life)
    home_store = rng.integers(0, len(stores), n_customers)
    online_pref = rng.random(n_customers)

    prod = list(products.itertuples(index=False))
    stor = list(stores.itertuples(index=False))
    lines = []
    order_no = 0
    for c in range(n_customers):
        start = signup[c]
        stop = min(END, start + pd.Timedelta(days=float(lifetime[c])))
        days = (stop - start).days
        if days <= 0:
            days = 1
        k = max(1, rng.poisson(rate[c] * days))
        offsets = np.sort(rng.integers(0, days, k))
        for off in offsets:
            order_no += 1
            d = start + pd.Timedelta(days=int(off))
            # festive-season boost is modelled as extra items, not extra orders
            n_items = int(rng.integers(1, 4)) + int(d.month in (10, 11))
            chan = "Online" if rng.random() < online_pref[c] else "Store"
            store = stor[home_store[c]]
            for _ in range(n_items):
                p = prod[int(rng.integers(0, len(prod)))]
                disc = (
                    float(rng.choice([0.1, 0.15, 0.2, 0.25]))
                    if deal_seeker[c]
                    else float(rng.choice([0, 0, 0, 0.05, 0.1]))
                )
                lines.append(
                    (
                        f"SO-{order_no:07d}",
                        d.date(),
                        f"C{c + 1:06d}",
                        segment[c],
                        signup[c].date(),
                        store.store_name,
                        store.city,
                        store.state,
                        store.country,
                        chan,
                        p.sku,
                        p.product_name,
                        p.category,
                        p.subcategory,
                        p.brand,
                        int(rng.integers(1, 4)),
                        p.list_price,
                        disc,
                        p.unit_cost,
                        bool(rng.random() < 0.02),
                    )
                )
    cols = [
        "order_id",
        "order_date",
        "customer_id",
        "segment",
        "signup_date",
        "store_name",
        "city",
        "state",
        "country",
        "channel",
        "sku",
        "product_name",
        "category",
        "subcategory",
        "brand",
        "quantity",
        "unit_price",
        "discount_pct",
        "unit_cost",
        "is_returned",
    ]
    return pd.DataFrame(lines, columns=cols)


def write(path: str | Path = "data/raw/order_lines.csv") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    generate().to_csv(path, index=False)
    return path


if __name__ == "__main__":
    print(f"raw extract -> {write()}")
