"""
generate_dataset.py

Generates the SYNTHETIC / SIMULATED dataset for the Energy Consumption &
Carbon Analytics project: 6 related tables covering 50 commercial buildings
across 5 U.S. cities, daily, from 2020-01-01 to 2024-12-31.

This data does not represent any real company, building, or utility.
It is built to reproduce realistic *patterns* seen in real building energy
data (climate-driven load, occupancy-driven load, building-type baselines,
aging-related inefficiency) plus deliberately injected data-quality issues
and genuine anomalies, so later pipeline stages (data quality, EDA, SQL,
ML) have real problems to solve rather than clean toy data.

Design choices (see reports/data_generation_notes.md for the full writeup):
  - fact_energy is DAILY grain, not hourly. 50 buildings x 5 years of daily
    records is ~91K rows -- large enough to be meaningful, small enough to
    stay fast and avoid "millions of rows for the sake of it".
  - carbon_emissions is NOT precomputed here. It's derived downstream via a
    join against dim_emission_factor, so the emission calculation lives in
    one place (SQL/Python), not duplicated into the raw fact table.
  - fact_energy_cost is BUILDING-MONTH grain, not daily. Utility rates are
    set monthly/quarterly in reality, not daily -- daily cost rows would
    just be the same number repeated 30x for no analytical benefit.
  - Ground-truth anomaly flags are written to a SEPARATE validation-only
    file, never merged into fact_energy. If the anomaly flag lived in the
    delivered table, the later Isolation Forest model wouldn't be solving
    a real unsupervised problem -- it would be cheating off the answer key.
"""

import numpy as np
import pandas as pd
from pathlib import Path

RNG = np.random.default_rng(42)

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
OUT_DIR.mkdir(parents=True, exist_ok=True)

START_DATE = pd.Timestamp("2020-01-01")
END_DATE = pd.Timestamp("2024-12-31")
DATES = pd.date_range(START_DATE, END_DATE, freq="D")
N_DAYS = len(DATES)
DOY = DATES.dayofyear.values
IS_WEEKEND = (DATES.dayofweek >= 5).astype(int)

# ---------------------------------------------------------------------------
# 1. CITIES  (climate archetypes drive weather + heating/cooling demand)
# ---------------------------------------------------------------------------
CITIES = {
    "New York": dict(summer_hi=85, winter_lo=32, humidity=62, rain=0.11),
    "Chicago": dict(summer_hi=84, winter_lo=22, humidity=58, rain=0.10),
    "Phoenix": dict(summer_hi=104, winter_lo=52, humidity=22, rain=0.02),
    "Seattle": dict(summer_hi=76, winter_lo=40, humidity=72, rain=0.14),
    "Atlanta": dict(summer_hi=90, winter_lo=40, humidity=66, rain=0.12),
}

# ---------------------------------------------------------------------------
# 2. BUILDING TYPES  (baseline energy-use-intensity kWh/sqft/yr, gas share,
#    occupancy profile, operating hours). EUI values are in a realistic
#    ballpark for U.S. commercial buildings (CBECS-style magnitudes).
# ---------------------------------------------------------------------------
BUILDING_TYPES = {
    "Office":    dict(sqft=(40_000, 250_000), eui=16, gas_share=0.25, occ_wd=0.75, occ_we=0.06, hrs_wd=11, hrs_we=1,  always_on=False),
    "Retail":    dict(sqft=(15_000, 120_000), eui=14, gas_share=0.15, occ_wd=0.55, occ_we=0.70, hrs_wd=12, hrs_we=13, always_on=False),
    "Hospital":  dict(sqft=(80_000, 400_000), eui=27, gas_share=0.35, occ_wd=0.85, occ_we=0.82, hrs_wd=24, hrs_we=24, always_on=True),
    "School":    dict(sqft=(50_000, 200_000), eui=12, gas_share=0.30, occ_wd=0.80, occ_we=0.02, hrs_wd=9,  hrs_we=0,  always_on=False),
    "Warehouse": dict(sqft=(60_000, 300_000), eui=6,  gas_share=0.10, occ_wd=0.30, occ_we=0.12, hrs_wd=10, hrs_we=4,  always_on=False),
    "Mixed-Use": dict(sqft=(30_000, 180_000), eui=15, gas_share=0.20, occ_wd=0.60, occ_we=0.40, hrs_wd=13, hrs_we=8,  always_on=False),
}

N_BUILDINGS = 50
building_ids = [f"B{str(i).zfill(3)}" for i in range(1, N_BUILDINGS + 1)]
type_list = list(BUILDING_TYPES.keys())
city_list = list(CITIES.keys())

# ===========================================================================
# TABLE: dim_building
# ===========================================================================
dim_building_rows = []
for bid in building_ids:
    btype = RNG.choice(type_list, p=[0.30, 0.20, 0.10, 0.15, 0.15, 0.10])
    city = RNG.choice(city_list)
    spec = BUILDING_TYPES[btype]
    sqft = int(RNG.uniform(*spec["sqft"]))
    floors = max(1, int(sqft / RNG.uniform(12_000, 25_000)))
    year_built = int(RNG.integers(1975, 2021))
    occ_cap = int(sqft / RNG.uniform(180, 350))  # sqft per person varies by type
    has_solar = bool(RNG.random() < 0.30)  # 30% of portfolio has rooftop solar
    dim_building_rows.append(dict(
        building_id=bid, building_name=f"{city} {btype} {bid[-3:]}",
        building_type=btype, city=city, floor_area_sqft=sqft, floors=floors,
        year_built=year_built, occupancy_capacity=occ_cap, has_solar=has_solar,
    ))
dim_building = pd.DataFrame(dim_building_rows)

# ===========================================================================
# TABLE: fact_weather  (city x date)
# ===========================================================================
weather_frames = []
for city, spec in CITIES.items():
    mid = (spec["summer_hi"] + spec["winter_lo"]) / 2
    amp = (spec["summer_hi"] - spec["winter_lo"]) / 2
    # seasonal sinusoid peaking mid-summer (~day 200), plus day-to-day noise
    seasonal = mid + amp * np.sin(2 * np.pi * (DOY - 110) / 365.25)
    temp = seasonal + RNG.normal(0, 4.5, N_DAYS)
    humidity = np.clip(spec["humidity"] + RNG.normal(0, 8, N_DAYS), 10, 100)
    rain_prob = spec["rain"]
    rainfall = np.where(RNG.random(N_DAYS) < rain_prob, RNG.gamma(2, 0.3, N_DAYS), 0.0)
    wind = np.clip(RNG.normal(8, 3, N_DAYS), 0, None)
    weather_frames.append(pd.DataFrame(dict(
        date=DATES, city=city, temperature_f=temp.round(1),
        humidity_pct=humidity.round(1), rainfall_in=rainfall.round(2),
        wind_speed_mph=wind.round(1),
    )))
fact_weather = pd.concat(weather_frames, ignore_index=True)
weather_lookup = fact_weather.set_index(["city", "date"])["temperature_f"]

# ===========================================================================
# TABLE: dim_emission_factor  (grid electricity factor declines slightly
# year over year, reflecting real-world grid decarbonization trends)
# ===========================================================================
emission_rows = []
for year in range(2020, 2025):
    grid_factor = 0.42 - (year - 2020) * 0.012  # kg CO2e / kWh, gradually improving
    emission_rows.append(dict(energy_source="Grid Electricity", emission_factor=round(grid_factor, 4), effective_date=f"{year}-01-01"))
    emission_rows.append(dict(energy_source="Natural Gas", emission_factor=0.181, effective_date=f"{year}-01-01"))
    emission_rows.append(dict(energy_source="Renewable", emission_factor=0.0, effective_date=f"{year}-01-01"))
dim_emission_factor = pd.DataFrame(emission_rows)

# ===========================================================================
# TABLE: fact_energy  (the core table: building x date)
# ===========================================================================
energy_frames = []
maintenance_events = []  # collected here, saved separately below
ground_truth_anomalies = []  # validation-only, NOT shipped in fact_energy

for _, b in dim_building.iterrows():
    spec = BUILDING_TYPES[b.building_type]
    temps = weather_lookup.loc[b.city].reindex(DATES).values

    # Heating/cooling degree-day style demand: energy rises as temp departs
    # from a 65F comfort band -- the standard HVAC-load proxy used in
    # real energy analytics (this is *why* HDD/CDD exist as a concept).
    hdd = np.clip(65 - temps, 0, None)
    cdd = np.clip(temps - 65, 0, None)
    # Coefficients calibrated so weather-driven HVAC load is ~30-40% of
    # total annual EUI on average across the 5 cities (realistic HVAC
    # share for commercial buildings) rather than dwarfing the baseline --
    # an earlier version of this script used coefficients 5-10x too large,
    # which pushed simulated annual EUI 2-3x above real CBECS-ish
    # benchmarks for most building types. Verified against actual annual
    # HDD/CDD sums per city before picking these values.
    weather_load = 0.00065 * hdd + 0.00105 * cdd  # cooling costs more than heating, per kWh/sqft/day

    # Baseline daily EUI (kWh/sqft/day): ~65% of annual target EUI comes
    # from non-weather baseload (lighting, plug loads, hot water), the
    # remaining ~35% from weather-driven HVAC added below. This also means
    # a building's REALIZED annual EUI now varies by climate (Phoenix
    # buildings run hotter EUI than Seattle buildings of the same type),
    # which is itself a realistic pattern, not just noise.
    BASE_LOAD_FRACTION = 0.65
    base_daily = spec["eui"] * BASE_LOAD_FRACTION / 365.0
    daily_eui = base_daily + weather_load

    # Occupancy-driven multiplier: weekday vs weekend, school-year effect
    occ_rate = np.where(IS_WEEKEND, spec["occ_we"], spec["occ_wd"]).astype(float)
    if b.building_type == "School":
        # summer break (Jun-Aug): occupancy collapses even on weekdays
        month = DATES.month.values
        occ_rate = np.where(np.isin(month, [6, 7, 8]), occ_rate * 0.08, occ_rate)
    occ_rate = np.clip(occ_rate + RNG.normal(0, 0.05, N_DAYS), 0.0, 1.0)

    # Building-age efficiency drag: older buildings run ~0.1%/yr less
    # efficient without retrofits; ~40% of buildings got an efficiency
    # retrofit partway through the window (LED/BMS upgrades) -- a
    # realistic "why is consumption changing" story for the EDA stage.
    age_penalty = 1 + 0.0015 * (2024 - b.year_built)
    retrofitted = RNG.random() < 0.4
    trend = np.ones(N_DAYS)
    if retrofitted:
        retrofit_day = RNG.integers(300, N_DAYS - 300)
        trend[retrofit_day:] *= RNG.uniform(0.85, 0.93)  # ~7-15% step-down after retrofit

    occupancy_multiplier = 0.55 + 0.45 * occ_rate  # buildings never go fully to zero
    noise = RNG.normal(1.0, 0.06, N_DAYS)

    total_kwh_equiv = daily_eui * b.floor_area_sqft * age_penalty * trend * occupancy_multiplier * noise
    total_kwh_equiv = np.clip(total_kwh_equiv, 5, None)

    gas_kwh = total_kwh_equiv * spec["gas_share"] * (0.4 + 0.9 * (hdd / (hdd.max() + 1)))
    electricity_kwh = total_kwh_equiv - gas_kwh

    renewable_kwh = np.zeros(N_DAYS)
    if b.has_solar:
        solar_seasonal = 0.5 + 0.5 * np.sin(2 * np.pi * (DOY - 80) / 365.25)  # peaks ~summer
        renewable_kwh = np.clip(electricity_kwh * 0.18 * solar_seasonal + RNG.normal(0, electricity_kwh.mean() * 0.01, N_DAYS), 0, electricity_kwh * 0.5)

    hrs = np.where(IS_WEEKEND, spec["hrs_we"], spec["hrs_wd"]).astype(float)
    peak_demand_kw = (electricity_kwh / np.clip(hrs, 3, None)) * RNG.uniform(1.15, 1.4, N_DAYS)

    # --- genuine business anomalies: real equipment-failure-style spikes,
    # distinct from data errors injected later. ~2-4 per building over 5yrs.
    n_anom = RNG.integers(2, 5)
    anom_days = RNG.choice(N_DAYS, size=n_anom, replace=False)
    for d in anom_days:
        severity = RNG.uniform(1.6, 2.8)
        electricity_kwh[d] *= severity
        peak_demand_kw[d] *= RNG.uniform(1.3, 1.8)
        ground_truth_anomalies.append(dict(
            building_id=b.building_id, date=DATES[d], severity_multiplier=round(severity, 2),
            likely_cause=RNG.choice(["HVAC fault suspected", "Equipment left running", "Unplanned high load event"]),
        ))
        # Most (not all) injected anomalies get a linked maintenance ticket
        # a few days later -- realistic response lag, not instant detection.
        if RNG.random() < 0.7:
            maintenance_events.append(dict(
                building_id=b.building_id,
                maintenance_date=DATES[min(d + int(RNG.integers(1, 6)), N_DAYS - 1)],
                equipment_type=RNG.choice(["HVAC", "Electrical", "Boiler", "Lighting"]),
                issue_type="Emergency",
                downtime_hours=round(RNG.uniform(2, 18), 1),
                maintenance_cost=round(RNG.uniform(800, 9000), 2),
            ))

    energy_frames.append(pd.DataFrame(dict(
        building_id=b.building_id, date=DATES,
        electricity_kwh=electricity_kwh.round(2), natural_gas_kwh=gas_kwh.round(2),
        renewable_kwh=renewable_kwh.round(2), peak_demand_kw=peak_demand_kw.round(2),
        occupancy_rate=occ_rate.round(3), operating_hours=hrs,
    )))

# routine (non-emergency) maintenance, independent of anomalies
for bid in building_ids:
    n_routine = RNG.integers(8, 16)
    routine_days = RNG.choice(N_DAYS, size=n_routine, replace=False)
    for d in routine_days:
        maintenance_events.append(dict(
            building_id=bid, maintenance_date=DATES[d],
            equipment_type=RNG.choice(["HVAC", "Electrical", "Boiler", "Lighting", "Elevator"]),
            issue_type=RNG.choice(["Preventive", "Corrective"], p=[0.65, 0.35]),
            downtime_hours=round(RNG.uniform(0.5, 6), 1),
            maintenance_cost=round(RNG.uniform(150, 3000), 2),
        ))

fact_energy = pd.concat(energy_frames, ignore_index=True)
fact_energy.insert(0, "record_id", range(1, len(fact_energy) + 1))

fact_maintenance = pd.DataFrame(maintenance_events)
fact_maintenance.insert(0, "maintenance_id", range(1, len(fact_maintenance) + 1))

ground_truth_anomalies = pd.DataFrame(ground_truth_anomalies)

# ===========================================================================
# TABLE: fact_energy_cost  (building x month -- utility rates are set
# monthly/quarterly in reality, not daily)
# ===========================================================================
months = pd.date_range(START_DATE, END_DATE, freq="MS")
CITY_BASE_RATE = {"New York": 0.21, "Chicago": 0.15, "Phoenix": 0.13, "Seattle": 0.11, "Atlanta": 0.13}
cost_rows = []
for _, b in dim_building.iterrows():
    base_rate = CITY_BASE_RATE[b.city]
    for i, m in enumerate(months):
        inflation = 1 + 0.025 * (i / 12)  # mild annual price inflation
        elec_price = round(base_rate * inflation * RNG.uniform(0.97, 1.03), 4)
        gas_price = round(0.045 * inflation * RNG.uniform(0.95, 1.05), 4)
        demand_charge = round(RNG.uniform(9, 18), 2)
        cost_rows.append(dict(date=m, building_id=b.building_id, electricity_price=elec_price, gas_price=gas_price, demand_charge=demand_charge))
fact_energy_cost = pd.DataFrame(cost_rows)

print("Base tables generated:")
for name, df in [("dim_building", dim_building), ("fact_weather", fact_weather),
                  ("dim_emission_factor", dim_emission_factor), ("fact_energy", fact_energy),
                  ("fact_energy_cost", fact_energy_cost), ("fact_maintenance", fact_maintenance)]:
    print(f"  {name:22s} {df.shape[0]:>8,} rows x {df.shape[1]} cols")

# ===========================================================================
# INJECT DATA-QUALITY ISSUES (deliberate, for the Stage 2 data-quality
# workflow -- these are DATA ERRORS, kept distinct from the genuine
# business anomalies injected above).
# ===========================================================================
fe = fact_energy.copy()
fw = fact_weather.copy()
n = len(fe)

# missing values (~1.2% of key numeric fields)
for col in ["electricity_kwh", "occupancy_rate", "natural_gas_kwh"]:
    idx = RNG.choice(n, size=int(n * 0.012), replace=False)
    fe.loc[idx, col] = np.nan

# duplicate records (exact row duplicates, ~0.05%)
dup_idx = RNG.choice(n, size=int(n * 0.0005), replace=False)
fe = pd.concat([fe, fe.loc[dup_idx]], ignore_index=True)

# data-entry errors: negative electricity (impossible) and impossible occupancy (>1)
neg_idx = RNG.choice(len(fe), size=25, replace=False)
fe.loc[neg_idx, "electricity_kwh"] = -np.abs(fe.loc[neg_idx, "electricity_kwh"])
occ_err_idx = RNG.choice(len(fe), size=20, replace=False)
fe.loc[occ_err_idx, "occupancy_rate"] = fe.loc[occ_err_idx, "occupancy_rate"].fillna(0.5) + RNG.uniform(1.1, 1.5, 20)

# missing weather (~0.8%)
w_idx = RNG.choice(len(fw), size=int(len(fw) * 0.008), replace=False)
fw.loc[w_idx, "temperature_f"] = np.nan

fe = fe.sample(frac=1, random_state=1).reset_index(drop=True)  # shuffle so errors aren't clustered at the end

# ===========================================================================
# SAVE
# ===========================================================================
dim_building.to_csv(OUT_DIR / "dim_building.csv", index=False)
fw.to_csv(OUT_DIR / "fact_weather.csv", index=False)
dim_emission_factor.to_csv(OUT_DIR / "dim_emission_factor.csv", index=False)
fe.to_csv(OUT_DIR / "fact_energy.csv", index=False)
fact_energy_cost.to_csv(OUT_DIR / "fact_energy_cost.csv", index=False)
fact_maintenance.to_csv(OUT_DIR / "fact_maintenance.csv", index=False)
ground_truth_anomalies.to_csv(OUT_DIR.parent / "processed" / "_validation_only_injected_anomalies.csv", index=False)

print("\nInjected (for Stage 2 to find):")
print(f"  Missing values (fact_energy)   : {fe[['electricity_kwh','occupancy_rate','natural_gas_kwh']].isna().sum().sum():,}")
print(f"  Duplicate rows (fact_energy)   : {fe.duplicated(subset=['building_id','date']).sum():,}")
print(f"  Negative electricity_kwh rows  : {(fe['electricity_kwh'] < 0).sum():,}")
print(f"  Impossible occupancy (>1) rows : {(fe['occupancy_rate'] > 1).sum():,}")
print(f"  Missing weather temps          : {fw['temperature_f'].isna().sum():,}")
print(f"  Genuine anomalies (ground truth, held out): {len(ground_truth_anomalies):,}")
print("\nFiles written to data/raw/")
