-- ============================================================================
-- data_quality.sql
-- Energy Consumption & Carbon Analytics
--
-- Two parts:
--   PART A — profiling queries (read-only, mirrors src/data_cleaning.py's
--            profile_data_quality() so Python and SQL agree on what's wrong)
--   PART B — staging -> curated transformation (the actual fix), applying
--            the same rules validated in notebooks/01_data_quality.ipynb:
--              data ERRORS get corrected; genuine anomalies get flagged,
--              never deleted.
--
-- NOTE ON HOW THIS WAS VALIDATED: this sandbox has no internet access, so
-- these statements could not be executed against a live PostgreSQL server
-- here. The cleaning LOGIC (dedup rule, imputation rule, capping rule) is
-- the same logic already run and verified in pandas in
-- notebooks/01_data_quality.ipynb -- run these against a real Postgres
-- instance (see reports/postgres_setup.md) and the row counts below should
-- match what that notebook reports.
-- ============================================================================


-- ============================================================================
-- PART A — PROFILING (run against staging.*, nothing is modified)
-- ============================================================================

-- A1. Missing values in the three key measures
SELECT
    COUNT(*) FILTER (WHERE electricity_kwh IS NULL) AS missing_electricity_kwh,
    COUNT(*) FILTER (WHERE natural_gas_kwh IS NULL) AS missing_natural_gas_kwh,
    COUNT(*) FILTER (WHERE occupancy_rate IS NULL)  AS missing_occupancy_rate,
    COUNT(*) AS total_rows
FROM staging.fact_energy;

-- A2. Exact duplicate (building_id, date) combinations
-- Uses ROW_NUMBER() to identify which copies are extras -- this is the one
-- place a window function genuinely earns its keep here (a GROUP BY HAVING
-- COUNT(*) > 1 would tell you THAT duplicates exist, not which specific
-- rows to drop).
SELECT COUNT(*) AS duplicate_rows_to_drop
FROM (
    SELECT record_id,
           ROW_NUMBER() OVER (PARTITION BY building_id, date ORDER BY record_id) AS rn
    FROM staging.fact_energy
) ranked
WHERE rn > 1;

-- A3. Physically impossible values
SELECT
    COUNT(*) FILTER (WHERE electricity_kwh < 0) AS negative_electricity_kwh,
    COUNT(*) FILTER (WHERE occupancy_rate > 1)  AS occupancy_over_100_pct
FROM staging.fact_energy;

-- A4. Date range validity
SELECT COUNT(*) AS out_of_range_dates
FROM staging.fact_energy
WHERE date < DATE '2020-01-01' OR date > DATE '2024-12-31';

-- A5. Referential integrity: orphaned building_id / city references
SELECT 'fact_energy.building_id' AS relationship, COUNT(*) AS orphan_rows
FROM staging.fact_energy fe
WHERE NOT EXISTS (SELECT 1 FROM staging.dim_building db WHERE db.building_id = fe.building_id)
UNION ALL
SELECT 'fact_weather.city', COUNT(*)
FROM staging.fact_weather fw
WHERE NOT EXISTS (SELECT 1 FROM staging.dim_building db WHERE db.city = fw.city)
UNION ALL
SELECT 'fact_maintenance.building_id', COUNT(*)
FROM staging.fact_maintenance fm
WHERE NOT EXISTS (SELECT 1 FROM staging.dim_building db WHERE db.building_id = fm.building_id);

-- A6. Category consistency (should be a short, fixed list -- if this count
-- ever creeps up, something upstream started sending typos/new categories)
SELECT COUNT(DISTINCT building_type) AS distinct_building_types,
       COUNT(DISTINCT city) AS distinct_cities
FROM staging.dim_building;

-- A7. Missing weather
SELECT COUNT(*) AS missing_temperature FROM staging.fact_weather WHERE temperature_f IS NULL;


-- ============================================================================
-- PART B — STAGING -> CURATED (the actual cleaning transformation)
-- ============================================================================

-- B1. Dimensions load straight across (no known issues in dim_building /
-- dim_emission_factor in this dataset -- but they're still profiled above
-- rather than assumed clean).
INSERT INTO curated.dim_building
SELECT building_id, building_name, building_type, city, floor_area_sqft,
       floors, year_built, occupancy_capacity, has_solar
FROM staging.dim_building;

INSERT INTO curated.dim_emission_factor (energy_source, emission_factor, effective_date)
SELECT energy_source, emission_factor, effective_date
FROM staging.dim_emission_factor;

-- B2. fact_energy cleaning
-- Step 1: dedupe (keep first record_id per building_id+date)
-- Step 2: compute building+weekday MEDIANS from the valid (non-negative,
--         non-null) readings only -- percentile_cont(0.5) is Postgres's
--         true-median function, matching the pandas .median() used in
--         the notebook.
-- Step 3: apply fixes -- negative/null electricity & gas & occupancy get
--         the building+weekday median; occupancy>1 gets capped at 1.0.
WITH deduped AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY building_id, date ORDER BY record_id) AS rn
    FROM staging.fact_energy
),
clean_base AS (
    SELECT * FROM deduped WHERE rn = 1
),
weekday_medians AS (
    SELECT building_id,
           EXTRACT(DOW FROM date) AS weekday,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY electricity_kwh)
               FILTER (WHERE electricity_kwh >= 0) AS median_electricity_kwh,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY natural_gas_kwh)
               FILTER (WHERE natural_gas_kwh IS NOT NULL) AS median_gas_kwh,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY occupancy_rate)
               FILTER (WHERE occupancy_rate BETWEEN 0 AND 1) AS median_occupancy_rate
    FROM clean_base
    GROUP BY building_id, EXTRACT(DOW FROM date)
)
INSERT INTO curated.fact_energy
    (building_id, date, electricity_kwh, natural_gas_kwh, renewable_kwh,
     peak_demand_kw, occupancy_rate, operating_hours, is_statistical_outlier)
SELECT
    cb.building_id,
    cb.date,
    CASE WHEN cb.electricity_kwh IS NULL OR cb.electricity_kwh < 0
         THEN wm.median_electricity_kwh ELSE cb.electricity_kwh END,
    CASE WHEN cb.natural_gas_kwh IS NULL
         THEN wm.median_gas_kwh ELSE cb.natural_gas_kwh END,
    cb.renewable_kwh,
    cb.peak_demand_kw,
    CASE WHEN cb.occupancy_rate IS NULL THEN wm.median_occupancy_rate
         WHEN cb.occupancy_rate > 1 THEN 1.0
         ELSE cb.occupancy_rate END,
    cb.operating_hours,
    FALSE  -- statistical outlier flag is computed separately in B4, not here
FROM clean_base cb
JOIN weekday_medians wm
  ON wm.building_id = cb.building_id AND wm.weekday = EXTRACT(DOW FROM cb.date);

-- B3. fact_weather cleaning: missing temperature -> city + day-of-year
-- climatological average (matches clean_fact_weather() in Python).
WITH climatology AS (
    SELECT city, EXTRACT(DOY FROM date) AS doy, AVG(temperature_f) AS avg_temp
    FROM staging.fact_weather
    WHERE temperature_f IS NOT NULL
    GROUP BY city, EXTRACT(DOY FROM date)
)
INSERT INTO curated.fact_weather (date, city, temperature_f, humidity_pct, rainfall_in, wind_speed_mph)
SELECT fw.date, fw.city,
       COALESCE(fw.temperature_f, c.avg_temp),
       fw.humidity_pct, fw.rainfall_in, fw.wind_speed_mph
FROM staging.fact_weather fw
JOIN climatology c ON c.city = fw.city AND c.doy = EXTRACT(DOY FROM fw.date);

-- B4. Statistical outlier flag (modified z-score, median/MAD-based, per
-- building) -- flags, never removes. Mirrors flag_statistical_outliers()
-- in Python; threshold 3.5 matches the notebook.
WITH stats AS (
    SELECT building_id,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY electricity_kwh) AS med
    FROM curated.fact_energy
    GROUP BY building_id
),
mad AS (
    SELECT fe.building_id,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY ABS(fe.electricity_kwh - s.med)) AS mad_val
    FROM curated.fact_energy fe
    JOIN stats s ON s.building_id = fe.building_id
    GROUP BY fe.building_id
)
UPDATE curated.fact_energy fe
SET is_statistical_outlier = TRUE
FROM stats s, mad m
WHERE fe.building_id = s.building_id
  AND fe.building_id = m.building_id
  AND m.mad_val > 0
  AND ABS(0.6745 * (fe.electricity_kwh - s.med) / m.mad_val) > 3.5;

-- B5. fact_energy_cost and fact_maintenance load straight across (no
-- injected issues in this dataset -- profiled, not assumed).
INSERT INTO curated.fact_energy_cost (building_id, month_start, electricity_price, gas_price, demand_charge)
SELECT building_id, date, electricity_price, gas_price, demand_charge
FROM staging.fact_energy_cost;

INSERT INTO curated.fact_maintenance (building_id, maintenance_date, equipment_type, issue_type, downtime_hours, maintenance_cost)
SELECT building_id, maintenance_date, equipment_type, issue_type, downtime_hours, maintenance_cost
FROM staging.fact_maintenance;

-- B6. Log what was done, for the audit trail
INSERT INTO curated.data_quality_log (table_name, check_name, rows_affected)
SELECT 'fact_energy', 'duplicate_rows_dropped',
       (SELECT COUNT(*) FROM staging.fact_energy) - (SELECT COUNT(*) FROM curated.fact_energy)
UNION ALL
SELECT 'fact_energy', 'negative_electricity_corrected',
       (SELECT COUNT(*) FROM staging.fact_energy WHERE electricity_kwh < 0)
UNION ALL
SELECT 'fact_energy', 'occupancy_over_1_capped',
       (SELECT COUNT(*) FROM staging.fact_energy WHERE occupancy_rate > 1)
UNION ALL
SELECT 'fact_energy', 'statistical_outliers_flagged',
       (SELECT COUNT(*) FROM curated.fact_energy WHERE is_statistical_outlier);
