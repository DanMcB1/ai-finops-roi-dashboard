"""Load, validate, and save usage CSVs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from finops.metrics import attach_costs, validate_usage_columns
from finops.schema import DATA_DIR, DEFAULT_PRICES


class UsageSchemaError(ValueError):
    pass


def load_usage_csv(
    path: str | Path,
    *,
    prices: pd.DataFrame | None = None,
    recalculate_cost: bool = False,
) -> pd.DataFrame:
    path = Path(path)
    frame = pd.read_csv(path)
    return normalize_usage(frame, prices=prices, recalculate_cost=recalculate_cost)


def normalize_usage(
    frame: pd.DataFrame,
    *,
    prices: pd.DataFrame | None = None,
    recalculate_cost: bool = False,
) -> pd.DataFrame:
    missing = validate_usage_columns(frame.columns)
    if missing:
        raise UsageSchemaError(
            "CSV is missing required columns: "
            + ", ".join(missing)
            + ". Expected at least: date, team, user, tool_model, use_case, "
            "input_tokens, output_tokens, api_calls, tasks_completed, minutes_saved. "
            "Optional: store, cost_usd."
        )
    out = frame.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
    if out["date"].isna().any():
        bad = int(out["date"].isna().sum())
        raise UsageSchemaError(f"{bad} row(s) have a date that could not be parsed.")
    numeric = ["input_tokens", "output_tokens", "api_calls", "tasks_completed", "minutes_saved"]
    if "cost_usd" in out.columns:
        numeric.append("cost_usd")
    for col in numeric:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0)
    if "store" not in out.columns:
        out["store"] = ""
    has_cost = "cost_usd" in frame.columns
    out = attach_costs(
        out,
        prices if prices is not None else DEFAULT_PRICES,
        overwrite=recalculate_cost or not has_cost,
    )
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    return out.reset_index(drop=True)


def save_usage_csv(frame: pd.DataFrame, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return path


def sample_usage_path() -> Path:
    return DATA_DIR / "sample_usage.csv"
