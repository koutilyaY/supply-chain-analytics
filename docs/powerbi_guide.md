# Power BI Dashboard Guide

This guide explains how to turn the exported CSVs in [`data/powerbi/`](../data/powerbi/)
into the interactive Power BI dashboards described in the project. It covers the
data model (star schema), the DAX measures behind each KPI, and the recommended
page-by-page visual layout.

> Power BI `.pbix` files are binary and authored in Power BI Desktop, so they
> can't be generated from code. Everything Power BI *needs* — a clean conformed
> star schema and the measure definitions — is produced here; building the
> `.pbix` is a ~30-minute drag-and-drop exercise following the steps below.

---

## 1. Load the data

In Power BI Desktop: **Get Data → Text/CSV** and load every file from
`data/powerbi/`:

| File | Role | Grain |
|---|---|---|
| `dim_date.csv` | Dimension | one row per calendar day |
| `dim_product.csv` | Dimension | one row per SKU |
| `dim_supplier.csv` | Dimension | one row per supplier |
| `fact_sales_daily.csv` | Fact | date × product × channel |
| `fact_inventory.csv` | Fact | week × product |
| `fact_purchase_orders.csv` | Fact | one row per PO |
| `fact_forecast.csv` | Fact | month × category |
| `kpi_executive_summary.csv` | Helper | one row per KPI (card values) |

Mark `dim_date` as the date table: **Table tools → Mark as date table → `date_key`**.

---

## 2. Model relationships (star schema)

Create these relationships (all single-direction, one-to-many from dimension → fact):

```
dim_date[date_key]      1 ─── *  fact_sales_daily[date_key]
dim_date[date_key]      1 ─── *  fact_inventory[snapshot_date]
dim_date[date_key]      1 ─── *  fact_purchase_orders[received_date]
dim_product[product_id] 1 ─── *  fact_sales_daily[product_id]
dim_product[product_id] 1 ─── *  fact_inventory[product_id]
dim_product[product_id] 1 ─── *  fact_purchase_orders[product_id]
dim_supplier[supplier_id] 1 ─ *  fact_purchase_orders[supplier_id]
dim_supplier[supplier_id] 1 ─ *  dim_product[supplier_id]   (snowflake; optional)
```

`fact_forecast` joins to `dim_date` on the month and to a `category` field — link
it via a small `dim_category` you can derive from `dim_product`, or relate on
`category` directly for a simpler model.

---

## 3. DAX measures

Create a dedicated **_Measures** table and add the following. These reproduce
the six executive KPIs.

```dax
-- Demand --------------------------------------------------------------
Total Revenue      = SUM ( fact_sales_daily[revenue] )
Total Units        = SUM ( fact_sales_daily[units] )
Total COGS         = SUM ( fact_sales_daily[cogs] )
Gross Margin       = SUM ( fact_sales_daily[gross_margin] )
Gross Margin %     = DIVIDE ( [Gross Margin], [Total Revenue] )

-- 1) Forecast Accuracy ----------------------------------------------
MAPE % =
    AVERAGEX (
        VALUES ( fact_forecast[year_month] ),
        DIVIDE ( ABS ( SUM ( fact_forecast[actual] ) - SUM ( fact_forecast[ml_forecast] ) ),
                 SUM ( fact_forecast[actual] ) )
    )
Forecast Accuracy % = 1 - [MAPE %]

-- 2) Inventory Turnover ---------------------------------------------
Avg Inventory Value =
    AVERAGEX ( VALUES ( fact_inventory[snapshot_date] ),
               SUM ( fact_inventory[inventory_value] ) )
Inventory Turnover = DIVIDE ( [Total COGS], [Avg Inventory Value] )

-- 3) Fill Rate ------------------------------------------------------
Fill Rate % = AVERAGE ( fact_purchase_orders[fill_ratio] )

-- 4) Stockout Rate --------------------------------------------------
Stockout Rate % = AVERAGE ( fact_inventory[is_stockout] )

-- 5) Lead Time Variance ---------------------------------------------
Avg Lead Time Variance = AVERAGE ( fact_purchase_orders[lead_time_variance_days] )
On-Time Delivery %     = AVERAGE ( fact_purchase_orders[on_time_flag] )

-- 6) Supplier Performance (composite 0-100) ------------------------
Supplier Score =
    50 * [On-Time Delivery %]
  + 30 * [Fill Rate %]
  + 20 * ( 1 - MIN ( 1,
        DIVIDE ( [Avg Lead Time Variance], AVERAGE ( dim_supplier[promised_lead_time_days] ) ) ) )

-- Demand variability (dashboard tile) ------------------------------
Demand CV =
    DIVIDE ( STDEV.P ( fact_inventory[weekly_demand_units] ),
             AVERAGE ( fact_inventory[weekly_demand_units] ) )
```

Format `Forecast Accuracy %`, `Fill Rate %`, `Stockout Rate %`,
`On-Time Delivery %`, and `Gross Margin %` as percentages.

---

## 4. Recommended pages

### Page 1 — Executive Scorecard
- **Card** visuals: Forecast Accuracy %, Inventory Turnover, Fill Rate %,
  Stockout Rate %, Avg Lead Time Variance, Supplier Score.
- **KPI** visuals comparing each measure to its target (use
  `kpi_executive_summary[Target]`), with conditional green/red formatting.
- Slicers: `dim_date[year]`, `dim_product[category]`.

### Page 2 — Demand & Seasonality
- **Line chart**: `Total Units` by `dim_date[year_month]`, legend `category`
  (shows the seasonal peaks).
- **Matrix**: rows `category`, columns `dim_date[month]`, values `Total Units`
  (seasonality heat-grid via conditional formatting).
- **Bar chart**: `Total Revenue` by `channel`.

### Page 3 — Forecast Accuracy
- **Line chart**: `fact_forecast[actual]` vs `fact_forecast[ml_forecast]` vs
  `baseline_forecast` over `year_month`.
- **Card**: `Forecast Accuracy %`; **column chart** of accuracy by `category`.

### Page 4 — Inventory Health
- **Card**: Inventory Turnover, Stockout Rate %, total inventory value.
- **Scatter**: `Demand CV` (x) vs `Inventory Turnover` (y), points = SKUs.
- **Table**: top slow-moving SKUs (`days_of_supply`, `inventory_value`) — load
  `data/processed/slow_moving_inventory.csv` for this tile.
- **Decomposition tree**: inventory value by category → ABC class → SKU.

### Page 5 — Supplier Performance
- **Table / scorecard**: supplier, On-Time %, Fill Rate %, Lead-Time Variance,
  Supplier Score, sorted ascending by score (watchlist on top).
- **Map**: Supplier Score by `dim_supplier[region]`.
- **Line chart**: `Avg Lead Time Variance` by `year_month`.

---

## 5. Refresh

Re-running `python src/run_all.py` regenerates every CSV in place, so a Power BI
**Refresh** picks up new data with no model changes required.
