"""Shared schema, default rates, budgets, and illustrative prices.

Prices and loaded hourly rates are *assumptions for this demo*, not live
vendor list prices and not a real payroll file.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PACKAGE_ROOT / "data"

REQUIRED_USAGE_COLUMNS = [
    "date",
    "team",
    "user",
    "tool_model",
    "use_case",
    "input_tokens",
    "output_tokens",
    "api_calls",
    "tasks_completed",
    "minutes_saved",
]

OPTIONAL_USAGE_COLUMNS = ["store", "cost_usd"]

ALL_USAGE_COLUMNS = REQUIRED_USAGE_COLUMNS + OPTIONAL_USAGE_COLUMNS

TEAMS = [
    "Sales",
    "F&I",
    "Service",
    "Accounting",
    "Marketing",
    "IT / Support",
]

# Loaded hourly rates: salary + benefits + overhead, illustrative only.
DEFAULT_RATES = pd.DataFrame(
    [
        {"team": "Sales", "hourly_rate_usd": 45.0, "notes": "Loaded rate assumption (sales consultants)"},
        {"team": "F&I", "hourly_rate_usd": 65.0, "notes": "Loaded rate assumption (F&I managers)"},
        {"team": "Service", "hourly_rate_usd": 50.0, "notes": "Loaded rate assumption (service advisors)"},
        {"team": "Accounting", "hourly_rate_usd": 40.0, "notes": "Loaded rate assumption"},
        {"team": "Marketing", "hourly_rate_usd": 42.0, "notes": "Loaded rate assumption"},
        {"team": "IT / Support", "hourly_rate_usd": 55.0, "notes": "Loaded rate assumption"},
    ]
)

# Monthly AI budget by team, illustrative.
DEFAULT_BUDGETS = pd.DataFrame(
    [
        {"team": "Sales", "monthly_budget_usd": 2500.0},
        {"team": "F&I", "monthly_budget_usd": 2200.0},
        {"team": "Service", "monthly_budget_usd": 3000.0},
        {"team": "Accounting", "monthly_budget_usd": 800.0},
        {"team": "Marketing", "monthly_budget_usd": 2000.0},
        {"team": "IT / Support", "monthly_budget_usd": 1500.0},
    ]
)

# Fictional tools with illustrative unit prices — not live vendor pricing.
# Fully loaded *illustrative* unit costs: a small token component plus
# an allocated per-call (or per-image) platform share. These are not a
# vendor price list. Edit them in the app and the dashboard recalculates.
DEFAULT_PRICES = pd.DataFrame(
    [
        {
            "tool_model": "Northstar Chat — Standard",
            "input_usd_per_m_tokens": 15.0,
            "output_usd_per_m_tokens": 60.0,
            "usd_per_call": 2.15,
            "notes": "Illustrative fully loaded cost (API + allocated platform), not a vendor list price",
        },
        {
            "tool_model": "Northstar Chat — Advanced",
            "input_usd_per_m_tokens": 50.0,
            "output_usd_per_m_tokens": 200.0,
            "usd_per_call": 5.40,
            "notes": "Illustrative fully loaded cost for the premium tier",
        },
        {
            "tool_model": "ServiceScribe",
            "input_usd_per_m_tokens": 18.0,
            "output_usd_per_m_tokens": 70.0,
            "usd_per_call": 2.65,
            "notes": "Illustrative fully loaded cost for RO write-up assistance",
        },
        {
            "tool_model": "LotCopy",
            "input_usd_per_m_tokens": 15.0,
            "output_usd_per_m_tokens": 60.0,
            "usd_per_call": 2.05,
            "notes": "Illustrative fully loaded cost for marketing copy",
        },
        {
            "tool_model": "ImageCraft",
            "input_usd_per_m_tokens": 0.0,
            "output_usd_per_m_tokens": 0.0,
            "usd_per_call": 2.40,
            "notes": "Illustrative fully loaded cost per generated image",
        },
        {
            "tool_model": "Ledger Mate",
            "input_usd_per_m_tokens": 12.0,
            "output_usd_per_m_tokens": 48.0,
            "usd_per_call": 1.85,
            "notes": "Illustrative fully loaded cost for accounting assistance",
        },
        {
            "tool_model": "TicketPilot",
            "input_usd_per_m_tokens": 15.0,
            "output_usd_per_m_tokens": 60.0,
            "usd_per_call": 2.25,
            "notes": "Illustrative fully loaded cost for support assistance",
        },
    ]
)

SAMPLE_COMPANY = "Lakeside Auto Group (sample)"
SAMPLE_AS_OF = "2026-11-24"
SAMPLE_START = "2026-09-01"
DEFAULT_SEED = 9

PRICE_NOTE = (
    "All model prices (including the per-call platform share) and loaded hourly rates in this demo are illustrative "
    "assumptions, not live vendor pricing and not a real payroll file."
)
