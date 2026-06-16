"""Export a clean star schema for Power BI.

Writes a self-contained set of CSVs to ``data/powerbi/`` that load straight
into Power BI Desktop as a star schema:

    Dimensions : dim_date, dim_product, dim_supplier
    Facts      : fact_sales_daily, fact_inventory, fact_purchase_orders,
                 fact_forecast
    Helper     : kpi_executive_summary

fact_sales is published at a date x product x channel daily grain (aggregating
any same-day line items) so the Power BI model keeps every analytic dimension
while presenting a clean, conformed fact table.

Run:  python src/export_powerbi.py
"""
from __future__ import annotations

import sqlite3

import pandas as pd

from config import DB_PATH, POWERBI_DIR, PROCESSED_DIR


def main() -> None:
    conn = sqlite3.connect(DB_PATH)

    # --- Dimensions -----------------------------------------------------
    for dim in ["dim_date", "dim_product", "dim_supplier"]:
        pd.read_sql(f"SELECT * FROM {dim}", conn).to_csv(
            POWERBI_DIR / f"{dim}.csv", index=False)

    # --- Fact: sales at date x product x channel daily grain ------------
    sales_daily = pd.read_sql("""
        SELECT date_key, product_id, category, channel,
               SUM(quantity)     AS units,
               ROUND(SUM(revenue), 2)      AS revenue,
               ROUND(SUM(cogs), 2)         AS cogs,
               ROUND(SUM(gross_margin), 2) AS gross_margin,
               COUNT(*)          AS line_items
        FROM fact_sales
        GROUP BY date_key, product_id, category, channel
    """, conn)
    sales_daily.to_csv(POWERBI_DIR / "fact_sales_daily.csv", index=False)

    # --- Fact: inventory & purchase orders ------------------------------
    pd.read_sql("SELECT * FROM fact_inventory", conn).to_csv(
        POWERBI_DIR / "fact_inventory.csv", index=False)
    pd.read_sql("SELECT * FROM fact_purchase_orders", conn).to_csv(
        POWERBI_DIR / "fact_purchase_orders.csv", index=False)

    conn.close()

    # --- Fact: forecast vs actual, rolled up to month x category --------
    fva = pd.read_csv(PROCESSED_DIR / "forecast_vs_actual.csv",
                      parse_dates=["week"])
    fva["year_month"] = fva["week"].dt.to_period("M").astype(str)
    fc_monthly = (fva.groupby(["year_month", "category"])
                     .agg(actual=("actual", "sum"),
                          ml_forecast=("ml_forecast", "sum"),
                          baseline_forecast=("baseline_forecast", "sum"))
                     .reset_index())
    fc_monthly["abs_error"] = (fc_monthly["actual"] - fc_monthly["ml_forecast"]).abs()
    fc_monthly["forecast_accuracy_pct"] = (
        100 - fc_monthly["abs_error"] / fc_monthly["actual"] * 100).round(2)
    fc_monthly = fc_monthly.round(1)
    fc_monthly.to_csv(POWERBI_DIR / "fact_forecast.csv", index=False)

    # --- KPI summary (for card visuals) ---------------------------------
    pd.read_csv(PROCESSED_DIR / "kpi_executive_summary.csv").to_csv(
        POWERBI_DIR / "kpi_executive_summary.csv", index=False)

    # --- Report ---------------------------------------------------------
    print("Power BI star schema written to data/powerbi/:")
    for f in sorted(POWERBI_DIR.glob("*.csv")):
        n = sum(1 for _ in open(f)) - 1
        print(f"  {f.name:<32} {n:>8,} rows")


if __name__ == "__main__":
    main()
