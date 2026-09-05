"""
data_cleaning.py

Reusable data-quality functions for the Energy Consumption & Carbon
Analytics project. The notebook (notebooks/01_data_quality.ipynb) imports
these rather than redefining cleaning logic inline -- keeps the rules in
one place, testable, and not duplicated if another notebook needs them.

CORE PRINCIPLE (per project brief): data errors get corrected, genuine
anomalies get flagged, never deleted. A negative kWh reading is physically
impossible -- that's an error. A building suddenly using 2.5x its normal
load is unusual but *possible* -- that's a business anomaly worth
investigating, not a row to quietly fix.
"""

import numpy as np
import pandas as pd
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

VALID_DATE_RANGE = (pd.Timestamp("2020-01-01"), pd.Timestamp("2024-12-31"))


def load_raw_tables() -> dict:
    tables = {
        "dim_building": pd.read_csv(RAW_DIR / "dim_building.csv"),
        "fact_weather": pd.read_csv(RAW_DIR / "fact_weather.csv", parse_dates=["date"]),
        "dim_emission_factor": pd.read_csv(RAW_DIR / "dim_emission_factor.csv", parse_dates=["effective_date"]),
        "fact_energy": pd.read_csv(RAW_DIR / "fact_energy.csv", parse_dates=["date"]),
        "fact_energy_cost": pd.read_csv(RAW_DIR / "fact_energy_cost.csv", parse_dates=["date"]),
        "fact_maintenance": pd.read_csv(RAW_DIR / "fact_maintenance.csv", parse_dates=["maintenance_date"]),
    }
    return tables


def profile_data_quality(tables: dict) -> pd.DataFrame:
    """One row per check. This is a read-only PROFILE -- nothing is fixed
    here. Business value: this table is what you'd hand to a data owner
    to say 'here's exactly what's wrong, here's how much of it there is'."""
    fe, fw, db = tables["fact_energy"], tables["fact_weather"], tables["dim_building"]
    out_of_range = (fe["date"] < VALID_DATE_RANGE[0]) | (fe["date"] > VALID_DATE_RANGE[1])

    checks = [
        ("fact_energy", "missing electricity_kwh", int(fe.electricity_kwh.isna().sum())),
        ("fact_energy", "missing natural_gas_kwh", int(fe.natural_gas_kwh.isna().sum())),
        ("fact_energy", "missing occupancy_rate", int(fe.occupancy_rate.isna().sum())),
        ("fact_energy", "exact duplicate (building_id + date)", int(fe.duplicated(subset=["building_id", "date"]).sum())),
        ("fact_energy", "negative electricity_kwh (impossible)", int((fe.electricity_kwh < 0).sum())),
        ("fact_energy", "occupancy_rate > 1 (impossible)", int((fe.occupancy_rate > 1).sum())),
        ("fact_energy", "date outside 2020-01-01..2024-12-31", int(out_of_range.sum())),
        ("fact_energy", "orphan building_id (referential integrity)", int((~fe.building_id.isin(db.building_id)).sum())),
        ("fact_weather", "missing temperature_f", int(fw.temperature_f.isna().sum())),
        ("dim_building", "distinct building_type values (category consistency check)", int(db.building_type.nunique())),
        ("dim_building", "distinct city values (category consistency check)", int(db.city.nunique())),
    ]
    return pd.DataFrame(checks, columns=["table", "check", "count"])


def check_referential_integrity(tables: dict) -> pd.DataFrame:
    fe, fw, fc, fm, db = (tables["fact_energy"], tables["fact_weather"],
                           tables["fact_energy_cost"], tables["fact_maintenance"], tables["dim_building"])
    results = [
        ("fact_energy.building_id -> dim_building", int((~fe.building_id.isin(db.building_id)).sum())),
        ("fact_weather.city -> dim_building.city", int((~fw.city.isin(db.city)).sum())),
        ("fact_energy_cost.building_id -> dim_building", int((~fc.building_id.isin(db.building_id)).sum())),
        ("fact_maintenance.building_id -> dim_building", int((~fm.building_id.isin(db.building_id)).sum())),
    ]
    return pd.DataFrame(results, columns=["relationship", "orphan_rows"])


def clean_fact_energy(fe: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns (cleaned_df, change_log_df).

    Rules (each is a DATA ERROR fix -- statistical outliers are handled
    separately in flag_statistical_outliers and are never touched here):
      1. Exact duplicate (building_id, date) -> keep first occurrence.
      2. Negative electricity_kwh -> physically impossible -> null it out,
         then impute using THAT BUILDING's own median for the same
         weekday (a global mean would ignore that a hospital and a
         warehouse have completely different baselines).
      3. occupancy_rate > 1 -> a rate can't exceed 100% -> capped at 1.0
         (a business-rule correction, not a deletion).
      4. Missing electricity_kwh / natural_gas_kwh / occupancy_rate ->
         same building+weekday median imputation as rule 2.
    """
    log_rows = []
    df = fe.copy()

    before = len(df)
    df = df.sort_values("record_id").drop_duplicates(subset=["building_id", "date"], keep="first")
    log_rows.append(dict(step="drop_exact_duplicate_building_date", rows_affected=before - len(df)))

    neg_mask = df["electricity_kwh"] < 0
    log_rows.append(dict(step="null_negative_electricity_kwh", rows_affected=int(neg_mask.sum())))
    df.loc[neg_mask, "electricity_kwh"] = np.nan

    occ_mask = df["occupancy_rate"] > 1
    log_rows.append(dict(step="cap_occupancy_rate_at_1", rows_affected=int(occ_mask.sum())))
    df.loc[occ_mask, "occupancy_rate"] = 1.0

    df["weekday"] = df["date"].dt.dayofweek
    for col in ["electricity_kwh", "natural_gas_kwh", "occupancy_rate"]:
        n_missing = int(df[col].isna().sum())
        df[col] = df.groupby(["building_id", "weekday"])[col].transform(lambda s: s.fillna(s.median()))
        df[col] = df.groupby("building_id")[col].transform(lambda s: s.fillna(s.median()))  # fallback if a group is all-null
        log_rows.append(dict(step=f"impute_{col}_building_weekday_median", rows_affected=n_missing))
    df = df.drop(columns=["weekday"])

    return df, pd.DataFrame(log_rows)


def flag_statistical_outliers(fe: pd.DataFrame, z_thresh: float = 3.5) -> pd.DataFrame:
    """
    Adds `is_statistical_outlier` (bool) using a per-building MODIFIED
    z-score (median/MAD-based). A plain mean/std z-score gets dragged
    around by the very outliers you're trying to find; median/MAD doesn't.

    This is a coarse first pass, NOT the anomaly-detection model. Isolation
    Forest (later ML stage) does the real multivariate detection using
    weather/occupancy context together. This flag exists so the
    data-quality stage documents unusual points without silently smoothing
    them into the "clean" data.
    """
    df = fe.copy()

    def mod_z(s):
        med = s.median()
        mad = (s - med).abs().median()
        if mad == 0:
            return pd.Series(0.0, index=s.index)
        return 0.6745 * (s - med) / mad

    z = df.groupby("building_id")["electricity_kwh"].transform(mod_z)
    df["is_statistical_outlier"] = z.abs() > z_thresh
    return df


def clean_fact_weather(fw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Missing temperature -> imputed with that CITY's climatological
    average for the same day-of-year. Weather is smooth and seasonal, so
    this beats a global mean or a same-row fill by a wide margin."""
    df = fw.copy()
    df["doy"] = df["date"].dt.dayofyear
    n_missing = int(df["temperature_f"].isna().sum())
    df["temperature_f"] = df.groupby(["city", "doy"])["temperature_f"].transform(lambda s: s.fillna(s.mean()))
    df["temperature_f"] = df.groupby("city")["temperature_f"].transform(lambda s: s.fillna(s.mean()))
    df = df.drop(columns=["doy"])
    log = pd.DataFrame([dict(step="impute_temperature_city_dayofyear_climatology", rows_affected=n_missing)])
    return df, log


def save_processed(tables: dict) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(PROCESSED_DIR / f"{name}.csv", index=False)
