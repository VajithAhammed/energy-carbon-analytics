# Interview Preparation

Every answer below is grounded in an actual decision made in this
project, not a generic textbook answer — the goal is being able to
explain this project without depending on anyone else. Organized by the
13 areas from the project brief.

---

## SQL

**Q: Why a staging + curated schema instead of one set of tables?**
Staging mirrors the raw CSVs with minimal constraints so the
deliberately-dirty raw data can load without being silently rejected.
Curated has the real constraints (`CHECK`, `NOT NULL`, foreign keys).
If I'd loaded straight into constrained tables, the constraint violations
would just reject rows on load — the data-quality stage would have
nothing to profile or report on.

**Q: Where did window functions genuinely help, versus where would they
have been over-engineering?**
`ROW_NUMBER() OVER (PARTITION BY building_id, date ORDER BY record_id)`
for deduplication — a `GROUP BY HAVING COUNT(*) > 1` would tell you
duplicates exist but not which specific row to keep. `LAG()` for
month-over-month change — the alternative is a self-join on month-1,
which `LAG` replaces cleanly. I didn't force a window function into the
top-10-buildings query, for example — a plain `ORDER BY ... LIMIT 10`
is already the right tool there.

**Q: Your SQL wasn't run against a live database. How do you know it's
correct?**
Every query's expected result is documented as a comment, cross-checked
against an independent pandas computation on the same underlying data —
different code path, same answer. That's not equivalent to actually
running it, and I say so directly rather than implying it was tested.
`reports/postgres_setup.md` gives the exact steps to actually run it.

**Q: How would you handle the emission-factor join in production, at
scale?**
Right now it's a `LOOKUPVALUE`/CTE join keyed on year, since factors only
change annually. If factors updated more granularly (monthly, or
mid-year revisions), I'd switch to a proper effective-dated join
(`effective_date <= transaction_date`, take the most recent) — I didn't
build that here because it would be solving a problem this dataset
doesn't have yet.

---

## Python

**Q: Why build reusable functions in `src/` instead of writing
everything inline in the notebooks?**
Two reasons: the same logic gets reused across notebooks (carbon
calculation is used in EDA, both ML models, and the SQL cross-checks),
and reusable functions are testable/reviewable independent of a specific
notebook run. Duplicating the carbon formula into three notebooks would
mean three places it could drift out of sync.

**Q: What's a bug you actually hit, not a hypothetical one?**
`pandas` 3.0 changed `groupby().apply()`'s default to exclude the
grouping column from what's passed into the applied function — my
warmup-row-truncation step was silently dropping `building_id`. I found
it because a downstream check (`assert 'building_id' in ml_df.columns`)
failed, traced it to the specific pandas version-behavior change, and
replaced the approach with a vectorized `cumcount()` filter that doesn't
have the same pitfall (and is faster).

---

## Pandas

**Q: Why `groupby(...).transform()` instead of `apply()` for the
lag/rolling features?**
`transform()` returns a Series aligned to the original index, so it
slots directly back into the DataFrame without a merge. It's also the
safer default after the `apply()` bug above — `transform` didn't have
that grouping-column-exclusion issue.

**Q: How did you avoid mixing one building's history into another's
lag/rolling calculation?**
Every lag/rolling operation is `df.groupby("building_id")[col].shift(...)`
or `.transform(lambda s: s.shift(1).rolling(window).mean())` — computed
*within* each group. I didn't just sort by date and take a global
rolling window, which would blend buildings together at each boundary.

---

## Data Cleaning

**Q: How do you decide whether something is a data error to fix or a
genuine anomaly to leave alone?**
Physical impossibility is the test: negative electricity consumption or
occupancy over 100% cannot be real readings — they get corrected.
Consumption 3x higher than a building's own typical range is *unusual*
but physically possible — it gets flagged, not altered, and referred to
the anomaly-detection model instead.

**Q: Why impute with a building+weekday median instead of the column
mean or a global fill?**
A hospital and a warehouse have completely different baseline loads — a
portfolio-wide mean would be meaningless for either. Building+weekday
median respects that a building's own Tuesday looks like its own other
Tuesdays, not like a different building's Saturday.

**Q: What would you do differently in production?**
Track imputation provenance per-row (a flag column: "this value was
imputed, here's how") rather than just logging aggregate counts — useful
for anyone downstream who needs to know which specific numbers are
real meter readings versus filled values.

---

## EDA

**Q: How did you avoid the "30 random charts" trap?**
Every chart in `02_eda.ipynb` maps to one specific business question
from the brief (trend, ranking, efficiency, weather, occupancy, carbon,
cost, seasonality, peak demand) — nine questions, nine charts, not nine
questions and thirty charts.

**Q: The temperature-vs-consumption correlation you report is only
0.181 — isn't that weak?**
That's expected and stated directly in the notebook: the relationship is
U-shaped (both hot and cold days raise load), so a *linear* correlation
understates it by design. The quadratic fit and the scatter plot show
the real relationship; the modest linear number is reported alongside
that explanation, not instead of it.

---

## Power BI

**Q: You didn't build an actual dashboard. What would you actually do
differently if you had Power BI Desktop right now?**
Nothing in the DAX or page design — I'd build it directly from
`powerbi/dashboard_pages.md`. What I couldn't do without the tool is
validate the DAX executes without a typo, or check that visuals render
as intended. That's a real gap I state plainly rather than paper over.

**Q: Why 9 imported CSVs instead of one big pre-joined table?**
Matches the star schema — Power BI's engine (VertiPaq) is optimized for
star schemas with measures computed via DAX at query time, not flat
denormalized tables. A single pre-joined table would also break the
`SAMEPERIODLASTYEAR`/`DATEADD` time-intelligence functions, which need a
proper marked date dimension.

---

## DAX

**Q: Why `LOOKUPVALUE` instead of a modeled relationship for the carbon
calculation?**
The correct emission factor depends on BOTH energy source (electricity
vs. gas — separate columns, not separate rows, on `fact_energy`) and
year. That's not a shape a single 1:many relationship can express, so
the measure does the lookup explicitly, row by row, via `SUMX`.

**Q: Why a measure instead of a calculated column for `Total Carbon`?**
A measure recalculates correctly under any filter context — a specific
building, a date range, a slicer selection. A calculated column would
compute once at refresh time and wouldn't respond to those filters the
same way a measure does; carbon is always something you aggregate, never
something you inspect row-by-row, so a measure is the right tool.

**Q: How do you know your split-by-source measures
(`Total Carbon - Electricity` + `Total Carbon - Gas`) are correct?**
They're required to sum exactly to `Total Carbon (kg CO2e)` — that
invariant is stated directly in the DAX file's comments as a way to
catch a bug in any of the three measures.

---

## Data Modeling

**Q: Why add a `dim_date` table that wasn't in the original data model?**
The brief itself says to adapt the model if the dataset needs it. A date
dimension is the standard star-schema pattern specifically because it
enables built-in time-intelligence (`SAMEPERIODLASTYEAR`, etc.) instead
of reimplementing calendar logic in every measure.

**Q: Why is `fact_energy_cost` at building-month grain instead of
daily, like `fact_energy`?**
Utility tariffs are set monthly/quarterly in reality, not daily — a
daily cost table would just repeat the same number 30 times with zero
analytical benefit. Matching the grain to how the real-world quantity
actually varies is the point, not defaulting to "make every fact table
the same grain."

---

## Machine Learning

**Q: Why compare 3 models instead of just using the best one you knew
in advance?**
Because "the best one" isn't knowable in advance without running the
comparison — Linear Regression came within 2 percentage points of R² of
Random Forest here, which is itself informative (a lot of the
predictive power comes from the lag features, which any model can use).

**Q: How do you know there's no data leakage?**
Not just an exclusion list — a concrete proof. `03_feature_engineering.ipynb`
manually recomputes `lag_1` and `rolling_mean_7` for a specific
building/date from the raw series and checks it matches the function's
output exactly, then computes what the *wrong* (leaky) version would
have been and confirms it's a different number.

**Q: Why exclude `natural_gas_kwh` and `peak_demand_kw` from the demand
forecast, if they're "just" other meter readings?**
They're simultaneous same-day readings, not information available
before the day happens — a real day-ahead forecast wouldn't have them
either. The exclusion list in `04_energy_forecasting.ipynb` is explained
column-by-column, not just declared.

---

## Feature Engineering

**Q: Why lags of 1, 7, and 30 days specifically?**
Yesterday (short-term persistence), same day last week (weekly cycle —
weekday vs. weekend patterns), same day last month (monthly/seasonal
drift). Not an arbitrary grid search — each has a specific business
reason tied to how building occupancy actually cycles.

**Q: Why drop the first 30 days of each building's series instead of
imputing lag values for them?**
Imputing a lag feature means inventing a plausible-looking history that
never happened. Losing 1,500 of 91,350 rows (1.6%) is a much smaller
cost than training on fabricated history.

---

## Time-Series Validation

**Q: Why a chronological split instead of `sklearn`'s default random
split?**
A random split lets the model train on rows that come *after* some of
its test rows — leakage, because a real forecasting model never has
next month's actuals before predicting this month. `time_aware_split()`
explicitly filters on date, and the notebook asserts zero date overlap
between train and test as a hard check, not just an assumption.

**Q: If you had more time, what validation would you add?**
Walk-forward cross-validation — multiple chronological splits at
different points in time, not just one train/test cut — to check the
model's accuracy is stable across different periods, not a lucky result
on this specific 2024 test year.

---

## Anomaly Detection

**Q: Walk me through why your first version of this model failed.**
13 features (z-score, weather, occupancy, calendar, building type) gave
an F1 of 0.05. I diagnosed two separate issues in sequence: first, the
z-score was computed across each building's whole year, so summer months
looked "anomalous" purely from normal seasonality — fixed by normalizing
within building AND month. That fix alone barely moved the score, which
told me seasonality wasn't the main problem. Testing a univariate version
(z-score alone) scored an F1 of 0.78 — Isolation Forest's random
per-node feature selection was diluting the one strong signal among
twelve weaker, partly-redundant ones.

**Q: Isn't contamination=0.0012 just reverse-engineered from the
answer key?**
Yes, and I say so directly in the notebook — that's only possible
because this is synthetic data with known ground truth. A real
deployment has no such ground truth and would calibrate contamination
against investigation capacity and the cost of a missed real fault
instead, which I state explicitly as a limitation, not something to
gloss over.

**Q: How do you know a flagged anomaly isn't just noise?**
I don't, for any single flagged day — that's exactly why the notebook's
summary says a flag means "deserves investigation," not "confirmed
fault." The `fact_maintenance` cross-reference (61.7% of flagged days
have a nearby maintenance ticket, 60.7% specifically an Emergency one)
is offered as supporting evidence, explicitly labeled correlational, not
causal proof.

---

## Business Interpretation

**Q: Your biggest carbon finding is that electricity dominates emissions
at 92%. What would you actually recommend, and what's the caveat?**
Prioritize grid-electricity decarbonization (renewable procurement,
on-site solar) over gas-equipment retrofits for a limited
carbon-reduction budget, since gas is only 8% of the split. Caveat:
that's specific to this simulated portfolio's synthetic gas share and
grid factor assumptions — the *method* (compute the split, prioritize
the bigger lever) generalizes; the specific 92/8 number doesn't
automatically transfer to a real portfolio with a different fuel mix.

**Q: How would you defend the what-if scenario tool's numbers to a
skeptical manager?**
I wouldn't claim more precision than it has — the tool explicitly labels
output as "estimated/simulated," and the underlying assumption (savings
scale linearly with reduction %) is stated as a real limitation, not
hidden in fine print. It's a planning tool for order-of-magnitude
estimates, not a guarantee, and I'd say that in the room, not just in
the documentation.
