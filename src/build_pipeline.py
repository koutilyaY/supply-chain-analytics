"""SQL-based ETL pipeline.

Emulates a production analytics pipeline using SQLite as the warehouse:

    1. EXTRACT  - read the five raw source extracts from data/raw/
    2. LOAD     - bulk-load them into typed staging tables (sql/01_schema.sql)
    3. TRANSFORM- build the star-schema mart (sql/02_transform.sql)
    4. KPI VIEWS- create pre-aggregated KPI views (sql/03_kpis.sql)
    5. PUBLISH  - export analytics-ready tables to data/processed/

Run:  python src/build_pipeline.py
"""
from __future__ import annotations

import math
import sqlite3

import pandas as pd

from config import DB_PATH, PROCESSED_DIR, RAW_DIR, SQL_DIR

# Raw file -> staging table mapping.
RAW_TO_STAGING = {
    "suppliers.csv": "stg_suppliers",
    "products.csv": "stg_products",
    "sales_transactions.csv": "stg_sales",
    "purchase_orders.csv": "stg_purchase_orders",
    "inventory_snapshots.csv": "stg_inventory_snapshots",
}

# Tables/views exported to data/processed/ for downstream Python + Power BI.
PUBLISH = [
    "dim_date", "dim_product", "dim_supplier",
    "fact_sales", "fact_purchase_orders", "fact_inventory",
    "v_sales_monthly", "v_supplier_performance", "v_lead_time_monthly",
    "v_inventory_monthly", "v_demand_variability",
]


def _run_sql_file(conn: sqlite3.Connection, name: str) -> None:
    sql = (SQL_DIR / name).read_text()
    conn.executescript(sql)
    conn.commit()
    print(f"  ran {name}")


def _load_staging(conn: sqlite3.Connection) -> None:
    for fname, table in RAW_TO_STAGING.items():
        df = pd.read_csv(RAW_DIR / fname)
        # Normalize boolean promo flag to 0/1 for SQLite.
        if "is_promo" in df.columns:
            df["is_promo"] = df["is_promo"].astype(int)
        df.to_sql(table, conn, if_exists="append", index=False)
        print(f"  loaded {table:<26} {len(df):>8,} rows")


def main() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    print(f"Building warehouse at {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    # SQLite lacks sqrt() unless built with math functions; register it so the
    # demand-variability view works portably across Python builds.
    conn.create_function("sqrt", 1, lambda x: math.sqrt(x) if x and x > 0 else 0.0)

    print("\n[1/4] Staging DDL")
    _run_sql_file(conn, "01_schema.sql")

    print("\n[2/4] Loading raw extracts")
    _load_staging(conn)

    print("\n[3/4] Transform -> star schema")
    _run_sql_file(conn, "02_transform.sql")

    print("\n[4/4] KPI views")
    _run_sql_file(conn, "03_kpis.sql")

    print("\nPublishing analytics-ready datasets to data/processed/")
    for tbl in PUBLISH:
        df = pd.read_sql(f"SELECT * FROM {tbl}", conn)
        df.to_csv(PROCESSED_DIR / f"{tbl}.csv", index=False)
        print(f"  {tbl:<26} {len(df):>8,} rows")

    conn.close()
    print("\nPipeline complete.")


if __name__ == "__main__":
    main()
