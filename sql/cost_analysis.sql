-- ============================================================================
-- cost_analysis.sql
-- Energy Consumption & Carbon Analytics
--
-- Expected values cross-validated against src/feature_engineering.py's
-- build_monthly_cost_table() run on the actual cleaned data.
-- ============================================================================

-- 10. Highest energy-cost buildings (5-year total, energy + demand charges)
-- GRAIN NOTE: demand_charge is billed once per MONTH against that month's
-- peak kW, never spread across days -- see data/README.md and
-- src/feature_engineering.py's build_monthly_cost_table() docstring for the
-- full reasoning. Getting this grain wrong would double-count or dilute the
-- demand charge, which is often 20-40% of a commercial building's bill.
-- Expected top 3: B049, B014, B023 -- confirmed in the pandas cross-check
-- (same buildings top the consumption ranking, but not in the same order --
-- see cost-per-sqft note below for why cost and consumption rankings diverge).
WITH monthly_energy_cost AS (
    SELECT
        fe.building_id,
        DATE_TRUNC('month', fe.date)::date AS month_start,
        SUM(fe.electricity_kwh * fc.electricity_price + fe.natural_gas_kwh * fc.gas_price) AS energy_cost,
        MAX(fe.peak_demand_kw) AS month_peak_demand_kw
    FROM curated.fact_energy fe
    JOIN curated.fact_energy_cost fc
        ON fc.building_id = fe.building_id AND fc.month_start = DATE_TRUNC('month', fe.date)::date
    GROUP BY fe.building_id, DATE_TRUNC('month', fe.date)
),
monthly_total_cost AS (
    SELECT
        mec.building_id, mec.month_start, mec.energy_cost,
        mec.month_peak_demand_kw * fc.demand_charge AS demand_cost,
        mec.energy_cost + (mec.month_peak_demand_kw * fc.demand_charge) AS total_cost
    FROM monthly_energy_cost mec
    JOIN curated.fact_energy_cost fc
        ON fc.building_id = mec.building_id AND fc.month_start = mec.month_start
)
SELECT
    b.building_id, b.building_name, b.city,
    ROUND(SUM(mtc.total_cost)::numeric, 0) AS total_cost_5yr,
    ROUND((SUM(mtc.total_cost) / b.floor_area_sqft)::numeric, 2) AS cost_per_sqft_5yr
FROM monthly_total_cost mtc
JOIN curated.dim_building b ON b.building_id = mtc.building_id
GROUP BY b.building_id, b.building_name, b.city, b.floor_area_sqft
ORDER BY total_cost_5yr DESC
LIMIT 10;

-- Bonus: cost per sqft tells a different story than raw total cost -- a
-- smaller building in an expensive city (e.g. New York) can cost more per
-- sqft than a bigger building that simply uses more energy overall.
-- Expected top 5 are all New York buildings (~$20-22/sqft) despite New York
-- buildings not dominating the raw-total-cost ranking above -- confirmed in
-- the pandas cross-check (top: B035 at $21.91/sqft).
WITH monthly_energy_cost AS (
    SELECT
        fe.building_id, DATE_TRUNC('month', fe.date)::date AS month_start,
        SUM(fe.electricity_kwh * fc.electricity_price + fe.natural_gas_kwh * fc.gas_price) AS energy_cost,
        MAX(fe.peak_demand_kw) AS month_peak_demand_kw
    FROM curated.fact_energy fe
    JOIN curated.fact_energy_cost fc
        ON fc.building_id = fe.building_id AND fc.month_start = DATE_TRUNC('month', fe.date)::date
    GROUP BY fe.building_id, DATE_TRUNC('month', fe.date)
),
monthly_total_cost AS (
    SELECT mec.building_id, mec.energy_cost + (mec.month_peak_demand_kw * fc.demand_charge) AS total_cost
    FROM monthly_energy_cost mec
    JOIN curated.fact_energy_cost fc ON fc.building_id = mec.building_id AND fc.month_start = mec.month_start
)
SELECT
    b.building_id, b.building_name, b.city,
    ROUND((SUM(mtc.total_cost) / b.floor_area_sqft)::numeric, 2) AS cost_per_sqft_5yr
FROM monthly_total_cost mtc
JOIN curated.dim_building b ON b.building_id = mtc.building_id
GROUP BY b.building_id, b.building_name, b.city, b.floor_area_sqft
ORDER BY cost_per_sqft_5yr DESC
LIMIT 10;
