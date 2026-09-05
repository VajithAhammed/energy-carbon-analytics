-- ============================================================================
-- carbon_analysis.sql
-- Energy Consumption & Carbon Analytics
--
-- Expected values cross-validated against src/feature_engineering.py /
-- notebooks/02_eda.ipynb on the actual cleaned data.
-- ============================================================================

-- 7. Carbon emissions by energy source
-- Reproduces the CONVENTION documented in src/feature_engineering.py:
-- renewable_kwh is a SUBSET of electricity_kwh (self-generated solar), so
-- grid_electricity_kwh = electricity_kwh - renewable_kwh carries the grid
-- emission factor; renewable's own factor is 0 and drops out naturally.
-- Joins to dim_emission_factor BY YEAR (factors change annually, not daily).
-- Expected split: ~92% electricity / ~8% natural gas -- confirmed in 02_eda.ipynb Section 6.
WITH yearly_factors AS (
    SELECT energy_source, EXTRACT(YEAR FROM effective_date)::int AS yr, emission_factor
    FROM curated.dim_emission_factor
),
energy_by_year AS (
    SELECT
        EXTRACT(YEAR FROM date)::int AS yr,
        SUM(electricity_kwh - renewable_kwh) AS grid_electricity_kwh,
        SUM(natural_gas_kwh) AS natural_gas_kwh
    FROM curated.fact_energy
    GROUP BY EXTRACT(YEAR FROM date)
)
SELECT 'Electricity' AS source, ROUND(SUM(e.grid_electricity_kwh * f.emission_factor)::numeric, 0) AS total_co2e_kg
FROM energy_by_year e
JOIN yearly_factors f ON f.energy_source = 'Grid Electricity' AND f.yr = e.yr
UNION ALL
SELECT 'Natural Gas', ROUND(SUM(e.natural_gas_kwh * f.emission_factor)::numeric, 0)
FROM energy_by_year e
JOIN yearly_factors f ON f.energy_source = 'Natural Gas' AND f.yr = e.yr;

-- 8. Buildings with unusual consumption
-- Reuses the is_statistical_outlier flag set during cleaning (data_quality.sql
-- Part B4) rather than recomputing z-scores here -- one definition of
-- "unusual," not two that could quietly drift apart.
-- Expected top building: B049 (54 flagged days) -- confirmed in the pandas cross-check.
SELECT
    building_id,
    COUNT(*) FILTER (WHERE is_statistical_outlier) AS outlier_days,
    COUNT(*) AS total_days,
    ROUND((100.0 * COUNT(*) FILTER (WHERE is_statistical_outlier) / COUNT(*))::numeric, 3) AS outlier_pct
FROM curated.fact_energy
GROUP BY building_id
HAVING COUNT(*) FILTER (WHERE is_statistical_outlier) > 0
ORDER BY outlier_days DESC
LIMIT 10;

-- 9. Renewable energy contribution, by building
-- CASE used to label buildings without solar explicitly, rather than letting
-- a 0%/NULL row look like a data gap.
-- Expected: solar buildings run ~10-11% renewable contribution; 0 for the rest.
SELECT
    b.building_id, b.building_name,
    CASE WHEN b.has_solar THEN 'Has solar' ELSE 'No solar' END AS solar_status,
    ROUND(SUM(fe.renewable_kwh)::numeric, 0) AS total_renewable_kwh,
    ROUND(SUM(fe.electricity_kwh)::numeric, 0) AS total_electricity_kwh,
    ROUND((100.0 * SUM(fe.renewable_kwh) / NULLIF(SUM(fe.electricity_kwh), 0))::numeric, 2) AS renewable_pct
FROM curated.fact_energy fe
JOIN curated.dim_building b ON b.building_id = fe.building_id
GROUP BY b.building_id, b.building_name, b.has_solar
ORDER BY renewable_pct DESC NULLS LAST
LIMIT 15;
