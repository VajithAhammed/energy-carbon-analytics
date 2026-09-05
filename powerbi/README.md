# Power BI — Build Guide

> ⚠️ **Environment limitation, stated plainly:** the sandbox this project
> was built in has no Power BI Desktop (it's a Windows GUI application —
> genuinely can't run in a Linux sandbox with no display). Nothing in
> `powerbi/` is a working `.pbix` file or a real screenshot. What's here
> is a complete, implementation-ready blueprint — data files, every DAX
> measure with its formula and business rationale, and a page-by-page
> design — that you build in Power BI Desktop by following this
> document. Every number quoted below as an "expected value" was
> computed for real in the Python notebooks, not guessed.

## Setup

1. Open Power BI Desktop → **Get Data → Text/CSV** → import all 9 files
   from `powerbi/dashboard/`:
   `dim_building.csv`, `dim_date.csv`, `dim_emission_factor.csv`,
   `fact_energy.csv`, `fact_weather.csv`, `fact_energy_cost.csv`,
   `fact_maintenance.csv`, `anomaly_flags.csv`, `energy_forecast_2025Q1.csv`.
2. (Alternative) If you set up the real PostgreSQL instance from
   `reports/postgres_setup.md`, connect to `curated.*` directly via
   **Get Data → PostgreSQL** instead of CSVs — same tables, live
   connection.
3. In Power Query, confirm data types: `date` columns as Date, `*_kwh`/
   `*_cost`/`*_price` as Decimal Number, `building_id` as Text,
   `is_statistical_outlier`/`has_solar`/`anomaly_flag`/`is_weekend` as
   True/False.

## Data model (star schema)

**Design principle carried over from `sql/schema.sql`:** dimensions are
small, facts are where the numbers live. `dim_emission_factor` is
deliberately **not** a modeled relationship (see below) — it's a lookup
table read through DAX, not joined through the model.

| From | To | Cardinality | Cross-filter | Why |
|---|---|---|---|---|
| `dim_building[building_id]` | `fact_energy[building_id]` | 1:* | Single | core fact table |
| `dim_building[building_id]` | `fact_energy_cost[building_id]` | 1:* | Single | |
| `dim_building[building_id]` | `fact_maintenance[building_id]` | 1:* | Single | |
| `dim_building[building_id]` | `anomaly_flags[building_id]` | 1:* | Single | |
| `dim_building[building_id]` | `energy_forecast_2025Q1[building_id]` | 1:* | Single | |
| `dim_date[date]` | `fact_energy[date]` | 1:* | Single | enables the built-in time-intelligence functions (`SAMEPERIODLASTYEAR`, etc.) |
| `dim_date[date]` | `fact_weather[date]` | 1:* | Single | |
| `dim_date[date]` | `anomaly_flags[date]` | 1:* | Single | |
| `dim_date[date]` | `energy_forecast_2025Q1[date]` | 1:* | Single | `dim_date` is deliberately extended through 2025-03-31 to cover the forecast |

**Why no relationship to `fact_weather` from `dim_building`:** weather is
inherently city-grain (5 cities), not building-grain (50 buildings) — a
direct many-to-many would need a bridge table for no real benefit. Instead,
add a **calculated column** on `fact_energy`:

```dax
Temperature (F) =
LOOKUPVALUE(
    fact_weather[temperature_f],
    fact_weather[city], RELATED(dim_building[city]),
    fact_weather[date], fact_energy[date]
)
```

This is the DAX-native version of the same join `src/feature_engineering.py`
does in pandas (`build_daily_analysis_table`) — one definition of "this
row's weather," not two that could drift apart.

**Why no relationship to `dim_emission_factor`:** the correct factor for
a `fact_energy` row depends on BOTH `energy_source` (electricity vs gas —
not a column that exists per-row, since both are separate columns on the
same row) AND year. That doesn't fit a clean 1:many relationship, so
carbon measures use `LOOKUPVALUE` directly (see `dax_measures.dax`,
`Total Carbon (kg CO2e)`) — matching the same "join by year" logic
`sql/carbon_analysis.sql` uses.

## What-if parameters (Page 6)

Create via **Modeling → New Parameter → Numeric range**:

| Parameter | Range | Generates |
|---|---|---|
| Energy Reduction % | 0% to 30%, step 1%, default 10% | `'Energy Reduction %'[Energy Reduction % Value]` |
| Renewable Increase % | 0% to 20%, step 1%, default 5% | `'Renewable Increase %'[Renewable Increase % Value]` |

Power BI auto-generates a small parameter table and a matching measure
for each — referenced directly in the scenario DAX measures.

## Expected KPI card values (Page 1)

Cross-validated in `notebooks/02_eda.ipynb` and `src/feature_engineering.py`
on the full 2020-2024 cleaned dataset — your Power BI totals should land
at or near these once the model is built (small rounding differences are
fine; a large mismatch means a relationship or measure is wrong):

| KPI | Expected value |
|---|---|
| Total Energy (2020-2024) | 411,526,962 kWh |
| Total Carbon | 144,367,517 kg CO2e |
| Total Cost (energy + demand charges) | $96,341,133 |
| Electricity / Gas CO2e split | 92.0% / 8.0% |
| YoY Energy Change, 2020→2024 | -3.2% |
