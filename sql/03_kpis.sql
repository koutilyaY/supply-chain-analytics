-- ============================================================================
-- 03_kpis.sql  |  KPI views over the analytics mart
-- ----------------------------------------------------------------------------
-- Pre-aggregated views that the reporting layer and Power BI can read directly.
-- These cover the demand / supply / inventory KPIs; forecast-accuracy KPIs are
-- produced by the Python model (src/forecasting.py) and merged in separately.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Monthly sales by category (demand patterns & seasonality)
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_sales_monthly;
CREATE VIEW v_sales_monthly AS
SELECT
    d.year_month,
    d.year,
    d.month,
    f.category,
    SUM(f.quantity)      AS units_sold,
    ROUND(SUM(f.revenue), 2)      AS revenue,
    ROUND(SUM(f.gross_margin), 2) AS gross_margin,
    COUNT(*)             AS transactions
FROM fact_sales f
JOIN dim_date d ON d.date_key = f.date_key
GROUP BY d.year_month, d.year, d.month, f.category;

-- ---------------------------------------------------------------------------
-- Supplier performance scorecard
--   on-time %, avg fill rate, avg lead-time variance
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_supplier_performance;
CREATE VIEW v_supplier_performance AS
SELECT
    s.supplier_id,
    s.supplier_name,
    s.region,
    s.promised_lead_time_days,
    COUNT(*)                                          AS po_count,
    ROUND(100.0 * AVG(po.on_time_flag), 1)           AS on_time_pct,
    ROUND(100.0 * AVG(po.fill_ratio), 1)             AS avg_fill_rate_pct,
    ROUND(AVG(po.actual_lead_time_days), 1)          AS avg_actual_lead_time,
    ROUND(AVG(po.lead_time_variance_days), 1)        AS avg_lead_time_variance,
    -- composite 0-100 score: 50% on-time, 30% fill, 20% lead-time adherence
    ROUND(
        50.0 * AVG(po.on_time_flag)
      + 30.0 * AVG(po.fill_ratio)
      + 20.0 * (1.0 - MIN(1.0, AVG(po.lead_time_variance_days) * 1.0
                                / NULLIF(s.promised_lead_time_days, 0)))
    , 1)                                             AS supplier_score
FROM fact_purchase_orders po
JOIN dim_supplier s ON s.supplier_id = po.supplier_id
GROUP BY s.supplier_id, s.supplier_name, s.region, s.promised_lead_time_days;

-- ---------------------------------------------------------------------------
-- Lead-time variance by month (trend of supply reliability)
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_lead_time_monthly;
CREATE VIEW v_lead_time_monthly AS
SELECT
    strftime('%Y-%m', po.received_date)              AS year_month,
    ROUND(AVG(po.actual_lead_time_days), 1)          AS avg_lead_time,
    ROUND(AVG(po.lead_time_variance_days), 1)        AS avg_variance,
    ROUND(100.0 * AVG(po.on_time_flag), 1)           AS on_time_pct
FROM fact_purchase_orders po
GROUP BY strftime('%Y-%m', po.received_date);

-- ---------------------------------------------------------------------------
-- Inventory position & stockout rate by month / category
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_inventory_monthly;
CREATE VIEW v_inventory_monthly AS
SELECT
    strftime('%Y-%m', snapshot_date)                 AS year_month,
    category,
    ROUND(AVG(on_hand_units), 1)                     AS avg_on_hand_units,
    ROUND(AVG(inventory_value), 2)                   AS avg_inventory_value,
    ROUND(100.0 * AVG(is_stockout), 2)               AS stockout_pct,
    SUM(weekly_demand_units)                         AS demand_units
FROM fact_inventory
GROUP BY strftime('%Y-%m', snapshot_date), category;

-- ---------------------------------------------------------------------------
-- Demand variability by product (coefficient of variation of weekly demand)
--   Powers the demand-variability dashboard tile.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_demand_variability;
CREATE VIEW v_demand_variability AS
WITH weekly AS (
    SELECT
        product_id,
        category,
        AVG(weekly_demand_units) AS mean_wk,
        -- population stdev via E[x^2] - E[x]^2
        AVG(weekly_demand_units * weekly_demand_units)
            - AVG(weekly_demand_units) * AVG(weekly_demand_units) AS var_wk
    FROM fact_inventory
    GROUP BY product_id, category
)
SELECT
    product_id,
    category,
    ROUND(mean_wk, 2)                                 AS mean_weekly_demand,
    ROUND(CASE WHEN var_wk > 0 THEN sqrt(var_wk) ELSE 0 END, 2) AS std_weekly_demand,
    ROUND(CASE WHEN mean_wk > 0
               THEN (CASE WHEN var_wk > 0 THEN sqrt(var_wk) ELSE 0 END) / mean_wk
               ELSE 0 END, 3)                         AS cv_demand
FROM weekly;
