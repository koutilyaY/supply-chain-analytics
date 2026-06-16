"""End-to-end pipeline orchestrator.

Runs every stage of the project in dependency order:

    1. generate_data      - synthetic source extracts -> data/raw/
    2. build_pipeline     - SQL ETL -> SQLite warehouse + data/processed/
    3. forecasting        - demand models + accuracy -> reports/, processed/
    4. inventory_analysis - ABC / slow-moving / carrying cost -> processed/
    5. kpis               - executive KPI scorecard + Excel -> reports/
    6. export_powerbi     - star-schema CSVs -> data/powerbi/
    7. weekly_report      - automated weekly report -> reports/

Run:  python src/run_all.py
"""
from __future__ import annotations

import time

import build_pipeline
import export_powerbi
import forecasting
import generate_data
import inventory_analysis
import kpis
import weekly_report

STAGES = [
    ("Generate synthetic data", generate_data.main),
    ("Build SQL pipeline", build_pipeline.main),
    ("Demand forecasting", forecasting.run),
    ("Inventory optimization", inventory_analysis.analyze),
    ("Executive KPIs", kpis.compute),
    ("Power BI export", export_powerbi.main),
    ("Weekly report", weekly_report.build_report),
]


def main() -> None:
    t0 = time.time()
    for i, (name, fn) in enumerate(STAGES, 1):
        print("\n" + "#" * 70)
        print(f"# STAGE {i}/{len(STAGES)}: {name}")
        print("#" * 70)
        fn()
    print(f"\nAll stages complete in {time.time() - t0:.1f}s.")


if __name__ == "__main__":
    main()
