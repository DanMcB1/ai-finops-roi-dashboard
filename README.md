# Department-Level FinOps & ROI Dashboard

A small, offline demo that shows **AI usage cost and business value by department** for a company that has already rolled out AI tools.

This is a **portfolio demo**, not production software. It does not connect to a billing API, the numbers are **sample data**, and the prices and hourly rates are **illustrative assumptions** — not live vendor pricing and not a real payroll file.

Built for **Daniel McBrearty** as part of a Forward Deployed Engineer / solutions engineer portfolio.

The sample company is **Lakeside Auto Group**, a fictional mid-size dealer group (the same name used in the Architecture Scoper demo). Departments are Sales, F&I, Service, Accounting, Marketing, and IT / Support.

## Why this matters for FDE work

Scoping gets you in the door. After a rollout, the conversation changes: *what did we spend, and what did we get?*

A Forward Deployed Engineer is often the person who has to answer that, in language a CFO and a department head will both accept. In a dealership, nobody manages the business from a single company total — they look at F&I gross, service absorption, and sales by store. AI spend needs the same view:

- cost by team, tool, and use case
- hours saved and a dollar value of that time (using a loaded rate you can debate)
- ROI and cost per task
- who is spending the most, and which days look unusual
- a simple forecast against a monthly budget
- a showback / chargeback table you can export

This dashboard is a practice version of that after-rollout artifact. It is useful in interviews because you can walk through the *math* — cost, time value, anomalies, forecast — without hiding behind a live vendor console.

## Quick start

You need Python 3.10+ (3.13 is fine). No account, no cloud key, no internet after the packages are installed.

```bash
git clone https://github.com/DanMcB1/ai-finops-roi-dashboard.git
cd ai-finops-roi-dashboard
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Or: `./run.sh`

The app opens in your browser (usually [http://localhost:8501](http://localhost:8501)).

- The default view is **November 2026 month-to-date** (the sample data runs through November 24).
- Filter by date range, team, model, or store.
- Edit the **price table**, **loaded hourly rates**, and **monthly budgets** in the sidebar; the dashboard recalculates.
- Download the **showback / chargeback** table as CSV.
- Optionally **upload a usage CSV** in the same schema to replace the sample.

Regenerate the seeded sample, or print the exec summary, from the command line:

```bash
source .venv/bin/activate
python -m finops generate --out data/sample_usage.csv
python -m finops summary --start 2026-11-01 --end 2026-11-24
```

To run the checks (cost, ROI, anomaly, forecast, and sample-data story beats):

```bash
python -m unittest discover -s tests
```

## What’s on the dashboard

- **Exec summary** — a short, deterministic, plain-English briefing. No model writes this; the same filters always produce the same sentences.
- **Snapshot** — spend, monthly budget used, hours saved, value of time, ROI, cost per task.
- **Spend vs budget** and a **run-rate forecast** to month end.
- **Spend over time** by team, model, and use case.
- **Hours saved**, **ROI**, and **cost per task** by team.
- **Top spenders** and **anomalies** (a day over 2× the prior 7-day average).
- **Showback / chargeback** table, exportable as CSV.

A saved example of that table is in [`examples/showback-november-2026.csv`](examples/showback-november-2026.csv).

## How it works

There is **no paid API**. Usage is either the seeded sample in `data/sample_usage.csv` or a file you upload.

1. **Generate.** `python -m finops generate` builds fictional daily usage for September 1 through November 24, 2026, with a fixed seed (`9`). A few story beats are intentional and documented in `finops/generate.py`: Service is high-volume and strong on hours saved; F&I shifts toward a more expensive model after mid-November, so cost per task rises; Marketing has a campaign spike on November 18.
2. **Price.** Cost is `input tokens / 1,000,000 × input price` plus the same for output tokens, plus `API calls × allocated $ / call`. The prices are *fully loaded illustrative unit costs* (a small token component plus an allocated platform share), not a vendor price list. Change them in the sidebar.
3. **Value.** Hours saved = `sum(minutes saved) / 60`. Time value = hours × the team’s loaded hourly rate (an assumption: pay + benefits + overhead).
4. **ROI.** `(time value − spend) / spend`. Value / spend is the multiple. Cost per task is `spend / tasks`.
5. **Anomalies.** A day is flagged when spend is more than **2×** the average of the prior **7** calendar days, and at least **5** of those days have history.
6. **Forecast.** `spend to date + (spend to date ÷ days elapsed) × days remaining` in the calendar month. Quiet days still count. It is a run rate, not a seasonal model.

The exec summary is assembled from those same functions in a fixed order, so you can point at a sentence and show the formula.

### Usage CSV schema

Required columns:

`date, team, user, tool_model, use_case, input_tokens, output_tokens, api_calls, tasks_completed, minutes_saved`

Optional: `store`, `cost_usd`. If `cost_usd` is missing, or if you check **Recalculate costs from the price table**, cost is computed from the price table.

## Honest limitations

- This is a **demo**. The Lakeside Auto Group data is fictional.
- **Time saved is estimated** on each row. A real program would need a measured baseline (time-motion, system timestamps, or a before/after sample), not a number the generator made up.
- **ROI here is only time value vs spend.** It does not include incremental F&I gross or PVR, CSI, no-show reduction, risk, or quality. A “good ROI” department might still be using the tool badly; a “weak ROI” department might be creating revenue the dashboard cannot see.
- Prices and loaded rates are **assumptions**. Change them and the story changes. That is the point of making them editable — and a reason not to treat the headline ROI as a fact.
- The monthly budget is a monthly figure. If you filter to a partial month, “budget used” must be read with that in mind.
- The anomaly rule is deliberately simple. A planned campaign can look like a spike. It is a prompt to ask a question, not a fraud verdict.
- The forecast is a straight calendar average. It does not model Saturdays vs Sundays, seasonality, or known events.
- Uploading a real customer export still keeps this a demo app: no SSO, no audit log, no write-back to a general ledger.

## What a production version would add

- Live pulls from vendor billing and usage APIs (OpenAI, Azure OpenAI, Anthropic, Microsoft Copilot, Google, internal gateways)
- SSO and role-based access so department heads see their numbers and finance sees all of them
- Cost-allocation tags (department, store / rooftop, cost center, application, environment)
- Store-level and product-line views that match how a dealer group already reports
- Outcome metrics beyond minutes: PVR, product penetration, RO cycle time, no-show rate, ticket handle time — agreed in the original SOW
- A measured time-saved methodology, not an assumed minutes field
- Alerting on anomalies and budget thresholds
- Chargeback into the actual GL, with a monthly close and a finance owner
- History, audit, and a paper trail for every rate or price change

## Project layout

```
ai-finops-roi-dashboard/
  app.py                 Streamlit UI
  run.sh                 One-command launcher
  requirements.txt       streamlit, pandas, plotly
  README.md
  LICENSE                MIT, Copyright (c) 2026 Daniel McBrearty
  DEMO_SCRIPT.md         ~1-minute talk track for interviews
  finops/                Pricing, metrics, sample generator, exec summary
  data/                  Seeded sample usage, prices, rates, budgets
  examples/              Example showback CSV
  screenshots/           App screenshot (if present)
  tests/                 Unit tests for the cost / ROI / anomaly math
```

## For interviewers

If you only have a minute, start the app on the November default view, read the exec summary out loud, then point at Service hours, the F&I cost-per-task rise, and the Marketing spike on November 18. The talk track is in [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md).

Daniel’s background is car sales, F&I, and auto software sales (Dealr.cloud), not professional software engineering. This project is meant to show he can talk about **per-department numbers and value** the way a dealer group already talks about gross — and that he is honest about what the math does not prove.

## License

This project is released under the [MIT License](LICENSE). Copyright (c) 2026 Daniel McBrearty.
