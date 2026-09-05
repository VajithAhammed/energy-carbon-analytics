-- ============================================================================
-- schema.sql
-- Energy Consumption & Carbon Analytics — PostgreSQL schema
-- ============================================================================
-- DESIGN DECISION: two schemas, not one.
--
--   staging.*  — mirrors the raw CSVs almost exactly. Minimal constraints,
--                because the raw data is DELIBERATELY dirty (see
--                data/README.md) and staging's job is just to hold what
--                was loaded, unmodified, so the cleaning logic in
--                data_quality.sql has something real to work against.
--
--   curated.*  — the trusted, constrained, indexed tables that SQL
--                analytics, Python notebooks, and Power BI actually query.
--                Star-schema shaped: fact_energy / fact_weather /
--                fact_energy_cost / fact_maintenance as facts,
--                dim_building / dim_date / dim_emission_factor as
--                dimensions.
--
-- ALTERNATIVE CONSIDERED: one schema, load straight into constrained
-- tables. Rejected — a NOT NULL / CHECK constraint would simply reject
-- the dirty rows on load, which means the "data quality" stage would have
-- nothing to do and no error counts to report. Staging lets errors land
-- safely so they can be profiled, not silently rejected.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS curated;

-- ----------------------------------------------------------------------------
-- STAGING TABLES — one per raw CSV, permissive types, no FK/CHECK constraints
-- ----------------------------------------------------------------------------

CREATE TABLE staging.dim_building (
    building_id         VARCHAR(10),
    building_name        TEXT,
    building_type        TEXT,
    city                  TEXT,
    floor_area_sqft       NUMERIC,
    floors                INTEGER,
    year_built            INTEGER,
    occupancy_capacity    INTEGER,
    has_solar             BOOLEAN
);

CREATE TABLE staging.fact_weather (
    date              DATE,
    city              TEXT,
    temperature_f     NUMERIC,   -- nullable on purpose: raw data has missing readings
    humidity_pct      NUMERIC,
    rainfall_in       NUMERIC,
    wind_speed_mph    NUMERIC
);

CREATE TABLE staging.dim_emission_factor (
    energy_source     TEXT,
    emission_factor   NUMERIC,
    effective_date    DATE
);

CREATE TABLE staging.fact_energy (
    record_id          INTEGER,
    building_id        VARCHAR(10),
    date               DATE,
    electricity_kwh    NUMERIC,  -- nullable AND can be negative in staging (raw data error)
    natural_gas_kwh    NUMERIC,
    renewable_kwh      NUMERIC,
    peak_demand_kw     NUMERIC,
    occupancy_rate     NUMERIC,  -- can exceed 1 in staging (raw data error)
    operating_hours    NUMERIC
);

CREATE TABLE staging.fact_energy_cost (
    date                DATE,
    building_id         VARCHAR(10),
    electricity_price   NUMERIC,
    gas_price           NUMERIC,
    demand_charge       NUMERIC
);

CREATE TABLE staging.fact_maintenance (
    maintenance_id      INTEGER,
    building_id         VARCHAR(10),
    maintenance_date    DATE,
    equipment_type       TEXT,
    issue_type            TEXT,
    downtime_hours        NUMERIC,
    maintenance_cost      NUMERIC
);

-- Load staging tables from the CSVs in data/raw/, e.g.:
--   \copy staging.dim_building      FROM 'data/raw/dim_building.csv'      CSV HEADER;
--   \copy staging.fact_weather      FROM 'data/raw/fact_weather.csv'      CSV HEADER;
--   \copy staging.dim_emission_factor FROM 'data/raw/dim_emission_factor.csv' CSV HEADER;
--   \copy staging.fact_energy       FROM 'data/raw/fact_energy.csv'       CSV HEADER;
--   \copy staging.fact_energy_cost  FROM 'data/raw/fact_energy_cost.csv'  CSV HEADER;
--   \copy staging.fact_maintenance  FROM 'data/raw/fact_maintenance.csv'  CSV HEADER;

-- ----------------------------------------------------------------------------
-- CURATED DIMENSION TABLES
-- ----------------------------------------------------------------------------

CREATE TABLE curated.dim_building (
    building_id          VARCHAR(10)  PRIMARY KEY,
    building_name         TEXT NOT NULL,
    building_type         VARCHAR(20) NOT NULL
        CHECK (building_type IN ('Office','Retail','Hospital','School','Warehouse','Mixed-Use')),
    city                   VARCHAR(50) NOT NULL,
    floor_area_sqft        NUMERIC NOT NULL CHECK (floor_area_sqft > 0),
    floors                 INTEGER NOT NULL CHECK (floors > 0),
    year_built              INTEGER NOT NULL CHECK (year_built BETWEEN 1800 AND 2100),
    occupancy_capacity      INTEGER NOT NULL CHECK (occupancy_capacity > 0),
    has_solar                BOOLEAN NOT NULL DEFAULT FALSE
);

-- DESIGN DECISION: a date dimension. Not in the original raw CSVs, but the
-- brief itself says "adapt the model if the actual dataset requires a
-- better design" -- a date dim is the standard star-schema pattern for
-- Power BI (clean YoY/MoM slicers, fiscal periods, a single place that
-- defines "what week/quarter is this date in") instead of computing
-- calendar logic redundantly in every DAX measure.
CREATE TABLE curated.dim_date (
    date            DATE PRIMARY KEY,
    year            INTEGER NOT NULL,
    quarter         INTEGER NOT NULL,
    month           INTEGER NOT NULL,
    month_name      VARCHAR(10) NOT NULL,
    day             INTEGER NOT NULL,
    day_of_week     INTEGER NOT NULL,       -- 0=Sunday .. 6=Saturday
    day_name        VARCHAR(10) NOT NULL,
    is_weekend      BOOLEAN NOT NULL,
    week_of_year    INTEGER NOT NULL
);

INSERT INTO curated.dim_date
SELECT
    d::DATE,
    EXTRACT(YEAR FROM d)::INT,
    EXTRACT(QUARTER FROM d)::INT,
    EXTRACT(MONTH FROM d)::INT,
    TO_CHAR(d, 'Month'),
    EXTRACT(DAY FROM d)::INT,
    EXTRACT(DOW FROM d)::INT,
    TO_CHAR(d, 'Day'),
    EXTRACT(DOW FROM d) IN (0, 6),
    EXTRACT(WEEK FROM d)::INT
FROM generate_series('2020-01-01'::DATE, '2024-12-31'::DATE, '1 day'::INTERVAL) AS d;

CREATE TABLE curated.dim_emission_factor (
    emission_factor_id   SERIAL PRIMARY KEY,
    energy_source          VARCHAR(30) NOT NULL,
    emission_factor         NUMERIC NOT NULL CHECK (emission_factor >= 0),
    effective_date           DATE NOT NULL,
    UNIQUE (energy_source, effective_date)
);

-- ----------------------------------------------------------------------------
-- CURATED FACT TABLES
-- ----------------------------------------------------------------------------

CREATE TABLE curated.fact_energy (
    record_id             SERIAL PRIMARY KEY,
    building_id           VARCHAR(10) NOT NULL REFERENCES curated.dim_building(building_id),
    date                  DATE NOT NULL REFERENCES curated.dim_date(date),
    electricity_kwh       NUMERIC NOT NULL CHECK (electricity_kwh >= 0),
    natural_gas_kwh       NUMERIC NOT NULL CHECK (natural_gas_kwh >= 0),
    renewable_kwh         NUMERIC NOT NULL CHECK (renewable_kwh >= 0),
    peak_demand_kw        NUMERIC NOT NULL CHECK (peak_demand_kw >= 0),
    occupancy_rate        NUMERIC NOT NULL CHECK (occupancy_rate BETWEEN 0 AND 1),
    operating_hours       NUMERIC NOT NULL CHECK (operating_hours BETWEEN 0 AND 24),
    is_statistical_outlier BOOLEAN NOT NULL DEFAULT FALSE,  -- flagged, never deleted (see data_quality.sql)
    UNIQUE (building_id, date)
);
CREATE INDEX idx_fact_energy_building_date ON curated.fact_energy (building_id, date);
CREATE INDEX idx_fact_energy_date ON curated.fact_energy (date);

CREATE TABLE curated.fact_weather (
    weather_id        SERIAL PRIMARY KEY,
    date               DATE NOT NULL REFERENCES curated.dim_date(date),
    city                VARCHAR(50) NOT NULL,
    temperature_f       NUMERIC NOT NULL,
    humidity_pct         NUMERIC NOT NULL CHECK (humidity_pct BETWEEN 0 AND 100),
    rainfall_in           NUMERIC NOT NULL CHECK (rainfall_in >= 0),
    wind_speed_mph         NUMERIC NOT NULL CHECK (wind_speed_mph >= 0),
    UNIQUE (city, date)
);
CREATE INDEX idx_fact_weather_city_date ON curated.fact_weather (city, date);

CREATE TABLE curated.fact_energy_cost (
    cost_id             SERIAL PRIMARY KEY,
    building_id          VARCHAR(10) NOT NULL REFERENCES curated.dim_building(building_id),
    month_start           DATE NOT NULL,   -- first of month; grain is building x month (see data/README.md)
    electricity_price      NUMERIC NOT NULL CHECK (electricity_price >= 0),
    gas_price               NUMERIC NOT NULL CHECK (gas_price >= 0),
    demand_charge             NUMERIC NOT NULL CHECK (demand_charge >= 0),
    UNIQUE (building_id, month_start)
);

CREATE TABLE curated.fact_maintenance (
    maintenance_id       SERIAL PRIMARY KEY,
    building_id            VARCHAR(10) NOT NULL REFERENCES curated.dim_building(building_id),
    maintenance_date         DATE NOT NULL,
    equipment_type             VARCHAR(30) NOT NULL,
    issue_type                   VARCHAR(20) NOT NULL CHECK (issue_type IN ('Preventive','Corrective','Emergency')),
    downtime_hours                 NUMERIC NOT NULL CHECK (downtime_hours >= 0),
    maintenance_cost                 NUMERIC NOT NULL CHECK (maintenance_cost >= 0)
);
CREATE INDEX idx_fact_maintenance_building ON curated.fact_maintenance (building_id, maintenance_date);

-- ----------------------------------------------------------------------------
-- AUDIT TABLE — records what the cleaning step in data_quality.sql actually
-- did (row counts per fix). Business value: an ESG/energy platform needs a
-- traceable answer to "was this number adjusted, and why" -- this table
-- IS that answer, not a comment buried in a script nobody re-reads.
-- ----------------------------------------------------------------------------
CREATE TABLE curated.data_quality_log (
    log_id          SERIAL PRIMARY KEY,
    run_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    table_name      TEXT NOT NULL,
    check_name      TEXT NOT NULL,
    rows_affected   INTEGER NOT NULL
);
