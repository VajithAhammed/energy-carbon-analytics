"""
generate_forecast.py

Produces a REAL 90-day forward forecast (2025-01-01 to 2025-03-31) using
the already-trained, already-evaluated Random Forest model from
04_energy_forecasting.ipynb -- not fabricated numbers for a dashboard.

Recursive multi-step forecasting: day 2's lag_1 feature is day 1's
PREDICTION (the actual value doesn't exist yet), and so on forward.
This is standard practice for forecasting beyond the last known day, and
is the reason this is a separate script rather than a single batch
.predict() call -- lag features for day N+2 literally don't exist until
day N+1 has been predicted.

INPUTS ASSUMED, DOCUMENTED, NOT HIDDEN:
  - Weather: each city's historical (2020-2024) climatological average
    for that day-of-year. This is a stand-in for a real weather forecast
    and will not reflect actual future conditions -- see the "why this
    matters" note in powerbi/README.md.
  - Occupancy / operating hours: each building's historical average for
    that (weekday, month) combination.
"""

import sys
sys.path.insert(0, "src")
import json
import joblib
import numpy as np
import pandas as pd
from feature_engineering import load_processed_tables, build_daily_analysis_table, add_calendar_features

MODEL_DIR = "models"
OUT_PATH = "data/processed/energy_forecast_2025Q1.csv"

FORECAST_START = pd.Timestamp("2025-01-01")
FORECAST_END = pd.Timestamp("2025-03-31")
FORECAST_DATES = pd.date_range(FORECAST_START, FORECAST_END, freq="D")

model = joblib.load(f"{MODEL_DIR}/energy_demand_model.joblib")
with open(f"{MODEL_DIR}/energy_demand_model_features.json") as f:
    FEATURE_COLS = json.load(f)

tables = load_processed_tables()
daily = build_daily_analysis_table(tables)
daily = add_calendar_features(daily)
db = tables["dim_building"].set_index("building_id")
fw = tables["fact_weather"].copy()
fw["doy"] = fw["date"].dt.dayofyear

# Climatological weather: city x day-of-year average across all 5 historical years
weather_clim = fw.groupby(["city", "doy"])[["temperature_f", "humidity_pct"]].mean()

# Occupancy / operating hours: building x (weekday, month) historical average
occ_clim = daily.groupby(["building_id", "weekday", "month"])[["occupancy_rate", "operating_hours"]].mean()

all_forecasts = []

for building_id in db.index:
    b = db.loc[building_id]
    city = b["city"]
    btype = b["building_type"]

    # Seed history with this building's actual last 35 days (need 30 for
    # the longest rolling window, +5 buffer) so day-1 lag/rolling features
    # are real, not assumed.
    hist = daily[daily.building_id == building_id].sort_values("date").tail(35)
    history_series = hist.set_index("date")["electricity_kwh"].copy()

    for target_date in FORECAST_DATES:
        doy = target_date.dayofyear
        weekday = target_date.dayofweek
        month = target_date.month
        is_weekend = int(weekday >= 5)
        month_sin = np.sin(2 * np.pi * month / 12)
        month_cos = np.cos(2 * np.pi * month / 12)

        temp = weather_clim.loc[(city, doy), "temperature_f"] if (city, doy) in weather_clim.index else weather_clim.loc[city, "temperature_f"].mean()
        humidity = weather_clim.loc[(city, doy), "humidity_pct"] if (city, doy) in weather_clim.index else weather_clim.loc[city, "humidity_pct"].mean()

        occ_key = (building_id, weekday, month)
        if occ_key in occ_clim.index:
            occ_rate = occ_clim.loc[occ_key, "occupancy_rate"]
            op_hours = occ_clim.loc[occ_key, "operating_hours"]
        else:
            occ_rate = daily[daily.building_id == building_id].occupancy_rate.mean()
            op_hours = daily[daily.building_id == building_id].operating_hours.mean()

        lag_1 = history_series.iloc[-1]
        lag_7 = history_series.iloc[-7] if len(history_series) >= 7 else history_series.mean()
        lag_30 = history_series.iloc[-30] if len(history_series) >= 30 else history_series.mean()
        rolling_7 = history_series.iloc[-7:].mean()
        rolling_30 = history_series.iloc[-30:].mean()

        row = {
            "occupancy_rate": occ_rate, "operating_hours": op_hours,
            "floor_area_sqft": b["floor_area_sqft"], "floors": b["floors"],
            "year_built": b["year_built"], "occupancy_capacity": b["occupancy_capacity"],
            "has_solar": b["has_solar"],
            "temperature_f": temp, "humidity_pct": humidity,
            "weekday": weekday, "month": month, "is_weekend": is_weekend,
            "month_sin": month_sin, "month_cos": month_cos,
            "electricity_kwh_lag_1": lag_1, "electricity_kwh_lag_7": lag_7, "electricity_kwh_lag_30": lag_30,
            "electricity_kwh_rolling_mean_7": rolling_7, "electricity_kwh_rolling_mean_30": rolling_30,
        }
        for t in ["Hospital", "Mixed-Use", "Office", "Retail", "School", "Warehouse"]:
            row[f"type_{t}"] = (btype == t)
        for c in ["Atlanta", "Chicago", "New York", "Phoenix", "Seattle"]:
            row[f"city_{c}"] = (city == c)

        X_row = pd.DataFrame([row])[FEATURE_COLS]
        pred = max(0, model.predict(X_row)[0])  # energy can't be negative

        history_series.loc[target_date] = pred
        all_forecasts.append(dict(building_id=building_id, date=target_date, predicted_electricity_kwh=pred))

forecast_df = pd.DataFrame(all_forecasts)
forecast_df.to_csv(OUT_PATH, index=False)
print(f"Forecast generated: {forecast_df.shape[0]:,} rows ({len(db)} buildings x {len(FORECAST_DATES)} days)")
print(f"Saved to {OUT_PATH}")
print("\nPortfolio-wide daily forecast total, first/last week:")
portfolio_daily = forecast_df.groupby("date").predicted_electricity_kwh.sum()
print(portfolio_daily.head(7).round(0))
print("...")
print(portfolio_daily.tail(7).round(0))
