"""Central configuration for the Supply Chain & Demand Planning Analytics project.

All paths are resolved relative to the project root so scripts can be run from
anywhere (e.g. `python src/generate_data.py` or from a notebook).
"""
from __future__ import annotations

from pathlib import Path

# --- Paths ----------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
POWERBI_DIR = DATA_DIR / "powerbi"
REPORTS_DIR = PROJECT_ROOT / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"
SQL_DIR = PROJECT_ROOT / "sql"

DB_PATH = PROCESSED_DIR / "supply_chain.db"

for _d in (RAW_DIR, PROCESSED_DIR, POWERBI_DIR, REPORTS_DIR, FIGURES_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --- Reproducibility ------------------------------------------------------
RANDOM_SEED = 42

# --- Simulation horizon ---------------------------------------------------
# Three full years of daily history gives us seasonality + trend to model.
START_DATE = "2022-01-01"
END_DATE = "2024-12-31"

# Target volume of sales rows. The generator tunes per-product daily demand so
# the total lands comfortably above the 500K headline figure.
TARGET_TRANSACTIONS = 520_000

# --- Catalog dimensions ---------------------------------------------------
N_PRODUCTS = 600
N_SUPPLIERS = 25
N_STORES = 18

# Product categories with relative demand weight and seasonal profile.
# `peak_months` drives a sinusoidal seasonal multiplier in the generator.
CATEGORIES = {
    "Electronics":      {"weight": 0.22, "peak_months": [11, 12], "base_price": 220.0, "margin": 0.28},
    "Home & Kitchen":   {"weight": 0.18, "peak_months": [11, 12, 1], "base_price": 65.0, "margin": 0.42},
    "Apparel":          {"weight": 0.20, "peak_months": [3, 4, 9, 10], "base_price": 45.0, "margin": 0.55},
    "Health & Beauty":  {"weight": 0.15, "peak_months": [1, 2], "base_price": 30.0, "margin": 0.50},
    "Sports & Outdoors":{"weight": 0.13, "peak_months": [5, 6, 7], "base_price": 80.0, "margin": 0.38},
    "Grocery":          {"weight": 0.12, "peak_months": [11, 12], "base_price": 12.0, "margin": 0.22},
}

# --- Inventory / cost assumptions -----------------------------------------
ANNUAL_HOLDING_COST_RATE = 0.25   # carrying cost as a fraction of unit cost / yr
SERVICE_LEVEL_Z = 1.65            # ~95% service level for safety stock
SLOW_MOVING_DAYS = 90             # no/low sales in this window => slow-moving

# --- Currency formatting helper -------------------------------------------
def money(x: float) -> str:
    return f"${x:,.0f}"
