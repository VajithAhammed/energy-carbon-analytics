-- ============================================================================
-- energy_analysis.sql
-- Energy Consumption & Carbon Analytics
--
-- Run against curated.* (after schema.sql + data_quality.sql have populated
-- it -- see reports/postgres_setup.md). Expected values in comments below
-- are cross-validated against src/feature_engineering.py run on the actual
-- cleaned data (see notebooks/02_eda.ipynb) -- not invented.
-- ============================================================================

-- 1. Top 10 highest-consuming buildings (all-time total)
-- Expected top 3: B049, B014, B023 (all Hospitals) -- confirmed in 02_eda.ipynb
SELECT
    b.building_id, b.building_name, b.building_type, b.city,
    ROUND(SUM(fe.electricity_kwh + fe.natural_gas_kwh)::numeric, 0) AS total_kwh
FROM curated.fact_energy fe
JOIN curated.dim_building b ON b.building_id = fe.building_id
GROUP BY b.building_id, b.building_name, b.building_type, b.city
ORDER BY total_kwh DESC
LIMIT 10;

-- 2. Highest energy intensity (EUI, kWh/sqft/year) buildings
-- Controls for building size -- a large building isn't necessarily inefficient,
-- see 02_eda.ipynb Section 3 for the same distinction made in Python.
WITH annual_kwh AS (
    SELECT building_id, EXTRACT(YEAR FROM date)::int AS yr,
           SUM(electricity_kwh + natural_gas_kwh) AS annual_kwh
    FROM curated.fact_energy
    GROUP BY building_id, EXTRACT(YEAR FROM date)
)
SELECT
    b.building_id, b.building_name, b.building_type,
    ROUND(AVG(a.annual_kwh / b.floor_area_sqft)::numeric, 2) AS avg_annual_eui_kwh_per_sqft
FROM annual_kwh a
JOIN curated.dim_building b ON b.building_id = a.building_id
GROUP BY b.building_id, b.building_name, b.building_type, b.floor_area_sqft
ORDER BY avg_annual_eui_kwh_per_sqft DESC
LIMIT 10;

-- 3. Month-over-month energy change, portfolio-wide
-- LAG() genuinely earns its place here: computing "change from prior row"
-- without it would need a self-join on month-1, which LAG replaces cleanly.
WITH monthly AS (
    SELECT DATE_TRUNC('month', date)::date AS month_start,
           SUM(electricity_kwh + natural_gas_kwh) AS total_kwh
    FROM curated.fact_energy
    GROUP BY DATE_TRUNC('month', date)
)
SELECT
    month_start,
    ROUND(total_kwh::numeric, 0) AS total_kwh,
    ROUND(LAG(total_kwh) OVER (ORDER BY month_start)::numeric, 0) AS prior_month_kwh,
    ROUND((100.0 * (total_kwh - LAG(total_kwh) OVER (ORDER BY month_start))
           / NULLIF(LAG(total_kwh) OVER (ORDER BY month_start), 0))::numeric, 2) AS mom_pct_change
FROM monthly
ORDER BY month_start;

-- 4. Year-over-year energy change, portfolio-wide
-- Expected: total energy fell ~-3.2% from 2020 to 2024 -- confirmed in 02_eda.ipynb Section 1.
WITH yearly AS (
    SELECT EXTRACT(YEAR FROM date)::int AS yr,
           SUM(electricity_kwh + natural_gas_kwh) AS total_kwh
    FROM curated.fact_energy
    GROUP BY EXTRACT(YEAR FROM date)
)
SELECT
    yr,
    ROUND(total_kwh::numeric, 0) AS total_kwh,
    ROUND((100.0 * (total_kwh - LAG(total_kwh) OVER (ORDER BY yr))
           / NULLIF(LAG(total_kwh) OVER (ORDER BY yr), 0))::numeric, 2) AS yoy_pct_change
FROM yearly
ORDER BY yr;

-- 5. Rolling 30-day energy consumption, per building
-- ROWS BETWEEN 29 PRECEDING AND CURRENT ROW = a true 30-day trailing window,
-- computed independently per building via PARTITION BY (never mixing one
-- building's history into another's -- same principle as the lag/rolling
-- features in src/feature_engineering.py).
-- NOTE: returns one row per building-day (~91K rows) -- add a WHERE
-- building_id = '...' or a date range filter for interactive use.
SELECT
    building_id, date, electricity_kwh,
    ROUND(AVG(electricity_kwh) OVER (
        PARTITION BY building_id ORDER BY date
        ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
    )::numeric, 2) AS rolling_30day_avg_kwh
FROM curated.fact_energy
ORDER BY building_id, date;

-- 6. Peak demand by building, ranked
-- RANK() (not ROW_NUMBER()) deliberately -- ties should share a rank, since
-- two buildings with the identical peak demand are equally "riskiest," not
-- arbitrarily ordered.
SELECT
    building_id,
    ROUND(MAX(peak_demand_kw)::numeric, 1) AS max_peak_demand_kw,
    RANK() OVER (ORDER BY MAX(peak_demand_kw) DESC) AS demand_rank
FROM curated.fact_energy
GROUP BY building_id
ORDER BY demand_rank
LIMIT 10;
