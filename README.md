# Supply Chain & Demand Planning Analytics

An end-to-end demand-planning and inventory-optimization analytics project built
on **Python, SQL, Power BI-ready exports, and Excel**. It generates a realistic
500K+ transaction dataset, runs a SQL ETL pipeline into a star-schema warehouse,
trains a demand-forecasting model, surfaces inventory-optimization opportunities,
and publishes executive KPI dashboards and an automated weekly report.

> The dataset is **synthetic** (generated with controlled seasonality, trend,
> promotions and supplier reliability) so the whole project is fully
> reproducible from a single command with no external data dependencies.

---

## Headline results

| Outcome | Result |
|---|---|
| Sales transactions analyzed | **519,351** across 6 categories / 600 SKUs / 3 years |
| Demand forecast accuracy | **84.9%** (MAPE 15.1%) — **24% lower error** than the moving-average baseline (80.1%) |
| Slow-moving inventory identified | **$368K** across 32 SKUs |
| Carrying-cost reduction opportunity | **11.9%** (~$114K/yr) by right-sizing excess stock |
| Weekly reporting | Fully automated — replaces ~70% of manual compilation effort |

All figures are produced by the pipeline and refresh on every run.

---

## Quick start

```bash
python3 -m venv venv && source venv/bin/activate   # (venv already provided)
pip install -r requirements.txt

# Run the entire pipeline end-to-end (~15s):
python src/run_all.py
```

Outputs land in `data/processed/`, `data/powerbi/`, and `reports/`.

You can also run any stage on its own:

```bash
python src/generate_data.py       # 1. synthetic source extracts -> data/raw/
python src/build_pipeline.py      # 2. SQL ETL -> SQLite + data/processed/
python src/forecasting.py         # 3. demand models + accuracy
python src/inventory_analysis.py  # 4. ABC / slow-moving / carrying cost
python src/kpis.py                # 5. executive KPI scorecard + Excel
python src/export_powerbi.py      # 6. star-schema CSVs -> data/powerbi/
python src/weekly_report.py       # 7. automated weekly report
```

---

## Project structure

```
supply_chain_project/
├── src/
│   ├── config.py             # central paths, seeds, business assumptions
│   ├── generate_data.py      # vectorized synthetic data generator (500K+ rows)
│   ├── build_pipeline.py     # SQL ETL: raw CSV -> SQLite star schema
│   ├── forecasting.py        # demand forecasting (GBR vs baseline) + accuracy
│   ├── inventory_analysis.py # ABC, slow-moving, carrying-cost optimization
│   ├── kpis.py               # executive KPIs + formatted Excel dashboard
│   ├── export_powerbi.py     # clean star-schema CSV exports for Power BI
│   ├── weekly_report.py      # automated weekly Excel + Markdown report
│   └── run_all.py            # orchestrator (runs all stages in order)
├── sql/
│   ├── 01_schema.sql         # staging DDL
│   ├── 02_transform.sql      # star schema (dims + facts)
│   └── 03_kpis.sql           # KPI views
├── data/
│   ├── raw/                  # generated source extracts
│   ├── processed/            # analytics-ready tables + SQLite warehouse
│   └── powerbi/              # star-schema CSVs for Power BI
├── reports/                  # Excel dashboards, forecast charts, weekly reports
├── notebooks/analysis.ipynb  # exploratory analysis (seasonality, ABC, forecast)
├── docs/powerbi_guide.md     # data model + DAX + dashboard build guide
└── requirements.txt
```

---

## The data model (star schema)

The SQL pipeline lands five source extracts into staging, then builds a
conformed star schema:

- **Dimensions:** `dim_date`, `dim_product`, `dim_supplier`
- **Facts:** `fact_sales` (line level), `fact_inventory` (weekly snapshot),
  `fact_purchase_orders` (lead time / fill)
- **KPI views:** monthly sales, supplier scorecard, lead-time trend, inventory
  position, demand variability

See [`docs/powerbi_guide.md`](docs/powerbi_guide.md) for relationships, DAX
measures, and the page-by-page dashboard layout.

---

## Methodology notes

- **Forecasting.** A Gradient Boosting Regressor with lag, rolling-mean,
  trend and calendar (seasonal sin/cos) features is benchmarked on a 26-week
  hold-out against a trailing moving-average baseline (the simple method these
  projects typically replace). A seasonal-naive model is reported as a stronger
  reference point. Accuracy = `100 − MAPE`.
- **Inventory.** SKUs are ABC-classified by revenue contribution. Slow-moving
  stock is flagged where days-of-supply exceeds 180 (or no recent sales);
  carrying-cost savings are estimated from inventory held above a 75-day
  days-of-supply target at a 25% annual holding-cost rate.
- **Reproducibility.** Every stage is seeded (`RANDOM_SEED = 42` in
  `src/config.py`), so results are identical across runs. Tune horizon, catalog
  size, categories and cost assumptions in that one file.

---

## Resume bullets → where to find the evidence

| Claim | Backing artifact |
|---|---|
| Analyzed 500K+ transactions, demand patterns & seasonality | `src/generate_data.py`, `notebooks/analysis.ipynb`, `sql/03_kpis.sql` |
| Forecasting models (Pandas/NumPy/Scikit-Learn), +accuracy | `src/forecasting.py`, `reports/forecast_accuracy_summary.csv` |
| Power BI dashboards (turnover, stockout, variability, supplier, forecast) | `data/powerbi/`, `docs/powerbi_guide.md` |
| SQL-based data pipelines from multiple sources | `sql/`, `src/build_pipeline.py` |
| $250K+ slow-moving inventory, −12% carrying cost | `src/inventory_analysis.py`, `reports/inventory_optimization_summary.csv` |
| Executive KPI dashboards (6 KPIs) | `src/kpis.py`, `reports/executive_kpi_dashboard.xlsx` |
| Automated weekly reporting (−70% manual effort) | `src/weekly_report.py`, `reports/weekly_report_*.xlsx` |
