"""Department-Level FinOps & ROI Dashboard — Streamlit UI.

Run with:  streamlit run app.py
Works fully offline. No API key required. Sample data is fictional.
"""

from __future__ import annotations

from datetime import date
from io import StringIO

import pandas as pd
import plotly.express as px
import streamlit as st

from finops.generate import default_budgets, default_prices, default_rates, generate_usage
from finops.io import UsageSchemaError, normalize_usage, sample_usage_path
from finops.metrics import (
    attach_costs,
    detect_anomalies,
    filter_usage,
    forecast_month_end,
    showback_table,
    totals,
)
from finops.schema import PRICE_NOTE, SAMPLE_AS_OF, SAMPLE_COMPANY, SAMPLE_START
from finops.summary import exec_summary

st.set_page_config(
    page_title="FinOps & ROI Dashboard",
    page_icon="blueprint",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
  .block-container { padding-top: 1.3rem; max-width: 1280px; }
  .demo-banner {
    background: #fff6e5;
    border: 1px solid #e6d2a8;
    color: #5a4500;
    padding: 0.7rem 1rem;
    border-radius: 8px;
    font-size: 0.95rem;
    margin-bottom: 0.8rem;
  }
  .finding {
    background: #f3f5f8;
    border: 1px solid #d5dbe3;
    border-left: 4px solid #1e3a5f;
    border-radius: 8px;
    padding: 0.65rem 0.9rem;
    margin: 0 0 0.55rem;
    font-size: 0.95rem;
    line-height: 1.45;
  }
  h1 { letter-spacing: -0.02em; }
  div[data-testid="stMetric"] {
    background: #f3f5f8;
    border: 1px solid #d5dbe3;
    border-radius: 10px;
    padding: 8px 12px;
  }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

TEAM_COLORS = {
    "Sales": "#1e3a5f",
    "F&I": "#3b6ea5",
    "Service": "#2a7f6f",
    "Accounting": "#6b5b8c",
    "Marketing": "#c47b2b",
    "IT / Support": "#4a5a70",
}

PRESETS = {
    "This month (Nov 2026)": (date(2026, 11, 1), date(2026, 11, 24)),
    "Last 30 days": (date(2026, 10, 26), date(2026, 11, 24)),
    "Last 90 days": (date(2026, 8, 27), date(2026, 11, 24)),
    "All sample data": (date(2026, 9, 1), date(2026, 11, 24)),
}


def money(value: float | None, digits: int = 0) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"${value:,.{digits}f}"


def pct(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value * 100:.0f}%"


def load_sample() -> pd.DataFrame:
    path = sample_usage_path()
    if path.exists():
        return normalize_usage(pd.read_csv(path), prices=default_prices(), recalculate_cost=False)
    return generate_usage()


@st.cache_data(show_spinner=False)
def cached_sample() -> pd.DataFrame:
    return load_sample()


def format_showback(table: pd.DataFrame) -> pd.DataFrame:
    out = table.copy()
    out["Spend"] = out["spend_usd"].map(lambda v: money(v, 0))
    out["Monthly budget"] = out["monthly_budget_usd"].map(lambda v: money(v, 0))
    out["Budget used"] = out["budget_used_pct"].map(pct)
    out["Tasks"] = out["tasks"].map(lambda v: f"{v:,.0f}")
    out["Cost / task"] = out["cost_per_task_usd"].map(lambda v: money(v, 2))
    out["Hours saved"] = out["hours_saved"].map(lambda v: f"{v:,.1f}")
    out["Loaded rate"] = out["hourly_rate_usd"].map(lambda v: money(v, 0))
    out["Time value"] = out["time_value_usd"].map(lambda v: money(v, 0))
    out["Net value"] = out["net_value_usd"].map(lambda v: money(v, 0))
    out["ROI"] = out["roi"].map(pct)
    out["Value / spend"] = out["value_over_spend"].map(lambda v: "—" if v is None or pd.isna(v) else f"{v:.1f}x")
    out["Users"] = out["users"]
    return out[
        [
            "team",
            "Spend",
            "Monthly budget",
            "Budget used",
            "Tasks",
            "Cost / task",
            "Hours saved",
            "Loaded rate",
            "Time value",
            "Net value",
            "ROI",
            "Value / spend",
            "Users",
        ]
    ].rename(columns={"team": "Team"})


def plot_style(fig):
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#1c2430", size=13),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        margin=dict(l=10, r=10, t=30, b=10),
    )
    fig.update_xaxes(gridcolor="#e6eaf0")
    fig.update_yaxes(gridcolor="#e6eaf0")
    return fig


# ---------------------------------------------------------------------------
# Session defaults
# ---------------------------------------------------------------------------
if "usage_source" not in st.session_state:
    st.session_state.usage_source = "sample"
if "uploaded_usage" not in st.session_state:
    st.session_state.uploaded_usage = None
if "rates" not in st.session_state:
    st.session_state.rates = default_rates()
if "budgets" not in st.session_state:
    st.session_state.budgets = default_budgets()
if "prices" not in st.session_state:
    st.session_state.prices = default_prices()
if "recalculate" not in st.session_state:
    st.session_state.recalculate = True

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters & assumptions")
    st.caption(PRICE_NOTE)

    preset = st.selectbox("Date range", list(PRESETS.keys()), index=0)
    start_default, end_default = PRESETS[preset]
    start = st.date_input("From", value=start_default, format="YYYY-MM-DD", key=f"start_{preset}")
    end = st.date_input("To", value=end_default, format="YYYY-MM-DD", key=f"end_{preset}")
    if isinstance(start, tuple):
        start = start[0]
    if isinstance(end, tuple):
        end = end[0]

    st.markdown("---")
    uploaded = st.file_uploader(
        "Optional: upload a usage CSV",
        type=["csv"],
        help="Same schema as data/sample_usage.csv. Required columns: date, team, user, tool_model, use_case, input_tokens, output_tokens, api_calls, tasks_completed, minutes_saved. Optional: store, cost_usd.",
    )
    if uploaded is not None:
        try:
            raw = pd.read_csv(uploaded)
            st.session_state.uploaded_usage = raw
            st.session_state.usage_source = "upload"
            st.success(f"Loaded {len(raw):,} uploaded rows. Applying filters on the main view.")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not read that CSV: {exc}")
    if st.session_state.usage_source == "upload":
        if st.button("Back to sample data"):
            st.session_state.usage_source = "sample"
            st.session_state.uploaded_usage = None
            st.rerun()

    st.markdown("---")
    st.session_state.recalculate = st.checkbox(
        "Recalculate costs from the price table",
        value=st.session_state.recalculate,
        help="On: every row is priced from the table below. Off: keep cost_usd from the file when it is present.",
    )

    with st.expander("Illustrative price table", expanded=False):
        st.caption("Edit a cell and the dashboard will reprice usage on the next rerun.")
        prices = st.data_editor(
            st.session_state.prices,
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            column_config={
                "input_usd_per_m_tokens": st.column_config.NumberColumn("Input $/M tokens", format="$%.2f"),
                "output_usd_per_m_tokens": st.column_config.NumberColumn("Output $/M tokens", format="$%.2f"),
                "usd_per_call": st.column_config.NumberColumn("Allocated $ / call", format="$%.2f"),
            },
            key="price_editor",
        )
        st.session_state.prices = prices

    with st.expander("Loaded hourly rates by team", expanded=False):
        rates = st.data_editor(
            st.session_state.rates,
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            column_config={
                "hourly_rate_usd": st.column_config.NumberColumn("Loaded $/hour", format="$%.0f"),
            },
            key="rate_editor",
        )
        st.session_state.rates = rates

    with st.expander("Monthly budgets by team", expanded=False):
        budgets = st.data_editor(
            st.session_state.budgets,
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            column_config={
                "monthly_budget_usd": st.column_config.NumberColumn("Monthly budget", format="$%.0f"),
            },
            key="budget_editor",
        )
        st.session_state.budgets = budgets

    if st.button("Reset rates, budgets, and prices"):
        st.session_state.rates = default_rates()
        st.session_state.budgets = default_budgets()
        st.session_state.prices = default_prices()
        st.rerun()

    st.markdown("---")
    st.caption("Portfolio demo for Daniel McBrearty · Forward Deployed / Solutions Engineer")

# ---------------------------------------------------------------------------
# Load + filter
# ---------------------------------------------------------------------------
try:
    if st.session_state.usage_source == "upload" and st.session_state.uploaded_usage is not None:
        usage_all = normalize_usage(
            st.session_state.uploaded_usage,
            prices=st.session_state.prices,
            recalculate_cost=st.session_state.recalculate,
        )
        source_label = "Uploaded usage file (still treated as a demo unless you know otherwise)"
    else:
        usage_all = cached_sample()
        if st.session_state.recalculate:
            usage_all = attach_costs(usage_all, st.session_state.prices, overwrite=True)
        source_label = f"Sample data · {SAMPLE_COMPANY}"
except UsageSchemaError as exc:
    st.error(str(exc))
    st.stop()

if start > end:
    st.error("The start date is after the end date.")
    st.stop()

teams_available = sorted(usage_all["team"].dropna().unique().tolist())
models_available = sorted(usage_all["tool_model"].dropna().unique().tolist())
stores_available = (
    sorted(usage_all["store"].dropna().unique().tolist()) if "store" in usage_all.columns else []
)

# Put remaining filters in the main area so the first screen isn't only sidebar
# Team / model filters sit just under the banner.

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("Department-Level FinOps & ROI Dashboard")
st.caption(
    "AI spend, time saved, and return by department. "
    "A portfolio demo — not a live billing console."
)
st.markdown(
    '<div class="demo-banner">'
    "<strong>Honest label:</strong> this dashboard is running on <em>sample data</em> "
    f"for {SAMPLE_COMPANY}, a fictional mid-size dealer group, as of {SAMPLE_AS_OF}. "
    "Prices and loaded hourly rates are illustrative assumptions, not live vendor pricing "
    "and not a real payroll file. Time saved is estimated, not clocked. "
    "This is not production software and it does not connect to a billing API."
    "</div>",
    unsafe_allow_html=True,
)

f1, f2, f3 = st.columns(3)
with f1:
    selected_teams = st.multiselect("Team", teams_available, default=teams_available)
with f2:
    selected_models = st.multiselect("Model / tool", models_available, default=models_available)
with f3:
    selected_stores = st.multiselect(
        "Store (optional)",
        stores_available,
        default=[],
        help="Leave empty to include every store, including the central office.",
    )

usage = filter_usage(
    usage_all,
    start=start,
    end=end,
    teams=selected_teams or None,
    models=selected_models or None,
    stores=selected_stores or None,
)
st.caption(f"{source_label}. Showing {len(usage):,} usage rows from {start.isoformat()} to {end.isoformat()}.")

if usage.empty:
    st.warning("No rows match these filters. Widen the date range or add a team back in.")
    st.stop()

rates = st.session_state.rates
budgets = st.session_state.budgets
agg = totals(usage, rates, budgets)
table = showback_table(usage, rates, budgets)
as_of = min(end, date.fromisoformat(str(pd.to_datetime(usage["date"]).max().date())))
fc = forecast_month_end(usage, as_of=as_of)

# ---------------------------------------------------------------------------
# Exec summary
# ---------------------------------------------------------------------------
st.subheader("Exec summary")
findings = exec_summary(
    usage,
    rates,
    budgets,
    as_of=as_of,
    period_start=start,
    period_end=end,
)
for line in findings:
    st.markdown(f'<div class="finding">{line}</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# KPI row
# ---------------------------------------------------------------------------
st.subheader("Snapshot")
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("AI spend", money(agg["spend_usd"]))
k2.metric(
    "Budget used",
    pct(agg["budget_used_pct"]),
    help="This is spend in the selected window divided by the *monthly* budget. If you are mid-month, that is expected to be under 100%.",
)
k3.metric("Hours saved", f"{agg['hours_saved']:,.0f}")
k4.metric("Value of time saved", money(agg["time_value_usd"]))
k5.metric("ROI", pct(agg["roi"]), help="(time value − spend) / spend. Time value uses the loaded hourly rates.")
k6.metric("Cost per task", money(agg["cost_per_task_usd"], 2))

# ---------------------------------------------------------------------------
# Spend vs budget + forecast
# ---------------------------------------------------------------------------
left, right = st.columns((1.15, 1))
with left:
    st.markdown("#### Spend vs monthly budget")
    bar = table[["team", "spend_usd", "monthly_budget_usd"]].copy()
    bar = bar.rename(columns={"team": "Team", "spend_usd": "Spend in period", "monthly_budget_usd": "Monthly budget"})
    bar_long = bar.melt(id_vars="Team", var_name="Series", value_name="USD")
    fig = px.bar(
        bar_long,
        x="Team",
        y="USD",
        color="Series",
        barmode="group",
        color_discrete_map={"Spend in period": "#1e3a5f", "Monthly budget": "#c5d0e0"},
    )
    plot_style(fig)
    fig.update_layout(yaxis_title="USD", xaxis_title=None)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Budgets are monthly. A mid-month window should usually sit below the budget bar.")

with right:
    st.markdown("#### Forecast to month end")
    if fc["is_complete"]:
        st.write(
            f"{fc['month_start'].strftime('%B %Y')} is complete in this view. "
            f"Actual spend was {money(fc['spend_to_date'])}."
        )
    else:
        st.write(
            f"As of {as_of.strftime('%b')} {as_of.day}, {fc['month_start'].strftime('%Y')}: "
            f"{money(fc['spend_to_date'])} spent over {fc['days_elapsed']} days "
            f"({money(fc['avg_daily_usd'])}/day). "
            f"{fc['days_remaining']} days remain. Projected month-end spend is "
            f"**{money(fc['projected_month_usd'])}** versus a {money(agg['monthly_budget_usd'])} budget."
        )
    fc_df = pd.DataFrame(
        {
            "Item": [
                "Month",
                "As of",
                "Days elapsed",
                "Days remaining",
                "Spend to date",
                "Average daily spend",
                "Projected month-end spend",
                "Monthly budget",
                "Projected vs budget",
            ],
            "Value": [
                fc["month_start"].strftime("%B %Y"),
                str(fc["as_of"]),
                str(fc["days_elapsed"]),
                str(fc["days_remaining"]),
                money(fc["spend_to_date"]),
                money(fc["avg_daily_usd"]),
                money(fc["projected_month_usd"]),
                money(agg["monthly_budget_usd"]),
                money((agg["monthly_budget_usd"] or 0) - fc["projected_month_usd"]),
            ],
        }
    )
    st.dataframe(fc_df, hide_index=True, use_container_width=True)
    st.caption("Forecast method: spend so far ÷ days elapsed × remaining calendar days. Quiet Sundays are included in the average.")

# ---------------------------------------------------------------------------
# Trends
# ---------------------------------------------------------------------------
st.markdown("#### Spend over time")
t1, t2, t3 = st.tabs(["By team", "By model / tool", "By use case"])

def trend_chart(frame: pd.DataFrame, group: str, color_map: dict | None = None):
    tmp = frame.copy()
    tmp["date"] = pd.to_datetime(tmp["date"])
    daily = tmp.groupby(["date", group], as_index=False)["cost_usd"].sum()
    fig = px.area(
        daily,
        x="date",
        y="cost_usd",
        color=group,
        color_discrete_map=color_map or {},
    )
    plot_style(fig)
    fig.update_layout(yaxis_title="Spend (USD)", xaxis_title=None, yaxis_tickprefix="$")
    return fig

with t1:
    st.plotly_chart(trend_chart(usage, "team", TEAM_COLORS), use_container_width=True)
with t2:
    st.plotly_chart(trend_chart(usage, "tool_model"), use_container_width=True)
with t3:
    st.plotly_chart(trend_chart(usage, "use_case"), use_container_width=True)

# ---------------------------------------------------------------------------
# Hours, ROI, cost per task
# ---------------------------------------------------------------------------
c_left, c_right = st.columns(2)
with c_left:
    st.markdown("#### Hours saved and time value by team")
    hv = table[["team", "hours_saved", "time_value_usd"]].copy()
    fig = px.bar(
        hv,
        x="team",
        y="hours_saved",
        color="team",
        color_discrete_map=TEAM_COLORS,
        labels={"hours_saved": "Hours saved", "team": "Team"},
    )
    plot_style(fig)
    fig.update_layout(showlegend=False, xaxis_title=None)
    st.plotly_chart(fig, use_container_width=True)
with c_right:
    st.markdown("#### ROI and cost per task")
    roi_df = table[["team", "roi", "cost_per_task_usd", "net_value_usd"]].copy()
    roi_df["ROI %"] = roi_df["roi"].map(lambda v: None if v is None or pd.isna(v) else v * 100)
    fig = px.bar(
        roi_df.dropna(subset=["ROI %"]),
        x="team",
        y="ROI %",
        color="team",
        color_discrete_map=TEAM_COLORS,
        labels={"team": "Team"},
    )
    plot_style(fig)
    fig.update_layout(showlegend=False, xaxis_title=None, yaxis_ticksuffix="%")
    st.plotly_chart(fig, use_container_width=True)
    st.caption("ROI = (value of time saved − AI spend) / AI spend. A high number can mean a modest spend as much as a large saving.")

# ---------------------------------------------------------------------------
# Top spenders + anomalies
# ---------------------------------------------------------------------------
s1, s2 = st.columns(2)
with s1:
    st.markdown("#### Top spenders")
    spenders = (
        usage.groupby(["user", "team"], as_index=False)
        .agg(spend_usd=("cost_usd", "sum"), tasks=("tasks_completed", "sum"), minutes=("minutes_saved", "sum"))
        .sort_values("spend_usd", ascending=False)
        .head(10)
    )
    spenders["Hours saved"] = (spenders["minutes"] / 60).map(lambda v: f"{v:,.1f}")
    spenders["Spend"] = spenders["spend_usd"].map(lambda v: money(v, 0))
    spenders["Tasks"] = spenders["tasks"].map(lambda v: f"{v:,.0f}")
    st.dataframe(
        spenders.rename(columns={"user": "User", "team": "Team"})[["User", "Team", "Spend", "Tasks", "Hours saved"]],
        hide_index=True,
        use_container_width=True,
    )
with s2:
    st.markdown("#### Anomalies")
    st.caption("A day is flagged when spend is more than 2× the average of the prior 7 days, with at least 5 prior days of history. Team-level first, then company-level.")
    team_flags = detect_anomalies(usage, group="team")
    company_flags = detect_anomalies(usage, group=None)
    if team_flags.empty and company_flags.empty:
        st.info("No daily spikes over 2× the trailing average in this window.")
    else:
        if not team_flags.empty:
            show = team_flags.copy()
            show["Date"] = pd.to_datetime(show["date"]).dt.strftime("%Y-%m-%d")
            show["Spend"] = show["cost_usd"].map(lambda v: money(v, 0))
            show["Trailing avg"] = show["trailing_avg_usd"].map(lambda v: money(v, 0))
            show["Ratio"] = show["ratio"].map(lambda v: f"{v:.1f}x")
            st.dataframe(
                show.rename(columns={"team": "Team"})[["Date", "Team", "Spend", "Trailing avg", "Ratio"]],
                hide_index=True,
                use_container_width=True,
            )
        if not company_flags.empty:
            with st.expander("Company-level daily spikes"):
                show = company_flags.copy()
                show["Date"] = pd.to_datetime(show["date"]).dt.strftime("%Y-%m-%d")
                show["Spend"] = show["cost_usd"].map(lambda v: money(v, 0))
                show["Trailing avg"] = show["trailing_avg_usd"].map(lambda v: money(v, 0))
                show["Ratio"] = show["ratio"].map(lambda v: f"{v:.1f}x")
                st.dataframe(show[["Date", "Spend", "Trailing avg", "Ratio"]], hide_index=True, use_container_width=True)

# ---------------------------------------------------------------------------
# Showback / chargeback
# ---------------------------------------------------------------------------
st.subheader("Showback / chargeback")
st.caption(
    "One row per team for the current filters. Export this table to start a chargeback conversation. "
    "Monthly budgets are shown even when the date window is not a full month — read 'Budget used' with that in mind."
)
display = format_showback(table)
st.dataframe(display, hide_index=True, use_container_width=True)

export_cols = [
    "team",
    "spend_usd",
    "monthly_budget_usd",
    "budget_used_pct",
    "tasks",
    "cost_per_task_usd",
    "hours_saved",
    "hourly_rate_usd",
    "time_value_usd",
    "net_value_usd",
    "roi",
    "value_over_spend",
    "users",
]
csv_buf = StringIO()
table[export_cols].to_csv(csv_buf, index=False)
st.download_button(
    "Download showback table as CSV",
    data=csv_buf.getvalue().encode("utf-8"),
    file_name=f"showback-{start.isoformat()}-to-{end.isoformat()}.csv",
    mime="text/csv",
    type="primary",
)

raw_buf = StringIO()
usage.to_csv(raw_buf, index=False)
st.download_button(
    "Download filtered usage rows as CSV",
    data=raw_buf.getvalue().encode("utf-8"),
    file_name=f"usage-{start.isoformat()}-to-{end.isoformat()}.csv",
    mime="text/csv",
)

# Persist a copy of the current showback into examples/ when running locally is optional;
# the generate CLI writes the sample, and tests cover the math.

with st.expander("How the math works"):
    st.markdown(
        """
- **Cost.** `input tokens / 1,000,000 × input price` plus the same for output tokens, plus `API calls × allocated $ / call`. Prices are illustrative and editable.
- **Hours saved.** `sum(minutes saved) / 60`. Minutes are estimates on each usage row, not a measured time clock.
- **Time value.** `hours saved × loaded hourly rate` for that team. The rate is an assumption (pay + benefits + overhead), not a payroll extract.
- **ROI.** `(time value − spend) / spend`. **Value / spend** is the multiple (`time value / spend`).
- **Cost per task.** `spend / tasks completed`.
- **Anomaly.** A day whose spend is more than **2×** the average of the prior **7** calendar days, with at least **5** prior days of history.
- **Forecast.** `spend to date + (spend to date ÷ days elapsed) × days remaining` in the calendar month. It is a run rate, not a seasonal model.
        """
    )
