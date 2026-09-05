# LinkedIn Post

Written to avoid the "I'm excited to announce!!!" pattern the brief
explicitly warned against — genuine technical content, real numbers,
one honest story about being wrong and fixing it.

---

Spent the last stretch building an end-to-end energy and carbon
analytics pipeline for a simulated 50-building commercial real estate
portfolio — and the two most useful things I learned came from getting
things wrong first.

The setup: synthetic data across 5 U.S. cities, 2020-2024, run through a
PostgreSQL staging-to-curated data model, a Python data-quality and EDA
layer, three machine learning models, and a Power BI dashboard spec with
20 DAX measures.

Two things worth sharing:

**My synthetic data generator had a calibration bug.** Energy-use
intensity across most building types came out 2-3x higher than real
CBECS benchmarks. I only caught it because I checked the simulated
numbers against real published figures instead of just trusting that the
generation code ran without errors. Fixed the underlying coefficients,
regenerated the dataset, moved on — but it was a good reminder that
"the code runs" and "the output is correct" are different bars.

**More features made my anomaly detector worse, not better.** I built an
Isolation Forest with 13 features — consumption z-score, weather,
occupancy, building type — reasoning that more context should help it
tell "unusual" from "expected given conditions." It scored an F1 of
0.05. Stripping it down to one well-normalized feature brought that to
0.78. Isolation Forest splits on a randomly chosen feature at each node,
so a strong signal genuinely gets diluted by weaker, redundant ones —
something I understood in principle but hadn't seen bite until I tested
both versions side by side.

Final results: demand forecasting and carbon prediction models both
around R² 0.97-0.98, anomaly detection at 92.5% precision / 67.3% recall
against held-out ground truth, and a 10-query SQL analytics layer using
window functions where they actually earn their place.

Full writeup and code: [GitHub link]

#DataAnalytics #Python #SQL #PowerBI #MachineLearning
