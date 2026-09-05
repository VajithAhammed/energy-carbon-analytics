# Energy Consumption & Carbon Analytics

### An Intelligent Energy Monitoring, Carbon Intelligence & Demand Forecasting Platform

An end-to-end analytics case study for a (simulated) multi-building
commercial real estate portfolio — from raw data through SQL, Python,
machine learning, and a Power BI decision-support dashboard.

> ⚠️ **This project uses synthetic/simulated data**, clearly labeled
> throughout (see [`data/README.md`](data/README.md)). No real company,
> building, or utility is represented. Everything else — the pipeline,
> the analysis, the models, the honest limitations — is real work,
> genuinely executed and validated, not a template filled with plausible
> numbers.

---

## Problem

A company operating multiple commercial buildings across several cities
needs to answer, with data rather than guesswork: Where is energy being
wasted? Which buildings are inefficient? Which generate the most carbon?
Are there consumption patterns that deserve investigation? What will
demand look like next quarter? Where could reduction efforts have the
biggest impact?

## Solution

A full pipeline — synthetic data generation → PostgreSQL staging/curated
schema → Python data-quality and EDA → three independently-evaluated ML
models (demand forecasting, carbon prediction, anomaly detection) → a
Power BI dashboard blueprint with 20 DAX measures across 6 pages.

## Impact

Supports concrete decisions: which buildings to prioritize for
efficiency investment, where carbon-reduction budget has the biggest
lever (grid decarbonization vs. gas retrofits — see
[`reports/business_insights.md`](reports/business_insights.md)), when to
schedule maintenance around seasonal peak-demand risk, and what a given
energy-reduction target would actually save.

## Tech Stack

Python (Pandas, NumPy, Scikit-Learn, Matplotlib, Seaborn) · SQL
(PostgreSQL) · Power BI (DAX) · Jupyter

---

## Architecture

```
Data (synthetic, 6 tables, ~104K rows)
   → PostgreSQL staging schema (raw, deliberately dirty)
   → Data quality + cleaning (Python & SQL, in parallel)
   → PostgreSQL curated schema (constrained, star-schema)
   → EDA (9 business-question-driven charts)
   → Feature engineering (lag/rolling/calendar, leakage-proven)
   → 3 ML models (demand forecast, carbon prediction, anomaly detection)
   → SQL analytics layer (10 business queries)
   → Power BI (6-page dashboard, 20 DAX measures)
   → Business decisions
```

Repository layout:
```
energy-carbon-analytics/
├── data/            raw + processed CSVs, data dictionary
├── notebooks/       01-06, run in order, every cell actually executed
├── sql/             schema + data quality + 3 analytics files
├── src/             reusable pipeline code (not duplicated into notebooks)
├── powerbi/         data model, DAX measures, page designs, data exports
├── models/          trained models (2 of 3 gitignored — see below)
└── reports/         model results, business insights, setup guides
```

## Dataset

50 buildings, 5 U.S. cities (New York, Chicago, Phoenix, Seattle,
Atlanta — chosen to span distinct climate zones), daily grain,
2020-01-01 through 2024-12-31. **104,270 rows across 6 related tables**
(building attributes, weather, emission factors, energy consumption,
energy cost, maintenance events).

**Why synthetic, not a public dataset:** real public building-energy
datasets (ASHRAE Great Energy Predictor III, NYC Local Law 84) cover
energy + weather at most — this project's business case also needs
occupancy, tariffs, emission factors, renewables, and maintenance tied to
the *same* building, which no public source provides truthfully together.
Full reasoning, the exact data-quality issues deliberately injected, and
a mid-build calibration bug that was found and fixed (original EUI values
were 2-3x too high vs. real building-energy benchmarks) are documented in
[`data/README.md`](data/README.md).

## Data Model

Star schema, two PostgreSQL schemas: `staging` (permissive, mirrors raw
CSVs) and `curated` (constrained, indexed, the one everything downstream
queries). Full DDL in [`sql/schema.sql`](sql/schema.sql), reasoning for
every design choice (including why a `dim_date` table was added beyond
the original brief) inline as SQL comments.

## Data Pipeline

`notebooks/01_data_quality.ipynb` profiles and fixes deliberately
injected issues (3,288 missing values, 45 duplicates, 25 impossible
negative readings, 20 impossible occupancy values, 73 missing weather
readings) while explicitly preserving 147 genuine anomalies as flagged,
not deleted — the core distinction the brief asks for: **data error vs.
business anomaly**. Every fix rule and every count is in the notebook,
executed for real, not asserted.

## EDA

`notebooks/02_eda.ipynb` — 9 charts, each answering one specific business
question (trend, ranking, efficiency, weather, occupancy, carbon, cost,
seasonality, peak demand). Real findings in
[`reports/business_insights.md`](reports/business_insights.md).

## SQL Analytics

`sql/energy_analysis.sql`, `carbon_analysis.sql`, `cost_analysis.sql` —
10 business queries using CTEs, window functions (`LAG`, `RANK`, rolling
frames), and `FILTER`-based conditional aggregation where each genuinely
earns its place (not forced in for the sake of using them). **Honest
note:** this sandbox has no internet access, so these queries are
logic-validated against independently-computed pandas results (see
in-file comments for expected values) but not executed against a live
PostgreSQL server — see [`reports/postgres_setup.md`](reports/postgres_setup.md)
for how to actually run them yourself.

## Machine Learning

Three models, each compared across Linear Regression / Random Forest /
Gradient Boosting with real MAE/RMSE/R² on a chronological (never random)
train/test split:

| Model | Target | Winner | R² | Notebook |
|---|---|---|---|---|
| Demand forecasting | `electricity_kwh` | Random Forest | 0.979 | `04_energy_forecasting.ipynb` |
| Carbon prediction | `carbon_emissions_kgCO2e` | Random Forest | 0.974 | `05_carbon_prediction.ipynb` |
| Anomaly detection | — (Isolation Forest) | — | precision 92.5%, recall 67.3% | `06_anomaly_detection.ipynb` |

The anomaly detection notebook is worth reading even if you skip the
others — it documents 3 real attempts, including a version that scored
badly (F1 0.05) and *why*, before arriving at the version that works
(F1 0.78). Full metrics, feature importances, and stated limitations for
all three models: [`reports/model_results.md`](reports/model_results.md).

A genuine 90-day forward forecast (Q1 2025, not backtested) was generated
using the trained model — validated within 0.2% of the historical Q1
average before being trusted (`src/generate_forecast.py`).

## Dashboard (Power BI)

**Honest limitation:** this project was built in a sandbox with no
Power BI Desktop available (a Windows GUI application), so there is no
live `.pbix` file or real screenshot here. What exists instead is a
complete, implementation-ready blueprint: [`powerbi/README.md`](powerbi/README.md)
(data model + setup), [`powerbi/dax_measures.dax`](powerbi/dax_measures.dax)
(20 measures, each with its business rationale), and
[`powerbi/dashboard_pages.md`](powerbi/dashboard_pages.md) (all 6 required
pages, visual-by-visual). All 9 source data files are already exported to
`powerbi/dashboard/`. Screenshots go in `powerbi/screenshots/` once built.

## Business Insights

See [`reports/business_insights.md`](reports/business_insights.md) for
the full write-up. Highlights: electricity accounts for 92% of portfolio
emissions vs. 8% for gas (grid decarbonization matters more than gas
retrofits here); a real baseload floor persists even at near-zero
occupancy (35% of peak-occupancy load); climate zone drives seasonal
*swing size*, not just average consumption (Phoenix's swing is >4x
Seattle's).

## Scenario Analysis

Power BI Page 6 (What-if parameters + DAX) lets a manager set a target
energy-reduction % and see estimated kWh/cost/CO2 savings update live.
Explicitly labeled **estimated/simulated** per the brief's instruction —
a uniform linear scaling assumption, with the specific limitation (demand
charges don't necessarily scale linearly with average-load reduction)
stated directly in the DAX file's comments, not hidden.

## Limitations

Stated plainly, not buried:

- **Synthetic data.** Patterns are realistic; specific numbers are not
  claims about any real portfolio.
- **No live PostgreSQL or Power BI execution** in the build environment
  — both are logic-validated against independent computations instead;
  see `reports/postgres_setup.md` and `powerbi/README.md` for how to run
  them for real.
- **Weather features are historical actuals, not forecasts** — a
  production forecasting system would need to account for weather
  forecast error on top of the model error reported here.
- **No hyperparameter search** beyond the values shown — deliberate, to
  establish model class rather than chase marginal accuracy.
- **Single chronological train/test split**, not walk-forward
  cross-validation.
- **Anomaly detection's threshold was tuned against synthetic ground
  truth** that wouldn't exist in a real deployment — a production system
  needs a different calibration approach (investigation capacity, cost
  of a missed fault).
- Two of the three trained model files (171MB, 174MB) are gitignored —
  they exceed GitHub's 100MB hard file limit. Regenerate them by running
  the corresponding notebook (fully deterministic, `random_state=42`
  throughout).

## Future Improvements

Walk-forward cross-validation instead of a single split; per-building or
per-building-type anomaly models at larger portfolio scale; a real
weather-forecast API integration for genuine forward forecasting; live
PostgreSQL + Power BI deployment; containerization (Docker); automated
tests and CI for the data pipeline; hyperparameter tuning once model
class is established.

## Installation

```bash
git clone <this-repo-url>
cd energy-carbon-analytics
pip install -r requirements.txt
```

## Usage

Run in order (each stage depends on the previous one's output):

```bash
python src/generate_dataset.py          # generates data/raw/ (~30s, seeded/reproducible)
jupyter notebook notebooks/01_data_quality.ipynb          # → data/processed/
jupyter notebook notebooks/02_eda.ipynb
jupyter notebook notebooks/03_feature_engineering.ipynb    # → data/processed/ml_feature_table.csv
jupyter notebook notebooks/04_energy_forecasting.ipynb     # → models/energy_demand_model.joblib
jupyter notebook notebooks/05_carbon_prediction.ipynb      # → models/carbon_emissions_model.joblib
jupyter notebook notebooks/06_anomaly_detection.ipynb      # → models/anomaly_detection_model.joblib
python src/generate_forecast.py          # → data/processed/energy_forecast_2025Q1.csv (needs Model 1 trained first)
```

For SQL: see [`reports/postgres_setup.md`](reports/postgres_setup.md) to
stand up a real PostgreSQL instance, then run `sql/schema.sql` →
`sql/data_quality.sql` → the three analytics files.

For Power BI: open Power BI Desktop → import the 9 CSVs from
`powerbi/dashboard/` → follow `powerbi/README.md` and
`powerbi/dashboard_pages.md`.

## Screenshots

None yet — see the note above under **Dashboard (Power BI)**. Once built,
screenshots belong in `powerbi/screenshots/` (see that folder's README
for the expected filenames).

## License

MIT — see [`LICENSE`](LICENSE).
