-- ============================================================================
-- 01_schema.sql  |  Staging (raw) layer DDL
-- ----------------------------------------------------------------------------
-- Defines the landing tables that mirror the five source-system extracts.
-- The Python loader (src/build_pipeline.py) bulk-loads the raw CSVs into
-- these tables; downstream transforms read exclusively from here.
-- ============================================================================

DROP TABLE IF EXISTS stg_suppliers;
CREATE TABLE stg_suppliers (
    supplier_id              TEXT PRIMARY KEY,
    supplier_name            TEXT,
    region                   TEXT,
    promised_lead_time_days  INTEGER,
    reliability_score        REAL
);

DROP TABLE IF EXISTS stg_products;
CREATE TABLE stg_products (
    product_id    TEXT PRIMARY KEY,
    product_name  TEXT,
    category      TEXT,
    subcategory   TEXT,
    supplier_id   TEXT,
    unit_cost     REAL,
    unit_price    REAL
);

DROP TABLE IF EXISTS stg_sales;
CREATE TABLE stg_sales (
    transaction_id  INTEGER PRIMARY KEY,
    order_date      TEXT,
    product_id      TEXT,
    category        TEXT,
    store_id        TEXT,
    channel         TEXT,
    quantity        INTEGER,
    unit_price      REAL,
    is_promo        INTEGER,
    revenue         REAL
);

DROP TABLE IF EXISTS stg_purchase_orders;
CREATE TABLE stg_purchase_orders (
    po_id                    TEXT PRIMARY KEY,
    product_id               TEXT,
    supplier_id              TEXT,
    order_date               TEXT,
    promised_date            TEXT,
    received_date            TEXT,
    qty_ordered              INTEGER,
    qty_received             INTEGER,
    promised_lead_time_days  INTEGER,
    actual_lead_time_days    INTEGER
);

DROP TABLE IF EXISTS stg_inventory_snapshots;
CREATE TABLE stg_inventory_snapshots (
    snapshot_date        TEXT,
    product_id           TEXT,
    on_hand_units        INTEGER,
    weekly_demand_units  INTEGER,
    is_stockout          INTEGER
);

-- Helpful indexes for the transform joins / group-bys.
CREATE INDEX IF NOT EXISTS ix_sales_product ON stg_sales(product_id);
CREATE INDEX IF NOT EXISTS ix_sales_date    ON stg_sales(order_date);
CREATE INDEX IF NOT EXISTS ix_po_supplier   ON stg_purchase_orders(supplier_id);
CREATE INDEX IF NOT EXISTS ix_inv_product   ON stg_inventory_snapshots(product_id);
