"""Inventory optimization analysis.

Three analyses a planning team uses to free up working capital:

  1. ABC classification - rank SKUs by annual revenue contribution
     (A = top ~80% of revenue, B = next ~15%, C = bottom ~5%).
  2. Slow-moving inventory - SKUs whose on-hand stock vastly outpaces recent
     demand (high days-of-supply or no recent sales); their value is capital
     sitting idle on the shelf.
  3. Carrying-cost reduction - quantify the holding cost tied up in excess
     stock above a target days-of-supply, and the annual saving from
     right-sizing it.

Outputs:
    data/processed/inventory_abc.csv
    data/processed/slow_moving_inventory.csv
    reports/inventory_optimization_summary.csv

Run:  python src/inventory_analysis.py
"""
from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd

from config import (ANNUAL_HOLDING_COST_RATE, DB_PATH, PROCESSED_DIR,
                    REPORTS_DIR, SLOW_MOVING_DAYS, money)

# A SKU is "slow-moving" if it would take longer than this to sell its current
# stock at its recent sales velocity (or has had no sales in SLOW_MOVING_DAYS).
SLOW_MOVING_DOS = 180          # days of supply
# Excess capital = inventory held above this target days-of-supply cap.
# 75 days (~2.5 months of cover) is a realistic right-sizing target that also
# trims oversized safety stock on otherwise-healthy SKUs.
TARGET_DOS_CAP = 75


def load() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    conn = sqlite3.connect(DB_PATH)
    prod = pd.read_sql("SELECT * FROM dim_product", conn)
    sales = pd.read_sql(
        "SELECT product_id, date_key, quantity, revenue, cogs FROM fact_sales",
        conn, parse_dates=["date_key"])
    inv = pd.read_sql(
        "SELECT snapshot_date, product_id, on_hand_units FROM fact_inventory",
        conn, parse_dates=["snapshot_date"])
    conn.close()
    return prod, sales, inv


def analyze() -> dict:
    prod, sales, inv = load()
    max_date = sales["date_key"].max()
    last_365 = max_date - pd.Timedelta(days=365)
    last_window = max_date - pd.Timedelta(days=SLOW_MOVING_DAYS)

    # --- Per-SKU demand metrics ----------------------------------------
    annual = (sales[sales["date_key"] > last_365]
              .groupby("product_id")
              .agg(annual_units=("quantity", "sum"),
                   annual_revenue=("revenue", "sum"),
                   annual_cogs=("cogs", "sum")))
    recent = (sales[sales["date_key"] > last_window]
              .groupby("product_id")["quantity"].sum()
              .rename("recent_units"))

    # Current on-hand = latest snapshot per SKU.
    latest = inv.sort_values("snapshot_date").groupby("product_id").tail(1)
    onhand = latest.set_index("product_id")["on_hand_units"].rename("on_hand_units")

    df = (prod.set_index("product_id")
              .join(annual).join(recent).join(onhand)
              .reset_index())
    for c in ["annual_units", "annual_revenue", "annual_cogs",
              "recent_units", "on_hand_units"]:
        df[c] = df[c].fillna(0)

    df["inventory_value"] = (df["on_hand_units"] * df["unit_cost"]).round(2)
    df["avg_daily_demand"] = df["annual_units"] / 365.0
    # Days of supply from current stock at the trailing annual velocity.
    df["days_of_supply"] = np.where(
        df["avg_daily_demand"] > 0,
        df["on_hand_units"] / df["avg_daily_demand"],
        np.inf)

    # --- ABC classification (by annual revenue) ------------------------
    df = df.sort_values("annual_revenue", ascending=False).reset_index(drop=True)
    total_rev = df["annual_revenue"].sum()
    df["cum_revenue_pct"] = df["annual_revenue"].cumsum() / total_rev * 100
    df["abc_class"] = np.where(df["cum_revenue_pct"] <= 80, "A",
                       np.where(df["cum_revenue_pct"] <= 95, "B", "C"))

    # --- Slow-moving flag ----------------------------------------------
    df["is_slow_moving"] = (
        (df["recent_units"] == 0) | (df["days_of_supply"] > SLOW_MOVING_DOS)
    ).astype(int)

    # --- Excess capital above target DOS -------------------------------
    target_units = (df["avg_daily_demand"] * TARGET_DOS_CAP)
    df["excess_units"] = np.where(
        df["avg_daily_demand"] > 0,
        np.clip(df["on_hand_units"] - target_units, 0, None),
        df["on_hand_units"])          # no demand at all => all of it is excess
    df["excess_value"] = (df["excess_units"] * df["unit_cost"]).round(2)

    # --- Headline figures ----------------------------------------------
    total_inv_value = df["inventory_value"].sum()
    slow = df[df["is_slow_moving"] == 1]
    slow_value = slow["inventory_value"].sum()
    excess_value = df["excess_value"].sum()

    baseline_carrying = total_inv_value * ANNUAL_HOLDING_COST_RATE
    saving = excess_value * ANNUAL_HOLDING_COST_RATE
    reduction_pct = saving / baseline_carrying * 100 if baseline_carrying else 0

    # --- Persist --------------------------------------------------------
    abc_cols = ["product_id", "product_name", "category", "abc_class",
                "annual_units", "annual_revenue", "on_hand_units",
                "inventory_value", "days_of_supply", "cum_revenue_pct"]
    df[abc_cols].to_csv(PROCESSED_DIR / "inventory_abc.csv", index=False)

    slow_out = slow[["product_id", "product_name", "category", "abc_class",
                     "on_hand_units", "recent_units", "days_of_supply",
                     "inventory_value", "excess_value"]].copy()
    slow_out = slow_out.sort_values("inventory_value", ascending=False)
    slow_out.to_csv(PROCESSED_DIR / "slow_moving_inventory.csv", index=False)

    abc_summary = (df.groupby("abc_class")
                     .agg(skus=("product_id", "count"),
                          revenue=("annual_revenue", "sum"),
                          inventory_value=("inventory_value", "sum"))
                     .reset_index())
    abc_summary["revenue_pct"] = (abc_summary["revenue"] / total_rev * 100).round(1)

    summary = pd.DataFrame([
        ["Total SKUs", len(df)],
        ["Total inventory value", round(total_inv_value, 2)],
        ["Baseline annual carrying cost (25%)", round(baseline_carrying, 2)],
        ["Slow-moving SKUs", len(slow)],
        ["Slow-moving inventory value", round(slow_value, 2)],
        ["Excess inventory value (above %dd DOS)" % TARGET_DOS_CAP, round(excess_value, 2)],
        ["Annual carrying-cost saving", round(saving, 2)],
        ["Carrying-cost reduction %", round(reduction_pct, 1)],
    ], columns=["metric", "value"])
    summary.to_csv(REPORTS_DIR / "inventory_optimization_summary.csv", index=False)

    # --- Console report -------------------------------------------------
    print("\n" + "=" * 60)
    print("INVENTORY OPTIMIZATION ANALYSIS")
    print("=" * 60)
    print("ABC classification (by annual revenue):")
    for r in abc_summary.itertuples(index=False):
        print(f"  Class {r.abc_class}: {r.skus:>3} SKUs | "
              f"{r.revenue_pct:>5.1f}% of revenue | "
              f"inv {money(r.inventory_value)}")
    print("-" * 60)
    print(f"Total inventory value         : {money(total_inv_value)}")
    print(f"Slow-moving SKUs              : {len(slow)} "
          f"({len(slow)/len(df)*100:.1f}% of catalog)")
    print(f"Slow-moving inventory value   : {money(slow_value)}")
    print(f"Excess inventory (>{TARGET_DOS_CAP}d DOS) : {money(excess_value)}")
    print(f"Baseline annual carrying cost : {money(baseline_carrying)}")
    print(f"==> Right-sizing excess stock saves {money(saving)}/yr "
          f"({reduction_pct:.1f}% of carrying cost).")
    print("=" * 60)

    return {
        "total_inventory_value": round(total_inv_value, 2),
        "slow_moving_value": round(slow_value, 2),
        "slow_moving_skus": int(len(slow)),
        "excess_value": round(excess_value, 2),
        "carrying_saving": round(saving, 2),
        "carrying_reduction_pct": round(reduction_pct, 1),
    }


if __name__ == "__main__":
    analyze()
