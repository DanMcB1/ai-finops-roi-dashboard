"""CLI helpers: generate sample data or print a summary.

  python -m finops generate --out data/sample_usage.csv
  python -m finops summary --start 2026-11-01 --end 2026-11-24
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from finops.generate import default_budgets, default_prices, default_rates, generate_usage
from finops.io import load_usage_csv, sample_usage_path, save_usage_csv
from finops.schema import DATA_DIR, DEFAULT_SEED, SAMPLE_AS_OF, SAMPLE_START
from finops.summary import exec_summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FinOps ROI dashboard utilities (portfolio demo).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    gen = sub.add_parser("generate", help="Write the seeded sample usage CSV")
    gen.add_argument("--out", default=str(sample_usage_path()))
    gen.add_argument("--start", default=SAMPLE_START)
    gen.add_argument("--end", default=SAMPLE_AS_OF)
    gen.add_argument("--seed", type=int, default=DEFAULT_SEED)

    sm = sub.add_parser("summary", help="Print the exec summary for a usage CSV")
    sm.add_argument("--usage", default=str(sample_usage_path()))
    sm.add_argument("--start", default=None)
    sm.add_argument("--end", default=None)

    args = parser.parse_args(argv)

    if args.cmd == "generate":
        frame = generate_usage(start=args.start, end=args.end, seed=args.seed)
        path = save_usage_csv(frame, args.out)
        spend = float(frame["cost_usd"].sum())
        print(f"Wrote {path} ({len(frame):,} rows, ${spend:,.2f} total illustrative spend).")
        # Also write default lookup tables next to it when writing into data/
        out_dir = Path(args.out).parent
        if out_dir.resolve() == DATA_DIR.resolve():
            default_prices().to_csv(DATA_DIR / "sample_prices.csv", index=False)
            default_rates().to_csv(DATA_DIR / "sample_rates.csv", index=False)
            default_budgets().to_csv(DATA_DIR / "sample_budgets.csv", index=False)
            print(f"Wrote price, rate, and budget tables in {DATA_DIR}")
        return 0

    usage = load_usage_csv(args.usage)
    dates = sorted(usage["date"].unique())
    start = args.start or dates[0]
    end = args.end or dates[-1]
    from finops.metrics import filter_usage

    filtered = filter_usage(usage, start=start, end=end)
    lines = exec_summary(
        filtered,
        default_rates(),
        default_budgets(),
        as_of=date.fromisoformat(str(end)),
        period_start=start,
        period_end=end,
    )
    for line in lines:
        print(f"- {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
