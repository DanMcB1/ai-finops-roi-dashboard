"""Department-Level FinOps & ROI Dashboard — portfolio demo."""

__version__ = "1.0.0"

from finops.metrics import (
    attach_costs,
    compute_cost,
    cost_per_task,
    detect_anomalies,
    filter_usage,
    forecast_month_end,
    hours_saved,
    roi,
    showback_table,
    time_value,
)
from finops.summary import exec_summary

__all__ = [
    "attach_costs",
    "compute_cost",
    "cost_per_task",
    "detect_anomalies",
    "exec_summary",
    "filter_usage",
    "forecast_month_end",
    "hours_saved",
    "roi",
    "showback_table",
    "time_value",
    "__version__",
]
