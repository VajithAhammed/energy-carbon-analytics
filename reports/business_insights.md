# Business Insights

Every figure below is sourced directly from `notebooks/02_eda.ipynb`,
`notebooks/06_anomaly_detection.ipynb`, and `reports/model_results.md` —
nothing here was estimated for this summary. See those notebooks for the
full analysis behind each point.

> ⚠️ Findings are from synthetic/simulated data (see `data/README.md`)
> and illustrate the kind of insight this pipeline surfaces — not claims
> about any real building portfolio.

## Where consumption and cost concentrate

- The 3 highest-consuming buildings (B049, B014, B023) are all
  **Hospitals** — 24/7 operation makes them dominate absolute load
  despite being a minority of the portfolio by building count. The same
  3 buildings also lead **total cost**.
- **Cost-per-sqft tells a different story than raw cost**, though: New
  York office building B015 has the highest cost-per-sqft ($21.82) among
  the top-10-by-total-cost buildings, driven by New York's higher
  electricity rates rather than by unusually high consumption. (A
  separate, unscoped ranking finds B035 marginally higher still, at
  $21.91 — see `sql/cost_analysis.sql` for the distinction between the
  two rankings.)
- Energy efficiency (EUI) varies **~4x by building type alone** —
  5.7 kWh/sqft/yr (Warehouse) to 22.0 kWh/sqft/yr (Hospital) — before
  even accounting for individual-building variation (4.5 to 23.9
  kWh/sqft/yr across specific buildings).

## What actually drives demand

- Weather's relationship with load is **U-shaped, not linear** — both
  hot and cold days push consumption up. The linear correlation (0.181)
  looks modest specifically *because* the true relationship isn't
  linear; the quadratic fit's minimum-load point sits near 55F.
- Occupancy matters, but there's a real floor: even in the
  lowest-occupancy bucket, buildings still draw **35% of their
  peak-occupancy load** — a baseload that occupancy-based scheduling
  alone can't eliminate (equipment idling, standby loads, partial HVAC).
- Climate zone shapes *seasonality*, not just average load: Phoenix's
  seasonal swing (4,810 kWh between peak and trough month) is more than
  4x Seattle's (1,132 kWh) for otherwise-comparable buildings.
- Portfolio-wide peak demand risk (the number that drives demand
  charges) concentrates in **July** (679 kW average) vs. **October**
  (456 kW average) — a ~6-month window for scheduling major maintenance
  work during naturally lower-risk periods.

## Carbon

- **Electricity accounts for 92% of portfolio emissions vs. 8% for gas**
  — grid decarbonization (a utility-level lever, largely outside a
  facilities team's direct control) matters far more here than
  fuel-switching gas equipment.
- Office buildings are the single largest-emitting *type* in absolute
  terms, despite Hospitals having higher per-sqft intensity — simply
  because there are more office buildings in the portfolio. Absolute and
  intensity-based priorities point to different buildings.
- Portfolio-wide energy fell **-3.2%** from 2020 to 2024, consistent with
  the ~40% of buildings that received a mid-window efficiency retrofit in
  the simulation.

## Anomalies and operations

- The tuned anomaly detector (Isolation Forest, univariate on a
  seasonally-normalized z-score) achieves **92.5% precision / 67.3%
  recall** against known injected anomalies — see
  `reports/model_results.md` for why a simpler feature set dramatically
  outperformed a richer one here.
- **61.7%** of flagged anomalous days have a maintenance record within
  the following 7 days; **60.7%** specifically match an Emergency
  ticket — the strongest available operational explanation, though
  correlational, not proof of causation for any individual flagged day.
- Buildings B023 and B012 (both Hospitals) top the anomaly count —
  consistent with hospitals' 24/7 operation giving more opportunities for
  equipment-fault-style events to occur and be detected.

## Forecast reliability

- The trained demand-forecasting model's forward 90-day forecast (Q1
  2025) totals 15,867,788 kWh portfolio-wide — within **0.2%** of the
  actual 2021-2024 Q1 historical average (15,892,742 kWh). This is the
  expected, reassuring result for a "normal conditions" baseline
  forecast — not a claim of certainty about actual future weather (see
  `powerbi/README.md` for the stated assumption).

## What this suggests for action (illustrative, not a recommendation for any real portfolio)

- **Investigate B049, B014, B023 first** — they lead consumption, cost,
  and (for B023) anomaly count simultaneously.
- **Prioritize grid-electricity decarbonization / renewable procurement
  over gas equipment retrofits** for carbon-reduction budget, given the
  92%/8% emissions split.
- **Schedule non-urgent maintenance in October–November**, avoiding the
  July peak-demand risk window.
- **Treat anomaly flags as investigation triggers, not fault
  confirmations** — per the project brief's explicit instruction, and
  consistent with this model's precision being high but not perfect.
