"""CLI for validating pilot scoring and exports with synthetic test vectors only."""

import argparse
import os
import sys
from pathlib import Path

from pilot_study import DRY_RUN_LABEL, write_dry_run_outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export a clearly labeled synthetic pilot dry run.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=Path("pilot_dry_runs"))
    args = parser.parse_args(argv)

    if os.environ.get("PILOT_DRY_RUN", "").casefold() != "true":
        print("Set PILOT_DRY_RUN=true to generate synthetic validation files.", file=sys.stderr)
        return 2

    json_path, csv_path = write_dry_run_outputs(args.output_dir, args.seed)
    print(DRY_RUN_LABEL)
    print("Synthetic scoring/export fixtures only; no participant responses or findings.")
    print(f"JSON: {json_path}")
    print(f"CSV: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
