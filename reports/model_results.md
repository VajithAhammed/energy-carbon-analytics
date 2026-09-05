# Model Results

Every number below is copied directly from `reports/*_comparison.csv` and
`reports/anomaly_detection_contamination_sweep.csv` — the actual output
of `.fit()` / `.predict()` calls in the notebooks, not restated from
memory or invented for this summary.

> ⚠️ Trained on synthetic/simulated data — see `data/README.md`. Absolute
> error magnitudes (kWh, kg CO2e) are specific to this synthetic
> portfolio's scale and won't transfer to a different building portfolio;
> the R²/precision/recall figures and the methodology are the
> transferable parts.

## Model 1 — Energy Demand Forecasting

**Target:** `electricity_kwh` · **Notebook:** `04_energy_forecasting.ipynb`
**Split:** chronological — train 2020-2023 (71,550 rows), test 2024
(18,300 rows). Never randomly shuffled (see notebook for why that would
leak).

| Model | MAE | RMSE | R² | Fit time |
|---|---|---|---|---|
| **Random Forest (winner)** | **262.8** | **523.1** | **0.9790** | 122.2s |
| Gradient Boosting | 312.1 | 575.8 | 0.9745 | 38.0s |
| Linear Regression | 405.9 | 680.9 | 0.9644 | 0.2s |

- Naive baseline (predict yesterday's value) comparison, top feature
  drivers, worst-predicted-day analysis, and the actual-vs-predicted
  chart are all in the notebook — not repeated here to avoid this
  document quietly drifting out of sync with the source of truth.
- **Where it fails:** cross-checked directly (not assumed) — the
  worst-predicted test days disproportionately match genuine injected
  anomalies, which is the expected and correct failure mode for a model
  trained on typical patterns.

## Model 2 — Carbon Emissions Prediction

**Target:** `carbon_emissions_kgCO2e` · **Notebook:** `05_carbon_prediction.ipynb`
**Feature set:** deliberately excludes electricity/gas/cost columns
(near-total leakage, since carbon is mechanically derived from them) —
uses weather/occupancy/building/calendar features and carbon's own
lag/rolling history instead, mirroring Model 1's approach on a different
target.

| Model | MAE | RMSE | R² | Fit time |
|---|---|---|---|---|
| **Random Forest (winner)** | **119.8** | **223.1** | **0.9744** | 125.5s |
| Gradient Boosting | 129.0 | 228.0 | 0.9732 | 37.3s |
| Linear Regression | 162.8 | 264.3 | 0.9640 | 0.2s |

- Structurally similar results to Model 1 are expected and explained in
  the notebook: carbon is close to a linear transform of energy volume,
  so this model is largely re-deriving Model 1's problem one level
  removed.

## Model 3 — Anomaly Detection

**Method:** Isolation Forest · **Notebook:** `06_anomaly_detection.ipynb`
**Evaluated against:** 147 genuinely injected anomalies, held out from
every other stage.

**This model went through 3 documented attempts, not 1** — worth
including here because the process is as informative as the result:

| Attempt | Features | Precision | Recall | F1 |
|---|---|---|---|---|
| 1 | 13-dim, whole-year z-score | ~3% | ~10% | ~0.05 |
| 2 | 13-dim, monthly z-score (seasonality bug fixed) | ~3% | ~8% | ~0.04 |
| **3 (final)** | **univariate monthly z-score** | **92.5%** | **67.3%** | **0.780** |

Full contamination sweep for the final (univariate) model:

| contamination | n flagged | precision | recall | F1 |
|---|---|---|---|---|
| 0.0012 (**chosen**) | 107 | **92.5%** | 67.3% | **0.780** |
| 0.0016 | 141 | 75.2% | 72.1% | 0.736 |
| 0.002 | 175 | 62.9% | 74.8% | 0.683 |
| 0.0025 | 224 | 50.9% | 77.6% | 0.615 |
| 0.003 | 275 | 42.5% | 79.6% | 0.555 |
| 0.004 | 360 | 33.6% | 82.3% | 0.477 |
| 0.005 | 456 | 26.5% | 82.3% | 0.401 |

**The actual finding:** adding weather/occupancy/building-type context
to the detection model made it dramatically *worse* (F1 0.05 vs 0.78) —
Isolation Forest's random per-node feature selection diluted the one
genuinely strong signal among twelve weaker/redundant ones. The fix was
simplifying, not adding more features. See the notebook for the full
diagnostic trail.

**Operational cross-reference (using `fact_maintenance`):** 61.7% of
flagged days have a maintenance record within 7 days after; 60.7%
specifically match an Emergency ticket — the strongest available
(correlational, not causal) explanation.

## Cross-cutting limitations (all 3 models)

- Weather features are historical actuals, not forecasts.
- No hyperparameter search beyond the values shown — a deliberate choice
  to establish model *class* first, not chase the last 0.5% of accuracy.
- Single chronological split (Models 1-2), not walk-forward
  cross-validation — reasonable for a portfolio project, not for a
  production deployment decision.
- Anomaly detection's contamination parameter was tuned against ground
  truth that exists only because this data is synthetic — a real
  deployment needs a different calibration approach entirely (see
  `06_anomaly_detection.ipynb`'s summary).
