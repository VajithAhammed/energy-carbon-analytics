"""
feature_engineering.py

Builds the analysis-ready daily table used by EDA, SQL cross-checks, and
(later) ML feature sets. Kept in src/, not copy-pasted into notebooks, so
the carbon/cost calculation logic exists in exactly one place.

CARBON CALCULATION CONVENTION (see data/README.md):
  renewable_kwh is a SUBSET of electricity_kwh (on-site solar contributing
  to total use), not additional to it. So:
    grid_electricity_kwh = electricity_kwh - renewable_kwh
    carbon_emissions_kgCO2e = grid_electricity_kwh * grid_factor(year)
                             + natural_gas_kwh * gas_factor(year)
  (renewable's own emission factor is 0, so it drops out of the formula
  entirely -- it's still worth writing explicitly rather than silently
  omitting it, so the logic reads as a deliberate choice, not an oversight.)

EMISSION FACTOR CONVENTION:
  dim_emission_factor has one row per source per YEAR (effective_date =
  Jan 1). We join on calendar year, which is the correct grain here since
  that's how the factors were defined -- not a rolling "most recent
  effective_date <= date" lookup, which would be over-engineering for a
  table that only ever changes on Jan 1.

COST CALCULATION CONVENTION (see fact_energy_cost grain in data/README.md):
  electricity_price / gas_price are $/kWh and apply per-day multiplied by
  that day's usage. demand_charge is a MONTHLY charge based on that
  month's peak demand -- it is NOT a daily-additive cost, so it is
  reported separately at building-month grain, never divided across days.
"""

import numpy as np
import pandas as pd
from pathlib import Path

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"


def load_processed_tables() -> dict:
    return {
        "dim_building": pd.read_csv(PROCESSED_DIR / "dim_building.csv"),
        "fact_weather": pd.read_csv(PROCESSED_DIR / "fact_weather.csv", parse_dates=["date"]),
        "dim_emission_factor": pd.read_csv(PROCESSED_DIR / "dim_emission_factor.csv", parse_dates=["effective_date"]),
        "fact_energy": pd.read_csv(PROCESSED_DIR / "fact_energy.csv", parse_dates=["date"]),
        "fact_energy_cost": pd.read_csv(PROCESSED_DIR / "fact_energy_cost.csv", parse_dates=["date"]),
        "fact_maintenance": pd.read_csv(PROCESSED_DIR / "fact_maintenance.csv", parse_dates=["maintenance_date"]),
    }


def build_daily_analysis_table(tables: dict) -> pd.DataFrame:
    """One row per building-day. Adds: city/building_type/floor_area (from
    dim_building), temperature_f (from fact_weather), carbon_emissions_kgCO2e
    (derived), daily_energy_cost (derived, excludes demand charge -- see
    module docstring)."""
    fe = tables["fact_energy"].copy()
    db = tables["dim_building"]
    fw = tables["fact_weather"]
    ef = tables["dim_emission_factor"].copy()
    fc = tables["fact_energy_cost"].copy()

    fe["year"] = fe["date"].dt.year
    ef["year"] = ef["effective_date"].dt.year
    grid_ef = ef[ef.energy_source == "Grid Electricity"][["year", "emission_factor"]].rename(columns={"emission_factor": "grid_factor"})
    gas_ef = ef[ef.energy_source == "Natural Gas"][["year", "emission_factor"]].rename(columns={"emission_factor": "gas_factor"})

    df = fe.merge(db, on="building_id", how="left")
    df = df.merge(fw[["date", "city", "temperature_f", "humidity_pct"]], on=["date", "city"], how="left")
    df = df.merge(grid_ef, on="year", how="left")
    df = df.merge(gas_ef, on="year", how="left")

    df["grid_electricity_kwh"] = df["electricity_kwh"] - df["renewable_kwh"]
    df["carbon_emissions_kgCO2e"] = (
        df["grid_electricity_kwh"] * df["grid_factor"] + df["natural_gas_kwh"] * df["gas_factor"]
    )

    fc["month_start"] = fc["date"].values.astype("datetime64[M]")
    df["month_start"] = df["date"].values.astype("datetime64[M]")
    df = df.merge(
        fc[["building_id", "month_start", "electricity_price", "gas_price"]],
        on=["building_id", "month_start"], how="left",
    )
    df["daily_energy_cost"] = df["electricity_kwh"] * df["electricity_price"] + df["natural_gas_kwh"] * df["gas_price"]

    df["total_kwh"] = df["electricity_kwh"] + df["natural_gas_kwh"]
    df["energy_use_intensity"] = df["total_kwh"] / df["floor_area_sqft"]  # kWh/sqft/day

    return df.drop(columns=["year", "grid_factor", "gas_factor", "month_start"])


def build_monthly_cost_table(tables: dict, daily_df: pd.DataFrame) -> pd.DataFrame:
    """Building-month grain, INCLUDING the demand charge -- the correct
    grain for a demand charge, which bills once per month against that
    month's peak, not once per day."""
    fc = tables["fact_energy_cost"].copy()
    fc["month_start"] = fc["date"].values.astype("datetime64[M]")
    daily_df = daily_df.copy()
    daily_df["month_start"] = daily_df["date"].values.astype("datetime64[M]")

    monthly = daily_df.groupby(["building_id", "month_start"]).agg(
        energy_cost=("daily_energy_cost", "sum"),
        peak_demand_kw=("peak_demand_kw", "max"),
    ).reset_index()
    monthly = monthly.merge(fc[["building_id", "month_start", "demand_charge"]], on=["building_id", "month_start"], how="left")
    monthly["demand_cost"] = monthly["peak_demand_kw"] * monthly["demand_charge"]
    monthly["total_cost"] = monthly["energy_cost"] + monthly["demand_cost"]
    return monthly


# ============================================================================
# ML FEATURE ENGINEERING (Stage 4 / notebooks/03_feature_engineering.ipynb)
# ============================================================================
# Grain note: this project uses DAILY data (see data/README.md), so an
# "hour of day" feature (mentioned as a possible feature in the project
# brief) doesn't apply here -- there's no intraday granularity to encode.
# Every other listed feature category (weather, occupancy, building
# attributes, calendar, lag, rolling) is covered below.

LAG_DAYS = (1, 7, 30)
ROLLING_WINDOWS = (7, 30)


def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    """weekday / month / is_weekend, plus a cyclical (sin/cos) encoding of
    month -- a plain integer 1-12 tells a linear model that December (12)
    and January (1) are 11 apart, when they're actually adjacent. Cyclical
    encoding fixes that; tree models don't strictly need it but it doesn't
    hurt them either, so one encoding serves all three candidate models."""
    df = df.copy()
    df["weekday"] = df["date"].dt.dayofweek
    df["month"] = df["date"].dt.month
    df["is_weekend"] = (df["weekday"] >= 5).astype(int)
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
    return df


def add_lag_and_rolling_features(
    df: pd.DataFrame, target_col: str = "electricity_kwh",
    lags=LAG_DAYS, rolling_windows=ROLLING_WINDOWS,
) -> pd.DataFrame:
    """
    Adds `{target}_lag_{n}` and `{target}_rolling_mean_{n}`, computed
    PER BUILDING (never mixing one building's history into another's) and
    using ONLY past values.

    LEAKAGE GUARD: the rolling mean is computed on a series already
    shifted by 1 day before the window is applied. Without that shift,
    day D's rolling window would include day D's own target value --
    which is exactly the number the model is trying to predict. That's
    the single most common time-series leakage bug, so it's called out
    here explicitly rather than left implicit in the code. There's a
    dedicated check for this in the notebook, not just this comment.
    """
    df = df.sort_values(["building_id", "date"]).copy()

    for lag in lags:
        df[f"{target_col}_lag_{lag}"] = df.groupby("building_id")[target_col].shift(lag)

    for window in rolling_windows:
        df[f"{target_col}_rolling_mean_{window}"] = df.groupby("building_id")[target_col].transform(
            lambda s: s.shift(1).rolling(window).mean()
        )

    return df


def time_aware_split(df: pd.DataFrame, test_start: str = "2024-01-01") -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Chronological split: train = strictly before test_start, test = on/after.
    NOT a random split -- sklearn's train_test_split(shuffle=True) would
    let the model train on rows that come chronologically AFTER some of
    its test rows, which a forecasting model would never have access to
    in production (you don't get to see next month's actuals before
    predicting this month).
    """
    train = df[df["date"] < test_start].copy()
    test = df[df["date"] >= test_start].copy()
    return train, test


def build_ml_feature_table(daily_df: pd.DataFrame, target_col: str = "electricity_kwh") -> pd.DataFrame:
    """
    Full ML-ready table: calendar + lag + rolling features added to the
    existing daily analysis table, one-hot encoded building_type/city,
    with the leading rows per building (where lag/rolling windows aren't
    fully populated yet) dropped rather than imputed -- imputing a lag
    feature would mean inventing a plausible-looking history that never
    happened, which is worse than just having fewer usable rows.
    """
    df = add_calendar_features(daily_df)
    df = add_lag_and_rolling_features(df, target_col=target_col)

    max_window = max(max(LAG_DAYS), max(ROLLING_WINDOWS))
    before = len(df)
    # NOTE: originally implemented as groupby("building_id").apply(lambda g:
    # g.iloc[max_window:]) -- pandas 3.0 changed apply()'s default to
    # exclude the grouping column from what's passed to the function,
    # which silently dropped building_id from the output. cumcount() is
    # both immune to that and a vectorized (faster) way to do the same
    # per-group row-truncation.
    row_num_within_building = df.groupby("building_id").cumcount()
    df = df[row_num_within_building >= max_window]
    dropped = before - len(df)

    df = pd.get_dummies(df, columns=["building_type", "city"], prefix=["type", "city"])

    return df, dropped

