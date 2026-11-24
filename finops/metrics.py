"""Cost, ROI, anomaly, forecast, and showback math.

Every function here is pure and unit-tested so the interview walk-through
can point at a formula, not a hidden model.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from typing import Iterable

import pandas as pd

from finops.schema import REQUIRED_USAGE_COLUMNS


def compute_cost(
    input_tokens: float,
    output_tokens: float,
    api_calls: float,
    input_usd_per_m_tokens: float,
    output_usd_per_m_tokens: float,
    usd_per_call: float,
) -> float:
    """Cost from token volumes and/or a per-call price.

    cost = input_tokens / 1e6 * input_price
         + output_tokens / 1e6 * output_price
         + api_calls * usd_per_call
    """
    input_tokens = 0.0 if pd.isna(input_tokens) else float(input_tokens)
    output_tokens = 0.0 if pd.isna(output_tokens) else float(output_tokens)
    api_calls = 0.0 if pd.isna(api_calls) else float(api_calls)
    return (
        (input_tokens / 1_000_000.0) * float(input_usd_per_m_tokens)
        + (output_tokens / 1_000_000.0) * float(output_usd_per_m_tokens)
        + api_calls * float(usd_per_call)
    )


def attach_costs(usage: pd.DataFrame, prices: pd.DataFrame, *, overwrite: bool = True) -> pd.DataFrame:
    """Join the price table and compute cost_usd for each row."""
    if usage.empty:
        out = usage.copy()
        if "cost_usd" not in out.columns:
            out["cost_usd"] = pd.Series(dtype="float64")
        return out

    price_cols = [
        "tool_model",
        "input_usd_per_m_tokens",
        "output_usd_per_m_tokens",
        "usd_per_call",
    ]
    missing = [c for c in price_cols if c not in prices.columns]
    if missing:
        raise ValueError(f"Price table missing columns: {missing}")

    prices_small = prices[price_cols].drop_duplicates("tool_model")
    out = usage.merge(prices_small, on="tool_model", how="left")
    computed = [
        compute_cost(
            row.get("input_tokens", 0),
            row.get("output_tokens", 0),
            row.get("api_calls", 0),
            row["input_usd_per_m_tokens"] if pd.notna(row.get("input_usd_per_m_tokens")) else 0.0,
            row["output_usd_per_m_tokens"] if pd.notna(row.get("output_usd_per_m_tokens")) else 0.0,
            row["usd_per_call"] if pd.notna(row.get("usd_per_call")) else 0.0,
        )
        for row in out.to_dict(orient="records")
    ]
    if overwrite or "cost_usd" not in out.columns:
        out["cost_usd"] = computed
    else:
        existing = out["cost_usd"]
        out["cost_usd"] = [
            float(e) if pd.notna(e) else c for e, c in zip(existing, computed)
        ]
    out = out.drop(columns=["input_usd_per_m_tokens", "output_usd_per_m_tokens", "usd_per_call"])
    return out


def hours_saved(minutes: pd.Series | float) -> float:
    if isinstance(minutes, pd.Series):
        return float(minutes.fillna(0).sum() / 60.0)
    return float(minutes or 0) / 60.0


def time_value(hours: float, hourly_rate_usd: float) -> float:
    return float(hours) * float(hourly_rate_usd)


def roi(value_usd: float, cost_usd: float) -> float | None:
    """(time value - cost) / cost. None when cost is 0."""
    if cost_usd == 0 or pd.isna(cost_usd):
        return None
    return (float(value_usd) - float(cost_usd)) / float(cost_usd)


def cost_per_task(cost_usd: float, tasks: float) -> float | None:
    if tasks == 0 or pd.isna(tasks):
        return None
    return float(cost_usd) / float(tasks)


def value_over_spend(value_usd: float, cost_usd: float) -> float | None:
    """Time-value multiple (value / spend). None when spend is 0."""
    if cost_usd == 0 or pd.isna(cost_usd):
        return None
    return float(value_usd) / float(cost_usd)


def _as_date(value) -> date:
    if isinstance(value, date) and not isinstance(value, pd.Timestamp):
        return value
    return pd.Timestamp(value).date()


def filter_usage(
    usage: pd.DataFrame,
    *,
    start: date | str | None = None,
    end: date | str | None = None,
    teams: Iterable[str] | None = None,
    models: Iterable[str] | None = None,
    stores: Iterable[str] | None = None,
) -> pd.DataFrame:
    out = usage.copy()
    if out.empty:
        return out
    dates = pd.to_datetime(out["date"]).dt.date
    if start is not None:
        out = out.loc[dates >= _as_date(start)]
        dates = pd.to_datetime(out["date"]).dt.date
    if end is not None:
        out = out.loc[dates <= _as_date(end)]
    if teams:
        team_set = set(teams)
        out = out.loc[out["team"].isin(team_set)]
    if models:
        model_set = set(models)
        out = out.loc[out["tool_model"].isin(model_set)]
    if stores and "store" in out.columns:
        store_set = set(stores)
        out = out.loc[out["store"].isin(store_set)]
    return out.reset_index(drop=True)


def daily_spend(usage: pd.DataFrame, *, group: str | None = None) -> pd.DataFrame:
    """Spend by calendar day, optionally split by a column such as team."""
    if usage.empty:
        cols = ["date", "cost_usd"]
        if group:
            cols.insert(1, group)
        return pd.DataFrame(columns=cols)
    frame = usage.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    keys = ["date"] + ([group] if group else [])
    return (
        frame.groupby(keys, as_index=False)["cost_usd"]
        .sum()
        .sort_values(keys)
        .reset_index(drop=True)
    )


def detect_anomalies(
    usage: pd.DataFrame,
    *,
    window: int = 7,
    threshold: float = 2.0,
    min_prior_days: int = 5,
    group: str | None = None,
) -> pd.DataFrame:
    """Flag days whose spend is more than `threshold` times the trailing average.

    The trailing average is the mean daily spend over the previous `window`
    calendar days (not including the day itself). A day is only flagged if
    at least `min_prior_days` of those prior days have a spend row, so the
    first few days of a series are not treated as spikes.
    """
    if window < 1:
        raise ValueError("window must be >= 1")
    if threshold <= 0:
        raise ValueError("threshold must be > 0")

    rows = []
    groups = [None] if group is None else list(usage[group].dropna().unique()) if not usage.empty else []
    if group is None:
        series_list = [(None, daily_spend(usage))]
    else:
        series_list = [(g, daily_spend(usage[usage[group] == g])) for g in groups]

    for label, daily in series_list:
        if daily.empty:
            continue
        daily = daily.sort_values("date").reset_index(drop=True)
        by_date = {row["date"]: float(row["cost_usd"]) for _, row in daily.iterrows()}
        for current in daily["date"].tolist():
            prior_dates = [current - timedelta(days=i) for i in range(1, window + 1)]
            prior_values = [by_date[d] for d in prior_dates if d in by_date]
            if len(prior_values) < min_prior_days:
                continue
            trailing = sum(prior_values) / len(prior_values)
            spend = by_date[current]
            if trailing > 0 and spend > threshold * trailing:
                rec = {
                    "date": current,
                    "cost_usd": round(spend, 4),
                    "trailing_avg_usd": round(trailing, 4),
                    "ratio": round(spend / trailing, 3),
                    "window_days": len(prior_values),
                    "threshold": threshold,
                }
                if group:
                    rec[group] = label
                rows.append(rec)
    out = pd.DataFrame(rows)
    if out.empty:
        cols = ["date", "cost_usd", "trailing_avg_usd", "ratio", "window_days", "threshold"]
        if group:
            cols.insert(1, group)
        return pd.DataFrame(columns=cols)
    return out.sort_values(["date"] + ([group] if group else [])).reset_index(drop=True)


def month_bounds(day: date) -> tuple[date, date]:
    last = monthrange(day.year, day.month)[1]
    return date(day.year, day.month, 1), date(day.year, day.month, last)


def forecast_month_end(
    usage: pd.DataFrame,
    *,
    as_of: date | str,
    month: date | None = None,
) -> dict:
    """Simple calendar run-rate forecast to month end.

    projected = spend_to_date + (spend_to_date / days_elapsed) * days_remaining

    Days with zero spend still count in the average, so a quiet Sunday
    pulls the daily rate down and a remaining Sunday is also counted.
    If `as_of` is the last day of the month, the forecast equals actual
    spend and `days_remaining` is 0.
    """
    as_of_d = _as_date(as_of)
    start, end = month_bounds(month or as_of_d)
    if as_of_d < start:
        raise ValueError("as_of is before the forecast month")
    as_of_clamped = min(as_of_d, end)

    if usage.empty:
        month_rows = usage
        spend_to_date = 0.0
    else:
        month_rows = filter_usage(usage, start=start, end=as_of_clamped)
        spend_to_date = float(month_rows["cost_usd"].sum()) if not month_rows.empty else 0.0

    days_in_month = (end - start).days + 1
    days_elapsed = (as_of_clamped - start).days + 1
    days_remaining = (end - as_of_clamped).days
    avg_daily = spend_to_date / days_elapsed if days_elapsed else 0.0
    projected = spend_to_date + avg_daily * days_remaining
    return {
        "month_start": start,
        "month_end": end,
        "as_of": as_of_clamped,
        "days_elapsed": days_elapsed,
        "days_remaining": days_remaining,
        "days_in_month": days_in_month,
        "spend_to_date": spend_to_date,
        "avg_daily_usd": avg_daily,
        "projected_month_usd": projected,
        "is_complete": days_remaining == 0,
    }


def showback_table(
    usage: pd.DataFrame,
    rates: pd.DataFrame,
    budgets: pd.DataFrame,
) -> pd.DataFrame:
    """Per-team showback / chargeback rows for the (already filtered) usage."""
    rate_map = {r["team"]: float(r["hourly_rate_usd"]) for _, r in rates.iterrows()}
    budget_map = {b["team"]: float(b["monthly_budget_usd"]) for _, b in budgets.iterrows()}

    if usage.empty:
        teams = list(rate_map.keys()) or list(budget_map.keys())
        records = []
        for team in teams:
            records.append(_empty_showback_row(team, rate_map.get(team, 0.0), budget_map.get(team, 0.0)))
        return pd.DataFrame(records)

    rows = []
    for team, part in usage.groupby("team"):
        spend = float(part["cost_usd"].sum())
        tasks = float(part["tasks_completed"].sum())
        hrs = hours_saved(part["minutes_saved"])
        rate = rate_map.get(team, 0.0)
        value = time_value(hrs, rate)
        budget = budget_map.get(team, 0.0)
        rows.append(
            {
                "team": team,
                "spend_usd": spend,
                "monthly_budget_usd": budget,
                "budget_used_pct": (spend / budget) if budget else None,
                "tasks": tasks,
                "cost_per_task_usd": cost_per_task(spend, tasks),
                "hours_saved": hrs,
                "hourly_rate_usd": rate,
                "time_value_usd": value,
                "net_value_usd": value - spend,
                "roi": roi(value, spend),
                "value_over_spend": value_over_spend(value, spend),
                "users": int(part["user"].nunique()),
            }
        )

    # Include teams with a budget but no usage in the period.
    seen = {r["team"] for r in rows}
    for team, budget in budget_map.items():
        if team not in seen:
            rows.append(_empty_showback_row(team, rate_map.get(team, 0.0), budget))

    frame = pd.DataFrame(rows)
    # Keep a stable department order when possible.
    order = {t: i for i, t in enumerate(rates["team"].tolist())} if "team" in rates.columns else {}
    frame["_ord"] = frame["team"].map(lambda t: order.get(t, 99))
    frame = frame.sort_values(["_ord", "team"]).drop(columns="_ord").reset_index(drop=True)
    return frame


def _empty_showback_row(team: str, rate: float, budget: float) -> dict:
    return {
        "team": team,
        "spend_usd": 0.0,
        "monthly_budget_usd": budget,
        "budget_used_pct": 0.0 if budget else None,
        "tasks": 0.0,
        "cost_per_task_usd": None,
        "hours_saved": 0.0,
        "hourly_rate_usd": rate,
        "time_value_usd": 0.0,
        "net_value_usd": 0.0,
        "roi": None,
        "value_over_spend": None,
        "users": 0,
    }


def totals(usage: pd.DataFrame, rates: pd.DataFrame, budgets: pd.DataFrame) -> dict:
    """Company-level totals for the filtered period."""
    table = showback_table(usage, rates, budgets)
    spend = float(table["spend_usd"].sum())
    value = float(table["time_value_usd"].sum())
    hours = float(table["hours_saved"].sum())
    tasks = float(table["tasks"].sum())
    budget = float(table["monthly_budget_usd"].sum())
    return {
        "spend_usd": spend,
        "time_value_usd": value,
        "net_value_usd": value - spend,
        "hours_saved": hours,
        "tasks": tasks,
        "cost_per_task_usd": cost_per_task(spend, tasks),
        "roi": roi(value, spend),
        "value_over_spend": value_over_spend(value, spend),
        "monthly_budget_usd": budget,
        "budget_used_pct": (spend / budget) if budget else None,
    }


def week_over_week_cost_per_task(
    usage: pd.DataFrame,
    *,
    as_of: date | str,
) -> pd.DataFrame:
    """Cost per task this week vs the prior week, by team.

    Weeks are the 7-day window ending on `as_of` and the 7 days before that.
    """
    as_of_d = _as_date(as_of)
    this_start = as_of_d - timedelta(days=6)
    prev_end = this_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=6)

    def cpt(frame: pd.DataFrame) -> dict[str, float | None]:
        out: dict[str, float | None] = {}
        if frame.empty:
            return out
        for team, part in frame.groupby("team"):
            out[team] = cost_per_task(float(part["cost_usd"].sum()), float(part["tasks_completed"].sum()))
        return out

    this = filter_usage(usage, start=this_start, end=as_of_d)
    prev = filter_usage(usage, start=prev_start, end=prev_end)
    this_map = cpt(this)
    prev_map = cpt(prev)
    teams = sorted(set(this_map) | set(prev_map))
    rows = []
    for team in teams:
        current = this_map.get(team)
        previous = prev_map.get(team)
        change = None
        if current is not None and previous not in (None, 0):
            change = (current - previous) / previous
        rows.append(
            {
                "team": team,
                "cost_per_task_this_week": current,
                "cost_per_task_prior_week": previous,
                "change_pct": change,
                "this_week_start": this_start,
                "this_week_end": as_of_d,
                "prior_week_start": prev_start,
                "prior_week_end": prev_end,
            }
        )
    return pd.DataFrame(rows)


def validate_usage_columns(columns: Iterable[str]) -> list[str]:
    present = set(columns)
    return [c for c in REQUIRED_USAGE_COLUMNS if c not in present]
