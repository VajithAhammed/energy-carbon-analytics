# Getting a real PostgreSQL instance running

The SQL in this project (`sql/schema.sql`, `sql/data_quality.sql`, and the
analytics queries in later stages) was written and logic-checked against
the actual data using pandas, but **has not been executed against a live
PostgreSQL server** — the environment used to build this project had no
internet access to install one. Running it yourself matters for two
reasons: you'll actually see it work, and you'll be able to speak to it
honestly in an interview.

Pick whichever of these you're comfortable with — all are free.

## Option A — Local install (full control, works offline afterward)
1. Install PostgreSQL: [postgresql.org/download](https://www.postgresql.org/download/)
2. Create the database: `createdb energy_carbon_analytics`
3. Connect: `psql energy_carbon_analytics`

## Option B — Docker (fastest if you already have Docker)
```bash
docker run --name energy-pg -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres:16
psql -h localhost -U postgres
```

## Option C — Free hosted Postgres (zero local install)
Providers like Neon, Supabase, and ElephantSQL all offer a free tier that
gives you a connection string in a couple of minutes, plus a web SQL editor
so you don't strictly need `psql` installed locally. Search "[provider name]
free postgres" for current sign-up steps — free-tier details change often
enough that I'd rather you check the current page than trust anything I
say here as fixed.

## Running this project's SQL
```bash
# from the project root, after connecting to your database:
\i sql/schema.sql
\copy staging.dim_building        FROM 'data/raw/dim_building.csv'        CSV HEADER;
\copy staging.fact_weather        FROM 'data/raw/fact_weather.csv'        CSV HEADER;
\copy staging.dim_emission_factor FROM 'data/raw/dim_emission_factor.csv' CSV HEADER;
\copy staging.fact_energy         FROM 'data/raw/fact_energy.csv'         CSV HEADER;
\copy staging.fact_energy_cost    FROM 'data/raw/fact_energy_cost.csv'    CSV HEADER;
\copy staging.fact_maintenance    FROM 'data/raw/fact_maintenance.csv'    CSV HEADER;
\i sql/data_quality.sql
```

## How to know it worked
Run this and compare against the notebook's printed numbers
(`notebooks/01_data_quality.ipynb`, Section 3 output):
```sql
SELECT COUNT(*) FROM curated.fact_energy;              -- expect 91,350
SELECT COUNT(*) FROM curated.fact_energy WHERE electricity_kwh < 0;  -- expect 0
SELECT COUNT(*) FROM curated.fact_energy WHERE occupancy_rate > 1;   -- expect 0
SELECT COUNT(*) FROM curated.fact_energy WHERE is_statistical_outlier;  -- expect 95
SELECT * FROM curated.data_quality_log ORDER BY log_id;
```
If any of these don't match, that's a real bug to chase down — not
something to paper over. Tell me what you get and we'll debug it together.
