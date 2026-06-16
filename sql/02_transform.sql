-- ============================================================================
-- 02_transform.sql  |  Analytics-ready (mart) layer
-- ----------------------------------------------------------------------------
-- Joins/cleans the staging tables into conformed dimensions and fact tables
-- that the KPI layer, forecasting models and Power BI exports consume.
-- Built as a star schema:  dim_date, dim_product, dim_supplier
--                          fact_sales, fact_purchase_orders, fact_inventory
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Dimension: Date  (one row per calendar day seen in sales)
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS dim_date;
CREATE TABLE dim_date AS
WITH d AS (
    SELECT DISTINCT date(order_date) AS date_key FROM stg_sales
)
SELECT
    date_key,
    CAST(strftime('%Y', date_key) AS INTEGER)            AS year,
    CAST(strftime('%m', date_key) AS INTEGER)            AS month,
    CAST(strftime('%d', date_key) AS INTEGER)            AS day,
    CAST(strftime('%W', date_key) AS INTEGER)            AS week_of_year,
    CAST(strftime('%w', date_key) AS INTEGER)            AS day_of_week,   -- 0=Sun
    strftime('%Y-%m', date_key)                          AS year_month,
    CASE WHEN CAST(strftime('%w', date_key) AS INTEGER) IN (0, 6)
         THEN 1 ELSE 0 END                               AS is_weekend,
    CASE
        WHEN CAST(strftime('%m', date_key) AS INTEGER) IN (12, 1, 2)  THEN 'Winter'
        WHEN CAST(strftime('%m', date_key) AS INTEGER) IN (3, 4, 5)   THEN 'Spring'
        WHEN CAST(strftime('%m', date_key) AS INTEGER) IN (6, 7, 8)   THEN 'Summer'
        ELSE 'Fall'
    END                                                  AS season
FROM d;

-- ---------------------------------------------------------------------------
-- Dimension: Product  (master + supplier roll-up)
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS dim_product;
CREATE TABLE dim_product AS
SELECT
    p.product_id,
    p.product_name,
    p.category,
    p.subcategory,
    p.supplier_id,
    s.supplier_name,
    s.region            AS supplier_region,
    p.unit_cost,
    p.unit_price,
    ROUND(p.unit_price - p.unit_cost, 2)                          AS unit_margin,
    ROUND((p.unit_price - p.unit_cost) / p.unit_price, 4)         AS margin_pct
FROM stg_products p
LEFT JOIN stg_suppliers s ON s.supplier_id = p.supplier_id;

-- ---------------------------------------------------------------------------
-- Dimension: Supplier
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS dim_supplier;
CREATE TABLE dim_supplier AS
SELECT
    supplier_id,
    supplier_name,
    region,
    promised_lead_time_days,
    reliability_score
FROM stg_suppliers;

-- ---------------------------------------------------------------------------
-- Fact: Sales  (line-level, enriched with cost so margin is queryable)
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS fact_sales;
CREATE TABLE fact_sales AS
SELECT
    s.transaction_id,
    date(s.order_date)                       AS date_key,
    s.product_id,
    p.category,
    p.supplier_id,
    s.store_id,
    s.channel,
    s.quantity,
    s.unit_price,
    s.revenue,
    ROUND(s.quantity * p.unit_cost, 2)       AS cogs,
    ROUND(s.revenue - s.quantity * p.unit_cost, 2) AS gross_margin,
    s.is_promo
FROM stg_sales s
LEFT JOIN dim_product p ON p.product_id = s.product_id;

CREATE INDEX IF NOT EXISTS ix_fact_sales_pd   ON fact_sales(product_id, date_key);
CREATE INDEX IF NOT EXISTS ix_fact_sales_date ON fact_sales(date_key);

-- ---------------------------------------------------------------------------
-- Fact: Purchase Orders  (lead-time variance + fill computed inline)
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS fact_purchase_orders;
CREATE TABLE fact_purchase_orders AS
SELECT
    po.po_id,
    po.product_id,
    po.supplier_id,
    date(po.order_date)                       AS order_date,
    date(po.promised_date)                    AS promised_date,
    date(po.received_date)                    AS received_date,
    po.qty_ordered,
    po.qty_received,
    po.promised_lead_time_days,
    po.actual_lead_time_days,
    (po.actual_lead_time_days - po.promised_lead_time_days) AS lead_time_variance_days,
    CASE WHEN julianday(po.received_date) <= julianday(po.promised_date)
         THEN 1 ELSE 0 END                    AS on_time_flag,
    ROUND(CAST(po.qty_received AS REAL) / NULLIF(po.qty_ordered, 0), 4) AS fill_ratio
FROM stg_purchase_orders po;

-- ---------------------------------------------------------------------------
-- Fact: Inventory  (weekly snapshot, joined to cost for $ valuation)
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS fact_inventory;
CREATE TABLE fact_inventory AS
SELECT
    date(i.snapshot_date)                     AS snapshot_date,
    i.product_id,
    p.category,
    i.on_hand_units,
    i.weekly_demand_units,
    i.is_stockout,
    ROUND(i.on_hand_units * p.unit_cost, 2)   AS inventory_value
FROM stg_inventory_snapshots i
LEFT JOIN dim_product p ON p.product_id = i.product_id;

CREATE INDEX IF NOT EXISTS ix_fact_inv_pd ON fact_inventory(product_id, snapshot_date);
