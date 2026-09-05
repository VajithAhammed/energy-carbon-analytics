# Portfolio Case Study

For a portfolio website's project page — narrative structure, more
storytelling than the GitHub README, same underlying facts.

---

## Hero

**Energy Consumption & Carbon Analytics**
An end-to-end analytics platform for energy monitoring, carbon
intelligence, and demand forecasting across a simulated 50-building
commercial real estate portfolio.

## Problem

A company operating dozens of commercial buildings across multiple
cities has no unified way to answer basic operational questions: which
buildings waste the most energy, where carbon emissions concentrate,
whether unusual consumption patterns deserve investigation, and what
demand will look like next quarter. Data exists — meters, utility bills,
maintenance logs — but it's scattered and unvalidated.

## Approach

```
Data → SQL → Python → ML → Power BI → Business Decision
```

- **Data:** a purpose-built synthetic dataset (real public datasets don't
  combine energy + weather + occupancy + cost + emissions + maintenance
  for the same buildings) — 104,270 rows across 6 related tables,
  deliberately seeded with realistic data-quality issues to solve, not
  hidden away.
- **SQL:** a staging → curated PostgreSQL schema, with the "why staging
  first" decision itself being a deliberate one — see Lessons Learned.
- **Python:** data quality (distinguishing genuine data errors from real
  anomalies — never the same treatment for both), EDA answering 9
  specific business questions, and leakage-safe feature engineering.
- **ML:** three models, each independently evaluated against a
  chronological holdout, not a single blended pipeline.
- **Power BI:** a 6-page dashboard specification with 20 DAX measures —
  built as a complete blueprint rather than a working file, since the
  build environment had no Power BI Desktop available (stated directly,
  not glossed over).
- **Business decision:** a what-if scenario tool letting a manager see
  estimated savings from a target energy-reduction percentage, live.

## Key Findings

Real numbers, not illustrative placeholders:

- Electricity accounts for **92% of portfolio carbon emissions** vs. 8%
  for gas — grid decarbonization matters more here than fuel-switching
  equipment.
- Even at near-zero occupancy, buildings retain **35% of their
  peak-occupancy energy load** — a real baseload floor that
  scheduling alone can't close.
- Climate zone shapes *seasonal swing size*, not just average
  consumption — Phoenix's seasonal range is over 4x Seattle's for
  otherwise comparable buildings.
- A 90-day forward energy forecast landed within **0.2%** of the actual
  historical Q1 average — validated against real history before being
  trusted, not assumed accurate.

Full list: `reports/business_insights.md` in the repo.

## Dashboard

Six pages — Executive Summary, Energy Performance, Carbon &
Sustainability, Anomaly Monitoring, Forecasting, and a What-If
Management Scenario tool — specified in complete implementation detail
(data model, 20 DAX measures with business rationale, visual-by-visual
page designs). **No live screenshots exist yet** — the build environment
had no Power BI Desktop — so this section will be updated with real
screenshots once the dashboard is built from that spec. That gap is
stated here on purpose, not hidden behind a placeholder image.

## Machine Learning

| Model | Metric | Result |
|---|---|---|
| Energy demand forecasting (Random Forest) | R² | 0.979 |
| Carbon emissions prediction (Random Forest) | R² | 0.974 |
| Anomaly detection (Isolation Forest) | Precision / Recall | 92.5% / 67.3% |

The anomaly detection result is the more interesting story: a richer
13-feature version of the model scored an F1 of 0.05. Diagnosing why —
and simplifying to a single well-normalized feature instead — brought
that to 0.78. Full comparison: `reports/model_results.md`.

## Business Impact

The Power BI scenario tool estimates energy, cost, and CO2 savings from
a manager-set reduction target (0-30%, adjustable live via a What-If
parameter), explicitly labeled **estimated/simulated** per the honest
framing this project holds throughout — a linear scaling assumption with
its own stated limitation (demand charges don't necessarily scale
linearly with average-load reduction), not a guaranteed outcome.

## Lessons Learned

**Technical:** a synthetic data generator's calibration needs checking
against real-world benchmarks, not just "does the code run without
errors" — an early version of this project's energy-use-intensity values
were 2-3x too high until checked against real building-energy figures
and fixed. Separately, Isolation Forest's random per-node feature
selection means more context features can dilute a strong signal rather
than sharpen it — confirmed by testing both versions directly rather
than assuming richer inputs are always better.

**Business:** the specific finding that grid electricity (not gas)
dominates this portfolio's emissions reshapes where a real carbon-budget
would go — a good example of why the analysis has to precede the
recommendation, not the other way around.

**Process:** building in stages, with genuine validation at each one
(row counts, leakage proofs, cross-checks against independently computed
numbers) caught real bugs — the pandas 3.0 behavior change that silently
dropped a key column, the EUI miscalibration, an unverified claim in a
dashboard spec — before they compounded into the next stage.
