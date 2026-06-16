"""Generate a realistic synthetic supply-chain dataset.

Produces five raw "source system" extracts in ``data/raw/`` that emulate the
kind of operational data a planning team works with:

    products.csv            - product master (category, supplier, cost, price)
    suppliers.csv           - supplier master (region, promised lead time)
    sales_transactions.csv  - ~500K+ line-level sales (the analytic backbone)
    purchase_orders.csv     - replenishment POs with promised vs actual receipt
    inventory_snapshots.csv - weekly on-hand position per product

Demand is built from a base rate per product modulated by:
  * long-run growth trend
  * annual seasonality (category-specific peak months)
  * day-of-week effects (weekend lift for consumer goods)
  * random promotional spikes
  * Poisson noise

The whole thing is vectorized with NumPy/Pandas so 500K+ rows generate in
seconds; Faker is used only for the small master tables.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from faker import Faker

from config import (
    CATEGORIES, END_DATE, N_PRODUCTS, N_STORES, N_SUPPLIERS, RANDOM_SEED,
    RAW_DIR, SERVICE_LEVEL_Z, START_DATE, TARGET_TRANSACTIONS, money,
)

rng = np.random.default_rng(RANDOM_SEED)
fake = Faker()
Faker.seed(RANDOM_SEED)

REGIONS = ["North America", "Europe", "Asia-Pacific", "Latin America"]
CHANNELS = ["Retail Store", "E-Commerce", "Wholesale"]


# --------------------------------------------------------------------------
# Master data
# --------------------------------------------------------------------------
def build_suppliers() -> pd.DataFrame:
    rows = []
    for i in range(1, N_SUPPLIERS + 1):
        # Each supplier has a promised lead time and an intrinsic reliability
        # that later drives how much actuals deviate from promises.
        promised = int(rng.integers(5, 45))
        reliability = float(np.clip(rng.normal(0.85, 0.12), 0.45, 0.99))
        rows.append({
            "supplier_id": f"SUP{i:03d}",
            "supplier_name": fake.company(),
            "region": rng.choice(REGIONS),
            "promised_lead_time_days": promised,
            "reliability_score": round(reliability, 3),
        })
    return pd.DataFrame(rows)


def build_products(suppliers: pd.DataFrame) -> pd.DataFrame:
    cat_names = list(CATEGORIES.keys())
    cat_weights = np.array([CATEGORIES[c]["weight"] for c in cat_names])
    cat_weights = cat_weights / cat_weights.sum()

    rows = []
    for i in range(1, N_PRODUCTS + 1):
        cat = rng.choice(cat_names, p=cat_weights)
        meta = CATEGORIES[cat]
        # Unit price varies around the category base price (log-normal spread).
        price = float(meta["base_price"] * np.clip(rng.lognormal(0, 0.35), 0.4, 3.0))
        cost = price * (1 - meta["margin"]) * float(np.clip(rng.normal(1.0, 0.05), 0.8, 1.2))
        # Popularity sets the product's base daily demand rate.
        popularity = float(np.clip(rng.lognormal(0, 0.9), 0.05, 8.0))
        rows.append({
            "product_id": f"SKU{i:04d}",
            "product_name": f"{cat.split(' ')[0]} {fake.word().capitalize()} {rng.integers(100, 999)}",
            "category": cat,
            "subcategory": fake.word().capitalize(),
            "supplier_id": rng.choice(suppliers["supplier_id"].values),
            "unit_cost": round(cost, 2),
            "unit_price": round(price, 2),
            "popularity": popularity,          # internal, dropped before save
            "peak_months": meta["peak_months"],
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Demand / sales
# --------------------------------------------------------------------------
def _seasonal_multiplier(months: np.ndarray, peak_months: list[int]) -> np.ndarray:
    """Sinusoid peaking at the product's peak months (~1.6x) with ~0.6x trough."""
    peak = float(np.mean(peak_months))
    # phase so cos == 1 at the peak month
    angle = 2 * np.pi * (months - peak) / 12.0
    return 1.0 + 0.45 * np.cos(angle)


def build_sales(products: pd.DataFrame) -> pd.DataFrame:
    dates = pd.date_range(START_DATE, END_DATE, freq="D")
    n_days = len(dates)
    day_idx = np.arange(n_days)
    months = dates.month.to_numpy()
    dow = dates.dayofweek.to_numpy()           # 0 = Mon
    weekend_lift = np.where(dow >= 5, 1.35, 1.0)

    # Scale base demand so the total row count lands near the target.
    # Many low-lambda product-days yield zero rows, so the naive rows-per-unit
    # estimate overshoots demand. The empirical calibration factor (~3.2)
    # corrects for that so the row count lands above the 500K headline target.
    pop = products["popularity"].to_numpy()
    rough_rows_per_unit = pop.sum() * n_days * 1.0
    demand_scale = TARGET_TRANSACTIONS / rough_rows_per_unit * 3.2

    frames = []
    store_ids = [f"ST{j:02d}" for j in range(1, N_STORES + 1)]

    for prod in products.itertuples(index=False):
        peak_months = prod.peak_months
        seasonal = _seasonal_multiplier(months, peak_months)
        trend = 1.0 + 0.20 * (day_idx / n_days)          # +20% growth over horizon
        base = prod.popularity * demand_scale
        lam = base * seasonal * trend * weekend_lift

        # Promotional spikes on ~1.5% of days (2x-4x demand).
        promo_days = rng.random(n_days) < 0.015
        promo_mult = np.where(promo_days, rng.uniform(2.0, 4.0, n_days), 1.0)
        lam = lam * promo_mult

        units = rng.poisson(np.clip(lam, 0, None))
        active = units > 0
        if not active.any():
            continue

        d = dates[active]
        q = units[active]
        n = q.size
        frames.append(pd.DataFrame({
            "order_date": d,
            "product_id": prod.product_id,
            "category": prod.category,
            "store_id": rng.choice(store_ids, n),
            "channel": rng.choice(CHANNELS, n, p=[0.45, 0.40, 0.15]),
            "quantity": q,
            "unit_price": prod.unit_price,
            "is_promo": promo_days[active],
        }))

    sales = pd.concat(frames, ignore_index=True)
    sales["revenue"] = (sales["quantity"] * sales["unit_price"]).round(2)
    sales = sales.sort_values("order_date").reset_index(drop=True)
    sales.insert(0, "transaction_id", np.arange(1, len(sales) + 1))
    return sales


# --------------------------------------------------------------------------
# Purchase orders (lead time, fill rate, supplier performance)
# --------------------------------------------------------------------------
def build_purchase_orders(products: pd.DataFrame, suppliers: pd.DataFrame,
                          sales: pd.DataFrame) -> pd.DataFrame:
    sup = suppliers.set_index("supplier_id")
    # Order volume per product roughly tracks annual demand.
    annual_units = (sales.groupby("product_id")["quantity"].sum() / 3.0)

    po_rows = []
    po_counter = 1
    order_dates = pd.date_range(START_DATE, END_DATE, freq="7D")  # weekly cadence

    for prod in products.itertuples(index=False):
        sid = prod.supplier_id
        promised_lt = int(sup.loc[sid, "promised_lead_time_days"])
        reliability = float(sup.loc[sid, "reliability_score"])
        ann = float(annual_units.get(prod.product_id, 0.0))
        if ann <= 0:
            continue
        # Replenish every ~4 weeks; lot size ~ a month of demand.
        lot = max(int(ann / 12.0), 5)
        for od in order_dates[::4]:
            qty_ordered = int(rng.normal(lot, lot * 0.2))
            qty_ordered = max(qty_ordered, 1)
            # Actual lead time: promised plus a reliability-driven delay.
            delay = rng.normal((1 - reliability) * promised_lt, promised_lt * 0.25)
            actual_lt = int(np.clip(promised_lt + delay, 1, promised_lt * 3))
            promised_date = od + pd.Timedelta(days=promised_lt)
            received_date = od + pd.Timedelta(days=actual_lt)
            # Occasionally receive short (drives fill rate < 100%).
            fill = float(np.clip(rng.normal(reliability, 0.08), 0.6, 1.0))
            qty_received = int(round(qty_ordered * fill))
            po_rows.append({
                "po_id": f"PO{po_counter:06d}",
                "product_id": prod.product_id,
                "supplier_id": sid,
                "order_date": od,
                "promised_date": promised_date,
                "received_date": received_date,
                "qty_ordered": qty_ordered,
                "qty_received": qty_received,
                "promised_lead_time_days": promised_lt,
                "actual_lead_time_days": actual_lt,
            })
            po_counter += 1
    return pd.DataFrame(po_rows)


# --------------------------------------------------------------------------
# Inventory snapshots (turnover, stockouts, slow-moving)
# --------------------------------------------------------------------------
def build_inventory_snapshots(products: pd.DataFrame, sales: pd.DataFrame) -> pd.DataFrame:
    """Weekly on-hand snapshot from a simulated (s, S) replenishment policy.

    For each product we bucket actual sales into weekly demand, then run a
    periodic-review reorder-point simulation: when inventory position falls to
    the reorder point we order back up to S, and stock arrives after the
    product's lead time. On-hand stock, demand and stockouts are recorded each
    week. Some SKUs are deliberately overstocked so the slow-moving-inventory
    analysis has something to find.
    """
    # Weekly demand bucketed by W-SUN period, aligned to a full week index so
    # the snapshot dates and demand columns line up exactly.
    weeks = pd.period_range(START_DATE, END_DATE, freq="W-SUN")
    s = sales.copy()
    s["week"] = s["order_date"].dt.to_period("W-SUN")
    weekly = (s.groupby(["product_id", "week"])["quantity"].sum()
                .unstack(fill_value=0)
                .reindex(columns=weeks, fill_value=0))
    snap_dates = weeks.to_timestamp(how="end").normalize()

    rows = []
    for prod in products.itertuples(index=False):
        pid = prod.product_id
        wk_demand = (weekly.loc[pid].to_numpy()
                     if pid in weekly.index else np.zeros(len(weeks)))
        avg_wk = max(wk_demand.mean(), 0.05)
        std_wk = wk_demand.std()

        lead_weeks = int(rng.integers(1, 5))               # 1-4 week lead time
        safety = SERVICE_LEVEL_Z * std_wk * np.sqrt(lead_weeks)
        reorder_point = avg_wk * lead_weeks + safety
        order_up_to = reorder_point + avg_wk * 4           # ~4 wks of cover
        # ~22% of SKUs carry chronic excess stock (overstock multiplier > 1.5).
        overstock = float(np.clip(rng.lognormal(0.05, 0.45), 0.6, 4.0))
        order_up_to *= overstock

        # ~12% of SKUs carry persistent excess / obsolete stock - a buffer of
        # dead inventory that demand never draws down (bad buys, demand decline,
        # discontinued lines). This is the slow-moving capital the optimization
        # analysis is designed to surface.
        # An *absolute* unit buffer is realistic: on a slow low-velocity SKU it
        # represents months of dead supply (flagged slow-moving) while a
        # fast-mover absorbs it within its normal turns.
        is_excess = rng.random() < 0.12
        dead_buffer = float(rng.uniform(150, 360)) if is_excess else 0.0

        on_hand = order_up_to
        pipeline: dict[int, float] = {}
        for i in range(len(weeks)):
            if i in pipeline:                              # receive arrivals
                on_hand += pipeline.pop(i)
            d = wk_demand[i]
            sold = min(on_hand, d)
            on_hand -= sold
            stockout = 1 if d > sold else 0
            inv_position = on_hand + sum(pipeline.values())
            if inv_position <= reorder_point:              # place replenishment
                qty = max(order_up_to - inv_position, 0.0)
                arr = i + lead_weeks
                pipeline[arr] = pipeline.get(arr, 0.0) + qty
            rows.append({
                "snapshot_date": snap_dates[i],
                "product_id": pid,
                "on_hand_units": int(round(on_hand + dead_buffer)),
                "weekly_demand_units": int(d),
                "is_stockout": stockout,
            })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
def main() -> None:
    print("Generating supply-chain dataset (seed=%d)..." % RANDOM_SEED)

    suppliers = build_suppliers()
    products = build_products(suppliers)
    print(f"  suppliers: {len(suppliers):>7,}")
    print(f"  products : {len(products):>7,}")

    sales = build_sales(products)
    print(f"  sales    : {len(sales):>7,} transactions"
          f"  | revenue {money(sales['revenue'].sum())}")

    pos = build_purchase_orders(products, suppliers, sales)
    print(f"  POs      : {len(pos):>7,}")

    inv = build_inventory_snapshots(products, sales)
    print(f"  inv snaps: {len(inv):>7,}")

    # Drop internal helper columns before persisting the product master.
    products_out = products.drop(columns=["popularity", "peak_months"])

    suppliers.to_csv(RAW_DIR / "suppliers.csv", index=False)
    products_out.to_csv(RAW_DIR / "products.csv", index=False)
    sales.to_csv(RAW_DIR / "sales_transactions.csv", index=False)
    pos.to_csv(RAW_DIR / "purchase_orders.csv", index=False)
    inv.to_csv(RAW_DIR / "inventory_snapshots.csv", index=False)

    print(f"\nWrote 5 files to {RAW_DIR}")


if __name__ == "__main__":
    main()
