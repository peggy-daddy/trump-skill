#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch the latest Truth corpus and distill it into prompt-ready memory."
    )
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--skip-distill", action="store_true")
    parser.add_argument("--recent-days", type=int, default=30)
    parser.add_argument("--quotes-per-topic", type=int, default=3)
    return parser.parse_args()


def run_step(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    args = parse_args()

    if not args.skip_fetch:
        try:
            run_step([sys.executable, "scripts/fetch_truth_archive.py"])
        except subprocess.CalledProcessError:
            run_step([sys.executable, "scripts/fetch_truth_rss.py"])

    if not args.skip_distill:
        run_step(
            [
                sys.executable,
                "scripts/distill_truth_corpus.py",
                "--recent-days",
                str(args.recent_days),
                "--quotes-per-topic",
                str(args.quotes_per_topic),
            ]
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
