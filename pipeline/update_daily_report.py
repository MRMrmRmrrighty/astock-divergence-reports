#!/usr/bin/env python3
"""A股底背离多因子报告云端更新流水线。

用法：
  python pipeline/update_daily_report.py [--date YYYY-MM-DD] [--skip-fetch]

不传 --date 时使用最新工作日；GitHub Actions 在北京时间 17:35 运行。
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

PIPELINE = Path(__file__).resolve().parent
ROOT = PIPELINE.parent
WORK = ROOT / "work"
OUT = ROOT / "outputs"
HISTORY = PIPELINE / "history"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("daily-update")


def latest_completed_trade_date() -> str:
    d = dt.date.today()
    if d.weekday() >= 5:
        d -= dt.timedelta(days=d.weekday() - 4)
    return d.isoformat()


def previous_weekday(d: dt.date) -> str:
    d -= dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d.isoformat()


def ensure_dirs() -> None:
    (WORK / "cache").mkdir(parents=True, exist_ok=True)
    (WORK / "mpl").mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    HISTORY.mkdir(parents=True, exist_ok=True)


def run_script(script: str, replacements: dict[str, str]) -> None:
    src = PIPELINE / script
    target = PIPELINE / f".tmp_{script}"
    text = src.read_text(encoding="utf-8")
    for key, value in replacements.items():
        text = text.replace(key, value)
    target.write_text(text, encoding="utf-8")
    log.info("Running %s ...", script)
    result = subprocess.run(
        [sys.executable, str(target)],
        cwd=str(WORK),
        env={**os.environ, "PYTHONPATH": str(PIPELINE) + os.pathsep + os.environ.get("PYTHONPATH", ""), "MPLBACKEND": "Agg", "MPLCONFIGDIR": str(WORK / "mpl")},
        text=True,
    )
    target.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(f"{script} failed with exit code {result.returncode}")


def infer_actual_dates(requested: str, raw_path: Path) -> tuple[str, str]:
    """Use the latest date actually present in the fetched K-line data."""
    raw = pd.read_csv(raw_path, dtype={"code": str})
    dates = sorted(set(raw["latest_date"].dropna().astype(str)))
    if not dates:
        raise RuntimeError("no latest_date values in screened result")
    eligible = [d for d in dates if d <= requested]
    actual = eligible[-1] if eligible else dates[-1]
    before = [d for d in dates if d < actual]
    previous = before[-1] if before else previous_weekday(dt.date.fromisoformat(actual))
    if actual != requested:
        log.warning("No K line for %s; using latest completed trade date %s", requested, actual)
    return actual, previous


def copy_history(multifactor_path: Path, actual: str) -> None:
    target = HISTORY / f"A股底背离推荐等级排序_多因子_数据至{actual}.csv"
    shutil.copy2(multifactor_path, target)
    log.info("Saved history dataset %s", target.name)


def count_update_errors(path: Path) -> int:
    if not path.exists() or path.stat().st_size < 5:
        return 0
    return int(len(pd.read_csv(path)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="trade date, YYYY-MM-DD")
    parser.add_argument("--skip-fetch", action="store_true", help="debug: reuse an existing cache")
    args = parser.parse_args()
    requested = args.date or latest_completed_trade_date()
    nd = requested.replace("-", "")
    ensure_dirs()

    if not args.skip_fetch:
        run_script("update_cache.py", {"__TARGET_DATE__": requested, "__TARGET_ND__": nd})
        errors = count_update_errors(WORK / f"errors_update_{nd}.csv")
        if errors > 1200:
            raise RuntimeError(f"too many cache update errors: {errors}")

    run_script(
        "run_screen.py",
        {"__TARGET_DATE__": requested, "__TARGET_ND__": nd},
    )
    raw_path = WORK / f"all_bottom_divergence_raw_{nd}.csv"
    if not raw_path.exists() or raw_path.stat().st_size < 100:
        raise RuntimeError(f"screen result was not created: {raw_path}")

    actual, previous = infer_actual_dates(requested, raw_path)
    if actual != requested:
        nd = actual.replace("-", "")
    replacements = {
        "__TARGET_DATE__": actual,
        "__TARGET_ND__": nd,
        "__PREV_DATE__": previous,
    }
    log.info("Effective report date: %s; fallback valuation date: %s", actual, previous)
    run_script("multifactor.py", replacements)

    multifactor_path = OUT / f"A股底背离推荐等级排序_多因子_数据至{actual}.csv"
    if not multifactor_path.exists():
        raise RuntimeError(f"multifactor result was not created: {multifactor_path}")
    copy_history(multifactor_path, actual)

    run_script("build_report.py", replacements)
    run_script("build_trends.py", {})
    run_script("build_site.py", {})
    log.info("Daily update completed for %s", actual)


if __name__ == "__main__":
    main()
