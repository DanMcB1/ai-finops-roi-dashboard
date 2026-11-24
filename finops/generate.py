"""Seeded sample-data generator for Lakeside Auto Group (sample).

The data is fictional. A few planned story beats are baked in so the
dashboard has something honest to say in the exec summary:

- Service is a high-volume, strong-ROI department (RO write-ups).
- F&I shifts toward the more expensive Advanced model after mid-November,
  so cost per task rises in the most recent week.
- Marketing has a campaign spike around 2026-11-18 (image + copy volume).
- Accounting is small and stable. Sales is steady volume. IT is moderate.
- Sunday is quiet (dealership pattern: sales may be open, back office off).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from finops.metrics import attach_costs
from finops.schema import (
    DEFAULT_PRICES,
    DEFAULT_SEED,
    SAMPLE_AS_OF,
    SAMPLE_START,
    TEAMS,
)

STORES = [
    "Lakeside Honda",
    "Westbrook Chevrolet",
    "Harbor CDJR",
    "Northlake Toyota",
    "Parkside Ford",
    "Summit Kia",
]

# Central teams are not on a store floor.
CENTRAL_TEAMS = {"Accounting", "Marketing", "IT / Support"}

USERS: dict[str, list[str]] = {
    "Sales": ["Jordan Hale", "Priya Shah", "Chris Nguyen", "Alex Rivera", "Sam Ortiz", "Nina Brooks"],
    "F&I": ["Morgan Blake", "Luis Ortega", "Taylor Quinn", "Dana Ruiz"],
    "Service": ["Casey Ward", "Nina Patel", "Omar Hassan", "Riley Brooks", "Jamie Cole", "Elena Vasquez"],
    "Accounting": ["Pat Kim", "Shawn Lee"],
    "Marketing": ["Avery Chen", "Jordan Miles", "Sky Ramirez"],
    "IT / Support": ["Robin Adeyemi", "Chris Park", "Mel Fontaine"],
}

# (use_case, tool, typical input tokens, output tokens, calls, minutes, tasks)
USE_CASES: dict[str, list[tuple[str, str, int, int, int, float, int]]] = {
    "Sales": [
        ("Lead follow-up email", "Northstar Chat — Standard", 700, 350, 1, 6.0, 1),
        ("Vehicle description", "Northstar Chat — Standard", 900, 450, 1, 8.0, 1),
        ("Appointment confirmation", "Northstar Chat — Standard", 400, 180, 1, 3.0, 1),
    ],
    "F&I": [
        ("Menu talk track", "Northstar Chat — Standard", 1200, 700, 1, 10.0, 1),
        ("Product explanation", "Northstar Chat — Standard", 900, 500, 1, 8.0, 1),
        ("Deal-jacket completeness check", "Northstar Chat — Standard", 1800, 400, 1, 12.0, 1),
    ],
    "Service": [
        ("Repair order write-up", "ServiceScribe", 1100, 500, 1, 11.0, 1),
        ("Appointment reminder", "Northstar Chat — Standard", 350, 160, 1, 3.0, 1),
        ("Concern / parts summary", "ServiceScribe", 800, 350, 1, 7.0, 1),
    ],
    "Accounting": [
        ("Invoice coding suggestion", "Ledger Mate", 600, 200, 1, 5.0, 1),
        ("AP email draft", "Ledger Mate", 500, 250, 1, 4.0, 1),
        ("Variance note", "Ledger Mate", 900, 350, 1, 8.0, 1),
    ],
    "Marketing": [
        ("Social post", "LotCopy", 500, 300, 1, 8.0, 1),
        ("Vehicle photo caption", "LotCopy", 400, 120, 1, 4.0, 1),
        ("Campaign landing copy", "LotCopy", 1400, 700, 1, 15.0, 1),
        ("Promo image", "ImageCraft", 0, 0, 1, 6.0, 1),
    ],
    "IT / Support": [
        ("Ticket summary", "TicketPilot", 800, 300, 1, 6.0, 1),
        ("Knowledge-base draft", "TicketPilot", 1500, 700, 1, 14.0, 1),
        ("Internal how-to", "TicketPilot", 1000, 500, 1, 10.0, 1),
    ],
}

# Typical weekday event counts by team (then jittered).
WEEKDAY_VOLUME = {
    "Sales": 38,
    "F&I": 20,
    "Service": 52,
    "Accounting": 9,
    "Marketing": 16,
    "IT / Support": 12,
}

# Planned story dates
FI_MODEL_SHIFT = date(2026, 11, 15)
MARKETING_SPIKE = date(2026, 11, 18)


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def _volume(team: str, day: date, rng: np.random.Generator) -> int:
    weekday = day.weekday()  # Mon=0 .. Sun=6
    base = WEEKDAY_VOLUME[team]

    if weekday == 6:  # Sunday
        if team in {"Accounting", "F&I", "IT / Support"}:
            return 0
        if team == "Service":
            return int(rng.integers(0, 2))  # almost closed
        if team == "Sales":
            return int(round(base * 0.45 * rng.uniform(0.8, 1.2)))
        if team == "Marketing":
            return int(rng.integers(0, 3))
    if weekday == 5:  # Saturday — stores busy, office light
        if team in {"Accounting", "IT / Support"}:
            return int(rng.integers(0, 2))
        if team in {"Sales", "Service", "F&I"}:
            base = int(round(base * 1.15))
    if weekday == 0:  # Monday — service write-ups pile up
        if team == "Service":
            base = int(round(base * 1.2))

    # Marketing campaign spike: 16–18 Nov 2026
    if team == "Marketing" and date(2026, 11, 16) <= day <= date(2026, 11, 18):
        if day == MARKETING_SPIKE:
            base = int(round(base * 4.6))
        else:
            base = int(round(base * 2.4))

    jitter = rng.normal(1.0, 0.12)
    return max(0, int(round(base * jitter)))


def _pick_tool(team: str, use_case_tool: str, day: date, rng: np.random.Generator) -> str:
    """Most teams stay on their default tool. F&I shifts to Advanced after 11/15."""
    if team == "F&I":
        p_advanced = 0.18 if day < FI_MODEL_SHIFT else 0.78
        if rng.random() < p_advanced:
            return "Northstar Chat — Advanced"
        return "Northstar Chat — Standard"
    if team == "Sales" and rng.random() < 0.08:
        return "Northstar Chat — Advanced"
    return use_case_tool


def _jitter_amount(base: int, rng: np.random.Generator, scale: float = 0.25) -> int:
    if base <= 0:
        return 0
    value = int(round(base * rng.uniform(1 - scale, 1 + scale)))
    return max(0, value)


def generate_usage(
    *,
    start: str | date = SAMPLE_START,
    end: str | date = SAMPLE_AS_OF,
    seed: int = DEFAULT_SEED,
    prices: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return a deterministic usage frame with computed costs."""
    start_d = pd.Timestamp(start).date()
    end_d = pd.Timestamp(end).date()
    rng = _rng(seed)
    records: list[dict[str, Any]] = []

    day = start_d
    while day <= end_d:
        for team in TEAMS:
            n = _volume(team, day, rng)
            users = USERS[team]
            cases = USE_CASES[team]
            for _ in range(n):
                user = str(rng.choice(users))
                case = cases[int(rng.integers(0, len(cases)))]
                use_case, default_tool, in_tok, out_tok, calls, minutes, tasks = case
                # Bias Marketing spike toward images and campaign copy
                if team == "Marketing" and day == MARKETING_SPIKE:
                    if rng.random() < 0.55:
                        use_case, default_tool, in_tok, out_tok, calls, minutes, tasks = USE_CASES["Marketing"][3]
                    elif rng.random() < 0.5:
                        use_case, default_tool, in_tok, out_tok, calls, minutes, tasks = USE_CASES["Marketing"][2]
                tool = _pick_tool(team, default_tool, day, rng)
                store = "Group office (central)" if team in CENTRAL_TEAMS else str(rng.choice(STORES))
                rec_calls = _jitter_amount(calls, rng, 0.0) if default_tool != "ImageCraft" else int(rng.integers(1, 4))
                if tool == "ImageCraft":
                    rec_calls = int(rng.integers(1, 5)) if day == MARKETING_SPIKE else rec_calls or 1
                records.append(
                    {
                        "date": day.isoformat(),
                        "team": team,
                        "store": store,
                        "user": user,
                        "tool_model": tool,
                        "use_case": use_case,
                        "input_tokens": _jitter_amount(in_tok, rng),
                        "output_tokens": _jitter_amount(out_tok, rng),
                        "api_calls": rec_calls,
                        "tasks_completed": tasks,
                        "minutes_saved": round(max(1.0, minutes * float(rng.uniform(0.8, 1.2))), 1),
                    }
                )
        day += timedelta(days=1)

    frame = pd.DataFrame.from_records(records)
    frame = attach_costs(frame, prices if prices is not None else DEFAULT_PRICES, overwrite=True)
    # Stable column order
    cols = [
        "date",
        "team",
        "store",
        "user",
        "tool_model",
        "use_case",
        "input_tokens",
        "output_tokens",
        "api_calls",
        "cost_usd",
        "tasks_completed",
        "minutes_saved",
    ]
    return frame[cols]


def default_rates() -> pd.DataFrame:
    from finops.schema import DEFAULT_RATES

    return DEFAULT_RATES.copy()


def default_budgets() -> pd.DataFrame:
    from finops.schema import DEFAULT_BUDGETS

    return DEFAULT_BUDGETS.copy()


def default_prices() -> pd.DataFrame:
    return DEFAULT_PRICES.copy()
