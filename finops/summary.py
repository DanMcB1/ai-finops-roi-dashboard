"""Deterministic, plain-English executive summary.

No LLM. The same filtered data always produces the same sentences, in a
fixed order, so you can explain every line in an interview.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from finops.metrics import (
    detect_anomalies,
    forecast_month_end,
    showback_table,
    totals,
    week_over_week_cost_per_task,
)
from finops.schema import SAMPLE_COMPANY


def _money(value: float | None) -> str:
    if value is None:
        return "—"
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.0f}"


def _hours(value: float) -> str:
    if value >= 10:
        return f"{value:,.0f}"
    return f"{value:,.1f}"


def _pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.0f}%"


def _date(d) -> str:
    if isinstance(d, str):
        d = pd.Timestamp(d).date()
    return d.strftime("%b ") + str(d.day) + d.strftime(", %Y")


def exec_summary(
    usage: pd.DataFrame,
    rates: pd.DataFrame,
    budgets: pd.DataFrame,
    *,
    as_of: date | str,
    period_start: date | str,
    period_end: date | str,
    company: str = SAMPLE_COMPANY,
) -> list[str]:
    """Return a short list of plain-English findings."""
    lines: list[str] = []
    agg = totals(usage, rates, budgets)
    table = showback_table(usage, rates, budgets)
    start_s = _date(period_start)
    end_s = _date(period_end)

    # 1. Headline spend vs time value
    roi = agg["roi"]
    if roi is None:
        roi_phrase = "ROI is not defined because spend is $0"
    else:
        roi_phrase = f"ROI of {_pct(roi)} — about {agg['value_over_spend']:.1f}x the spend in time value"
    lines.append(
        f"For {company}, from {start_s} to {end_s}, AI spend was {_money(agg['spend_usd'])} "
        f"against a {_money(agg['monthly_budget_usd'])} monthly budget "
        f"({_pct(agg['budget_used_pct'])} used, remembering this budget is a monthly figure). "
        f"Teams logged about {_hours(agg['hours_saved'])} hours saved, worth {_money(agg['time_value_usd'])} "
        f"at the loaded rates on the sidebar. Net value is {_money(agg['net_value_usd'])}, or an {roi_phrase}."
    )

    # 2. Best hours / value team
    useful = table[table["hours_saved"] > 0]
    if not useful.empty:
        best_hours = useful.sort_values("hours_saved", ascending=False).iloc[0]
        best_roi = useful.dropna(subset=["roi"]).sort_values("roi", ascending=False)
        lines.append(
            f"{best_hours['team']} saved the most time: about {_hours(best_hours['hours_saved'])} hours, "
            f"worth {_money(best_hours['time_value_usd'])} at a loaded rate of "
            f"{_money(best_hours['hourly_rate_usd'])}/hour, on {_money(best_hours['spend_usd'])} of spend."
        )
        # Avoid repeating the same team if it's also the ROI leader; still mention ROI leader if different
        if not best_roi.empty:
            top = best_roi.iloc[0]
            if top["team"] != best_hours["team"]:
                lines.append(
                    f"{top['team']} has the strongest ROI in this window at {_pct(top['roi'])} "
                    f"(time value {_money(top['time_value_usd'])} on {_money(top['spend_usd'])} spend)."
                )

    # 3. Cost per task week-over-week — call out the largest rise
    wow = week_over_week_cost_per_task(usage, as_of=as_of)
    if not wow.empty:
        moved = wow.dropna(subset=["change_pct"]).copy()
        if not moved.empty:
            up = moved.sort_values("change_pct", ascending=False).iloc[0]
            down = moved.sort_values("change_pct", ascending=True).iloc[0]
            if up["change_pct"] >= 0.08:
                lines.append(
                    f"{up['team']} cost per task rose {_pct(up['change_pct'])} this week "
                    f"(to ${up['cost_per_task_this_week']:.2f} from ${up['cost_per_task_prior_week']:.2f} last week). "
                    f"Worth a look at the mix of models that team is using."
                )
            elif down["change_pct"] <= -0.08:
                lines.append(
                    f"{down['team']} cost per task fell {_pct(down['change_pct'])} this week "
                    f"(to ${down['cost_per_task_this_week']:.2f} from ${down['cost_per_task_prior_week']:.2f})."
                )
            else:
                lines.append("Cost per task was fairly stable week over week across departments.")

    # 4. Anomalies — prefer team-level, fall back to company-level
    team_spikes = detect_anomalies(usage, group="team")
    company_spikes = detect_anomalies(usage, group=None)
    if not team_spikes.empty:
        spike = team_spikes.sort_values("ratio", ascending=False).iloc[0]
        lines.append(
            f"Anomaly: {spike['team']} spent {_money(spike['cost_usd'])} on {_date(spike['date'])}, "
            f"about {spike['ratio']:.1f}x its prior 7-day average of {_money(spike['trailing_avg_usd'])}. "
            "The rule is simple: a day over 2x the trailing average gets flagged — not a fraud verdict, just a prompt to ask what happened."
        )
    elif not company_spikes.empty:
        spike = company_spikes.sort_values("ratio", ascending=False).iloc[0]
        lines.append(
            f"Anomaly: company spend was {_money(spike['cost_usd'])} on {_date(spike['date'])}, "
            f"about {spike['ratio']:.1f}x the prior 7-day average of {_money(spike['trailing_avg_usd'])}."
        )

    # 5. Forecast for the month of as_of
    fc = forecast_month_end(usage, as_of=as_of)
    budget = agg["monthly_budget_usd"]
    proj = fc["projected_month_usd"]
    month_label = fc["month_start"].strftime("%B %Y")
    if fc["is_complete"]:
        lines.append(
            f"{month_label} is complete in this data. Actual spend was {_money(fc['spend_to_date'])} "
            f"versus a {_money(budget)} monthly budget."
        )
    else:
        vs = "under" if budget and proj <= budget else "over"
        gap = abs((budget or 0) - proj)
        lines.append(
            f"Forecast: at the current calendar run rate (${fc['avg_daily_usd']:,.0f}/day), "
            f"{month_label} lands at about {_money(proj)} by {_date(fc['month_end'])} "
            f"({fc['days_remaining']} days left). That would come in {vs} the {_money(budget)} "
            f"monthly budget by {_money(gap)}. This is a straight average, not a seasonal model."
        )

    # 6. Watch-out: lowest net value or over-budget team
    watch = table.copy()
    if not watch.empty:
        over = watch[watch["monthly_budget_usd"] > 0].copy()
        over = over[over["spend_usd"] > over["monthly_budget_usd"]]
        if not over.empty:
            row = over.sort_values("spend_usd", ascending=False).iloc[0]
            lines.append(
                f"Watch: {row['team']} is already over its {_money(row['monthly_budget_usd'])} monthly budget "
                f"at {_money(row['spend_usd'])} in this window."
            )
        else:
            weak = watch.dropna(subset=["roi"])
            if not weak.empty:
                row = weak.sort_values("roi", ascending=True).iloc[0]
                if row["roi"] < 0:
                    lines.append(
                        f"Watch: {row['team']} shows a negative ROI in this window "
                        f"({_money(row['time_value_usd'])} of time value on {_money(row['spend_usd'])} spend). "
                        "That can be a rate, a use-case, or an estimate problem — it is not automatically waste."
                    )

    lines.append(
        "These figures use sample data and assumed rates. Time saved is an estimate, not a measured clock, "
        "and ROI here does not include incremental gross, CSI, or compliance risk."
    )
    return lines
