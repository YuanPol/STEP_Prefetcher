#!/usr/bin/env python3
"""
Batch collector to regenerate the standard metrics CSVs.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent


TASKS: List[Dict[str, object]] = [
    {"label": "single_core_l1", "filename": "single_core_results.csv", "log_subdir": Path("l1/l1_level")},
    {"label": "single_core_l2", "filename": "single_core_l2_results.csv", "log_subdir": Path("l2/single_core_performance")},
    {
        "label": "multi_level",
        "filename": "multi_level_prefetching_results.csv",
        "log_subdir": Path("l2/multi_level_prefetching"),
        "baseline_subdir": Path("l2/single_core_performance"),
    },
    {
        "label": "storage",
        "filename": "storage_sensitivity_results.csv",
        "log_subdir": Path("l2/storage_sensitivity"),
        "baseline_subdir": Path("l2/single_core_performance"),
    },
    {
        "label": "parameter",
        "filename": "parameter_sweep_results.csv",
        "log_subdir": Path("l2/parameter_sweep"),
        "baseline_subdir": Path("l2/single_core_performance"),
    },
    {
        "label": "ablation",
        "filename": "ablation_results.csv",
        "log_subdir": Path("l2/ablation_experiment"),
        "baseline_subdir": Path("l2/single_core_performance"),
    },
    {
        "label": "limited_way",
        "filename": "limited_way_1way_results.csv",
        "log_subdir": Path("l2/limited_way_experiment/ways_1"),
        "baseline_subdir": Path("l2/single_core_performance"),
    },
    {
        "label": "system",
        "filename": "system_sensitivity_results.csv",
        "log_subdir": Path("l2/system_parameter_experiment"),
    },
    {"label": "two_core_homo", "filename": "two_core_l2_results.csv", "log_subdir": Path("multicore/homo/2core_l2")},
    {"label": "four_core_homo", "filename": "four_core_l2_results.csv", "log_subdir": Path("multicore/homo/4core_l2")},
    {"label": "eight_core_homo", "filename": "eight_core_l2_results.csv", "log_subdir": Path("multicore/homo/8core_l2")},
    {"label": "two_core_heter", "filename": "two_core_l2_heter_results.csv", "log_subdir": Path("multicore/heter/2core_l2")},
    {"label": "four_core_heter", "filename": "four_core_l2_heter_results.csv", "log_subdir": Path("multicore/heter/4core_l2")},
    {"label": "eight_core_heter", "filename": "eight_core_l2_heter_results.csv", "log_subdir": Path("multicore/heter/8core_l2")},
]


def run_collect(
    *,
    log_root: Path,
    baseline: str,
    output: Path,
    json_root: Optional[Path] = None,
    baseline_log_root: Optional[Path] = None,
    baseline_json_root: Optional[Path] = None,
) -> int:
    cmd: List[str] = [
        sys.executable,
        str(SCRIPT_DIR / "collect_metrics.py"),
        "--log-root",
        str(log_root),
        "--baseline",
        baseline,
        "--output",
        str(output),
    ]
    if json_root and json_root.exists():
        cmd.extend(["--json-root", str(json_root)])
    if baseline_log_root and baseline_log_root.exists():
        cmd.extend(["--baseline-log-root", str(baseline_log_root)])
    if baseline_json_root and baseline_json_root.exists():
        cmd.extend(["--baseline-json-root", str(baseline_json_root)])

    print(f"[collect-all] Running: {' '.join(cmd)}", file=sys.stderr)
    return subprocess.call(cmd)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Collect all standard metrics CSVs.")
    parser.add_argument("--warmup", type=int, default=50_000_000, help="Warmup instructions.")
    parser.add_argument("--simulation", type=int, default=100_000_000, help="Simulation instructions.")
    parser.add_argument("--baseline", default="no", help="Baseline prefetcher name.")
    parser.add_argument("--log-base", type=Path, default=REPO_ROOT / "log", help="Base log directory.")
    parser.add_argument("--json-base", type=Path, default=REPO_ROOT / "json", help="Base JSON directory.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=SCRIPT_DIR / "results",
        help="Directory to write metrics CSVs.",
    )
    args = parser.parse_args(argv)

    warm = args.warmup
    sim = args.simulation
    status = 0
    suffix = Path(f"withwarm_{warm}_withsim_{sim}")
    tasks = list(TASKS)

    for task in tasks:
        log_root = args.log_base / task["log_subdir"] / suffix
        json_root = args.json_base / task["log_subdir"] / suffix
        output = args.output_dir / str(task["filename"])

        baseline_log_root = None
        baseline_json_root = None
        baseline_subdir = task.get("baseline_subdir")
        if baseline_subdir:
            baseline_log_root = args.log_base / baseline_subdir / suffix
            baseline_json_root = args.json_base / baseline_subdir / suffix

        ret = run_collect(
            log_root=log_root,
            json_root=json_root,
            baseline=args.baseline,
            output=output,
            baseline_log_root=baseline_log_root,
            baseline_json_root=baseline_json_root,
        )
        if ret != 0:
            print(f"[collect-all] FAILED for {task['label']} (exit {ret})", file=sys.stderr)
            status = ret

    return status


if __name__ == "__main__":
    raise SystemExit(main())
