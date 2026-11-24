"""Unit tests for cost, ROI, anomaly, forecast, and showback math."""

from __future__ import annotations

import io
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from finops.generate import default_budgets, default_prices, default_rates, generate_usage
from finops.io import UsageSchemaError, normalize_usage, save_usage_csv
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
    totals,
    week_over_week_cost_per_task,
)
from finops.schema import SAMPLE_AS_OF
from finops.summary import exec_summary

ROOT = Path(__file__).resolve().parents[1]


def _usage(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def _row(**kwargs) -> dict:
    base = {
        "date": "2026-11-10",
        "team": "Service",
        "user": "Casey Ward",
        "tool_model": "ServiceScribe",
        "use_case": "Repair order write-up",
        "input_tokens": 1000,
        "output_tokens": 400,
        "api_calls": 1,
        "tasks_completed": 1,
        "minutes_saved": 10,
    }
    base.update(kwargs)
    return base


class CostTests(unittest.TestCase):
    def test_compute_cost_tokens_and_calls(self):
        # 2M input * $3 + 1M output * $10 + 4 calls * $0.50 = 6 + 10 + 2 = 18
        self.assertAlmostEqual(
            compute_cost(2_000_000, 1_000_000, 4, 3.0, 10.0, 0.50),
            18.0,
        )

    def test_compute_cost_handles_zeros_and_nan(self):
        self.assertEqual(compute_cost(0, 0, 0, 10, 20, 0), 0.0)
        self.assertAlmostEqual(compute_cost(float("nan"), 0, 2, 0, 0, 1.5), 3.0)

    def test_attach_costs_matches_formula(self):
        prices = default_prices()
        usage = _usage(_row(input_tokens=1_000_000, output_tokens=1_000_000, api_calls=2))
        out = attach_costs(usage, prices)
        price = prices.set_index("tool_model").loc["ServiceScribe"]
        expected = compute_cost(
            1_000_000,
            1_000_000,
            2,
            price.input_usd_per_m_tokens,
            price.output_usd_per_m_tokens,
            price.usd_per_call,
        )
        self.assertAlmostEqual(float(out.loc[0, "cost_usd"]), expected)

    def test_attach_costs_keeps_existing_when_not_overwriting(self):
        prices = default_prices()
        usage = _usage(_row())
        usage["cost_usd"] = 99.0
        kept = attach_costs(usage, prices, overwrite=False)
        self.assertEqual(float(kept.loc[0, "cost_usd"]), 99.0)
        overwritten = attach_costs(usage, prices, overwrite=True)
        self.assertNotAlmostEqual(float(overwritten.loc[0, "cost_usd"]), 99.0)


class RoiTests(unittest.TestCase):
    def test_hours_and_time_value(self):
        self.assertAlmostEqual(hours_saved(pd.Series([30, 30, 60])), 2.0)
        self.assertAlmostEqual(hours_saved(90), 1.5)
        self.assertAlmostEqual(time_value(2.0, 50.0), 100.0)

    def test_roi_formula(self):
        self.assertAlmostEqual(roi(150, 50), 2.0)  # (150-50)/50
        self.assertAlmostEqual(roi(20, 50), -0.6)
        self.assertIsNone(roi(100, 0))

    def test_cost_per_task(self):
        self.assertAlmostEqual(cost_per_task(10, 4), 2.5)
        self.assertIsNone(cost_per_task(10, 0))


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.usage = attach_costs(
            _usage(
                _row(date="2026-11-01", team="Sales", tool_model="Northstar Chat — Standard"),
                _row(date="2026-11-10", team="Service", tool_model="ServiceScribe"),
                _row(date="2026-11-20", team="F&I", tool_model="Northstar Chat — Advanced"),
            ),
            default_prices(),
        )

    def test_filter_by_date_team_model(self):
        out = filter_usage(self.usage, start="2026-11-05", end="2026-11-20", teams=["Service", "F&I"])
        self.assertEqual(set(out["team"]), {"Service", "F&I"})
        out2 = filter_usage(self.usage, models=["ServiceScribe"])
        self.assertEqual(list(out2["team"]), ["Service"])


class AnomalyTests(unittest.TestCase):
    def _days(self, amounts: list[tuple[str, float]]) -> pd.DataFrame:
        rows = []
        for day, amount in amounts:
            rows.append(_row(date=day, cost_usd=amount, input_tokens=0, output_tokens=0, api_calls=0))
        return pd.DataFrame(rows)

    def test_flags_day_over_2x_trailing_average(self):
        # 7 days at $10, then a $25 day (2.5x)
        days = [(f"2026-11-{i:02d}", 10.0) for i in range(1, 8)] + [("2026-11-08", 25.0)]
        flagged = detect_anomalies(self._days(days), window=7, threshold=2.0, min_prior_days=5)
        self.assertEqual(list(flagged["date"]), [date(2026, 11, 8)])
        self.assertAlmostEqual(float(flagged.loc[0, "trailing_avg_usd"]), 10.0)
        self.assertAlmostEqual(float(flagged.loc[0, "ratio"]), 2.5)

    def test_does_not_flag_1_5x_day(self):
        days = [(f"2026-11-{i:02d}", 10.0) for i in range(1, 8)] + [("2026-11-08", 15.0)]
        flagged = detect_anomalies(self._days(days), window=7, threshold=2.0, min_prior_days=5)
        self.assertTrue(flagged.empty)

    def test_ignores_first_days_without_enough_history(self):
        days = [("2026-11-01", 5.0), ("2026-11-02", 50.0)]
        flagged = detect_anomalies(self._days(days), window=7, threshold=2.0, min_prior_days=5)
        self.assertTrue(flagged.empty)

    def test_team_level_isolation(self):
        rows = []
        for i in range(1, 8):
            rows.append(_row(date=f"2026-11-{i:02d}", team="Sales", cost_usd=10.0))
            rows.append(_row(date=f"2026-11-{i:02d}", team="Marketing", cost_usd=10.0))
        rows.append(_row(date="2026-11-08", team="Sales", cost_usd=10.0))
        rows.append(_row(date="2026-11-08", team="Marketing", cost_usd=40.0))
        flagged = detect_anomalies(pd.DataFrame(rows), group="team", window=7, threshold=2.0)
        self.assertEqual(list(flagged["team"]), ["Marketing"])
        self.assertAlmostEqual(float(flagged.loc[0, "ratio"]), 4.0)


class ForecastTests(unittest.TestCase):
    def test_run_rate_math(self):
        # Nov 1–10 spend $100/day = $1,000. As of Nov 10, 20 days remain.
        rows = [_row(date=f"2026-11-{i:02d}", cost_usd=100.0) for i in range(1, 11)]
        usage = pd.DataFrame(rows)
        result = forecast_month_end(usage, as_of=date(2026, 11, 10))
        self.assertEqual(result["days_elapsed"], 10)
        self.assertEqual(result["days_remaining"], 20)
        self.assertEqual(result["days_in_month"], 30)
        self.assertAlmostEqual(result["spend_to_date"], 1000.0)
        self.assertAlmostEqual(result["avg_daily_usd"], 100.0)
        self.assertAlmostEqual(result["projected_month_usd"], 3000.0)
        self.assertFalse(result["is_complete"])

    def test_complete_month_equals_actual(self):
        rows = [_row(date="2026-10-15", cost_usd=500.0)]
        result = forecast_month_end(pd.DataFrame(rows), as_of=date(2026, 10, 31))
        self.assertTrue(result["is_complete"])
        self.assertEqual(result["days_remaining"], 0)
        self.assertAlmostEqual(result["projected_month_usd"], 500.0)


class ShowbackTests(unittest.TestCase):
    def test_showback_and_totals(self):
        usage = attach_costs(
            _usage(
                _row(team="Service", minutes_saved=120, tasks_completed=4, tool_model="ServiceScribe"),
                _row(team="F&I", minutes_saved=60, tasks_completed=2, tool_model="Northstar Chat — Standard"),
            ),
            default_prices(),
        )
        table = showback_table(usage, default_rates(), default_budgets())
        self.assertIn("Service", set(table["team"]))
        service = table.set_index("team").loc["Service"]
        self.assertAlmostEqual(service["hours_saved"], 2.0)
        self.assertAlmostEqual(service["hourly_rate_usd"], 50.0)
        self.assertAlmostEqual(service["time_value_usd"], 100.0)
        self.assertAlmostEqual(service["net_value_usd"], 100.0 - service["spend_usd"])
        self.assertAlmostEqual(service["cost_per_task_usd"], service["spend_usd"] / 4)
        agg = totals(usage, default_rates(), default_budgets())
        self.assertAlmostEqual(agg["hours_saved"], 3.0)
        self.assertAlmostEqual(agg["monthly_budget_usd"], 12000.0)

    def test_wow_cost_per_task_change(self):
        rows = []
        # Prior week Nov 11–17: F&I spend $10, 10 tasks -> $1/task
        # This week Nov 18–24: spend $30, 10 tasks -> $3/task, +200%
        for i in range(11, 18):
            rows.append(_row(date=f"2026-11-{i:02d}", team="F&I", cost_usd=10 / 7, tasks_completed=10 / 7))
        for i in range(18, 25):
            rows.append(_row(date=f"2026-11-{i:02d}", team="F&I", cost_usd=30 / 7, tasks_completed=10 / 7))
        wow = week_over_week_cost_per_task(pd.DataFrame(rows), as_of=date(2026, 11, 24))
        fi = wow.set_index("team").loc["F&I"]
        self.assertAlmostEqual(fi["cost_per_task_prior_week"], 1.0, places=6)
        self.assertAlmostEqual(fi["cost_per_task_this_week"], 3.0, places=6)
        self.assertAlmostEqual(fi["change_pct"], 2.0, places=6)


class SampleDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.usage = generate_usage(seed=9)

    def test_deterministic(self):
        again = generate_usage(seed=9)
        pd.testing.assert_frame_equal(self.usage, again)

    def test_schema_and_positive_spend(self):
        self.assertGreater(len(self.usage), 1000)
        self.assertGreater(float(self.usage["cost_usd"].sum()), 1000)
        self.assertTrue((self.usage["cost_usd"] >= 0).all())
        self.assertEqual(set(self.usage["team"]), set(default_rates()["team"]))

    def test_marketing_spike_is_flagged(self):
        nov = filter_usage(self.usage, start="2026-11-01", end="2026-11-24")
        flags = detect_anomalies(nov, group="team")
        marketing = flags[flags["team"] == "Marketing"]
        self.assertFalse(marketing.empty)
        self.assertTrue((marketing["date"] == date(2026, 11, 18)).any())
        spike = marketing.set_index("date").loc[date(2026, 11, 18)]
        if isinstance(spike, pd.DataFrame):
            spike = spike.iloc[0]
        self.assertGreater(float(spike["ratio"]), 2.0)

    def test_fi_cost_per_task_rose_after_model_shift(self):
        nov = filter_usage(self.usage, start="2026-11-01", end="2026-11-24")
        wow = week_over_week_cost_per_task(nov, as_of=date(2026, 11, 24))
        fi = wow.set_index("team").loc["F&I"]
        self.assertIsNotNone(fi["change_pct"])
        self.assertGreater(fi["change_pct"], 0.15)

    def test_exec_summary_covers_story_beats(self):
        nov = filter_usage(self.usage, start="2026-11-01", end="2026-11-24")
        lines = exec_summary(
            nov,
            default_rates(),
            default_budgets(),
            as_of=date.fromisoformat(SAMPLE_AS_OF),
            period_start="2026-11-01",
            period_end="2026-11-24",
        )
        text = " ".join(lines)
        self.assertIn("Service", text)
        self.assertIn("F&I", text)
        self.assertIn("Marketing", text)
        self.assertIn("Nov 18, 2026", text)
        self.assertIn("Forecast", text)
        self.assertIn("sample data", text.lower())

    def test_uploaded_csv_roundtrip_and_schema_error(self):
        path = ROOT / "data" / "_tmp_roundtrip.csv"
        try:
            save_usage_csv(self.usage.head(20), path)
            loaded = normalize_usage(pd.read_csv(path), prices=default_prices(), recalculate_cost=True)
            self.assertEqual(len(loaded), 20)
        finally:
            if path.exists():
                path.unlink()
        with self.assertRaises(UsageSchemaError):
            normalize_usage(pd.DataFrame({"date": ["2026-11-01"], "team": ["Sales"]}))


if __name__ == "__main__":
    unittest.main()
