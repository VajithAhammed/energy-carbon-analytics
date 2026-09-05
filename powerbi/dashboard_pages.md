# Power BI — Dashboard Page Designs

Six pages, matching the project brief exactly. Each visual lists its type,
fields, and the specific business question it answers — no filler charts.

---

## Page 1 — Executive Summary

**KPI cards** (6, top row): Total Energy · Total Carbon (kg CO2e) · Total
Cost · Energy Intensity · Renewable % · YoY Energy Growth — each its own
card visual bound to the matching measure from `dax_measures.dax`.

**Visuals:**
| Visual | Type | Fields | Answers |
|---|---|---|---|
| Energy trend | Line chart | Axis: `dim_date[date]` (month), Value: `[Total Energy]` | Is consumption rising or falling? |
| Carbon trend | Line chart | Axis: month, Value: `[Total Carbon (kg CO2e)]` | Does carbon track energy 1:1, or diverge (e.g. grid decarbonizing)? |
| Top buildings | Bar chart | Axis: `dim_building[building_name]`, Value: `[Total Energy]`, Top N filter = 10 | Where's the biggest absolute load? |
| Energy by building type | Donut/bar | Axis: `dim_building[building_type]`, Value: `[Total Energy]` | Which building class dominates the portfolio? |
| Renewable contribution | Gauge or bar | Value: `[Renewable %]`, target = portfolio average | How much of the portfolio is self-generated? |

**Filters (page-level):** year slicer (`dim_date[year]`), city slicer
(`dim_building[city]`).

---

## Page 2 — Energy Performance

| Visual | Type | Fields | Answers |
|---|---|---|---|
| Building ranking | Table or bar | `dim_building[building_name]`, `[Total Energy]`, sorted desc | Full ranking, not just top 10 |
| Energy intensity | Bar chart | Axis: `building_type`, Value: `[Energy Intensity]` | Which type is least efficient per sqft? |
| Consumption trend | Line | Axis: date (day or week), Value: `[Total Energy]`, Legend: `building_type` | Trend by building class over time |
| Peak demand | Bar | Axis: `building_name`, Value: `[Peak Demand (kW)]`, Top N = 10 | Which buildings drive demand-charge risk? |
| Occupancy vs consumption | Scatter | X: `fact_energy[occupancy_rate]`, Y: `fact_energy[electricity_kwh]` | Does load actually track occupancy? |
| Weather vs consumption | Scatter | X: `[Temperature (F)]` (the calculated column from `powerbi/README.md`), Y: `electricity_kwh` | The U-shaped relationship confirmed in `02_eda.ipynb` |

**Drill-through:** right-click a building in the ranking table → drill
through to a single-building detail page (optional 7th page) showing that
building's full trend, peak demand, and maintenance history.

---

## Page 3 — Carbon & Sustainability

| Visual | Type | Fields | Answers |
|---|---|---|---|
| CO2 emissions trend | Line | Axis: month, Value: `[Total Carbon (kg CO2e)]` | |
| Carbon intensity | Bar | Axis: `building_type`, Value: `[Carbon Intensity]` | |
| Emissions by source | Donut | Legend: energy source, Value: `[Total Carbon - Electricity (kg CO2e)]` and `[Total Carbon - Gas (kg CO2e)]` | Expected split: 92% / 8% — confirmed in `02_eda.ipynb` |
| Renewable energy | Bar | Axis: `building_name` (top 10 by `[Renewable %]`) | Which buildings lean hardest on solar? |
| Carbon reduction opportunity | Bar | Axis: `building_name`, Value: `[Estimated CO2 Avoided by Renewables (kg CO2e)]`, sorted desc | Where would more solar have the biggest impact? |

**Tooltip page (optional):** hovering a building shows a mini card with
its EUI, carbon intensity, and renewable % together.

---

## Page 4 — Anomaly Monitoring

Uses `anomaly_flags.csv` (from `notebooks/06_anomaly_detection.ipynb`) —
`anomaly_flag`, `anomaly_score`, `elec_zscore` per building-day.

| Visual | Type | Fields | Answers |
|---|---|---|---|
| Anomaly count (KPI card) | Card | `COUNTROWS(FILTER(anomaly_flags, anomaly_flags[anomaly_flag] = TRUE))` | Total flagged days, current filter context |
| Anomaly rate (KPI card) | Card | Anomaly count ÷ `COUNTROWS(anomaly_flags)` | Expected ~0.12% (107/91,350 — see `06_anomaly_detection.ipynb`) |
| Buildings with most anomalies | Bar | Axis: `building_name`, Value: anomaly count, Top N = 10 | Expected top: B023, B012 (Hospitals) — confirmed in the notebook |
| Anomaly timeline | Scatter/line | X: date, Y: `elec_zscore`, color = `anomaly_flag` | When did severe events cluster? |
| Consumption spikes | Line + markers | `electricity_kwh` over time for a selected building, with flagged days marked | Visual "here's the spike" for a specific building — use a building slicer |

**Caution banner (text box, top of page):** "A flag means this behavior
deserves investigation — not that a fault is confirmed. See
`notebooks/06_anomaly_detection.ipynb` for the full methodology and
honest precision/recall numbers (92.5% / 67.3%)."

---

## Page 5 — Forecasting

Uses `energy_forecast_2025Q1.csv` — a REAL forecast from the trained
Random Forest model (`models/energy_demand_model.joblib`), not placeholder
numbers. See `src/generate_forecast.py` for exactly how it was produced.

| Visual | Type | Fields | Answers |
|---|---|---|---|
| Historical + forecasted energy | Line chart, two series | Series 1: `fact_energy[electricity_kwh]` by date (solid line) through 2024-12-31; Series 2: `energy_forecast_2025Q1[predicted_electricity_kwh]` by date (dashed line) from 2025-01-01 | One continuous view, actual vs. forecast |
| 30-day forecast | Line, filtered to 2025-01-01 through 2025-01-30 | | Near-term view |
| 90-day forecast | Line, full 2025-01-01 through 2025-03-31 range | | Full forecast horizon |
| Building-level forecast | Line, filterable by `building_id` slicer | | Drill into one building's forecast |

**Limitations text box (required, not optional polish):** "This forecast
assumes NORMAL weather (each city's 2020-2024 historical average for that
calendar day) and typical occupancy patterns — not an actual weather
forecast. It will not anticipate real weather anomalies. Validated
against historical Q1 averages: the model's Q1 2025 portfolio total
(15,867,788 kWh) lands within 0.2% of the 2021-2024 Q1 average
(15,892,742 kWh) — a reasonable outcome for a 'normal conditions'
baseline forecast, not a claim of certainty about actual 2025 weather."

---

## Page 6 — Management Scenario

**What-if controls:** two slicers bound to the parameters from
`powerbi/README.md` — "Energy Reduction %" (0-30%) and "Renewable
Increase %" (0-20%).

| Visual | Type | Fields | Answers |
|---|---|---|---|
| Current vs. scenario energy | KPI cards, side by side | `[Total Energy]` vs `[Total Energy] - [Estimated Energy Savings (kWh)]` | |
| Estimated savings | 3 KPI cards | `[Estimated Energy Savings (kWh)]`, `[Estimated Cost Savings]`, `[Estimated CO2 Avoided]` | Direct answer to the brief's scenario requirement |
| Renewable scenario | KPI card | `[Estimated Additional CO2 Avoided from Renewable Increase]` | |
| Sensitivity chart | Line, X = reduction % (0-30 in 1% steps), Y = estimated cost savings | Uses the parameter's built-in "what happens across the whole range" chart type | Lets a manager see the curve, not just one point |

**Banner (required, matches the brief's explicit instruction):** "All
figures on this page are ESTIMATED / SIMULATED business impact based on
a simplified linear scaling assumption — see `dax_measures.dax` for the
stated limitations. Not a guaranteed outcome."

---

## Cross-page consistency

Every page uses the SAME measures from `dax_measures.dax` — a KPI never
gets redefined differently on different pages. If `[Total Energy]` on
Page 2 and Page 3 ever show different numbers for the same filter
context, that's a real bug (duplicated/drifted measure logic), not a
rounding difference — same principle as Stage 2's "one definition of
unusual, not two" for `is_statistical_outlier`.
