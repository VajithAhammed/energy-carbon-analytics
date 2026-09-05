# Resume Bullets

Four bullets, ATS-friendly, every number traceable to
`reports/model_results.md` or the notebooks — nothing invented.

---

- Engineered an end-to-end energy & carbon analytics pipeline (Python,
  PostgreSQL, Power BI) processing 104,270 records across 6 relational
  tables for a 50-building portfolio, including a staging-to-curated
  data-quality layer that resolved 3,451 data errors while preserving
  147 genuine anomalies as flagged, not deleted

- Developed and benchmarked 3 regression models (Linear Regression,
  Random Forest, Gradient Boosting) for energy demand forecasting
  (R²=0.979) and carbon emission prediction (R²=0.974) using leakage-safe
  feature engineering and a chronological train/test split, validated
  with a manual recomputation proof rather than an untested assumption

- Built and iteratively improved an Isolation Forest anomaly detection
  model, diagnosing a feature-dilution issue through direct comparison
  and improving F1-score from 0.05 to 0.78 (92.5% precision, 67.3%
  recall against 147 held-out ground-truth anomalies)

- Designed a star-schema PostgreSQL data model and a 6-page Power BI
  dashboard specification with 20 DAX measures, translating raw
  operational data into executive KPIs, SQL-based business queries using
  window functions, and a what-if scenario analysis tool

---

**Usage note:** pick 3 of these 4 for a resume (4 is often one too many
for a single project entry) — which one to cut depends on which role
you're targeting: keep the SQL/dashboard bullet for a BI-leaning role,
the ML bullets for a data science-leaning one.
