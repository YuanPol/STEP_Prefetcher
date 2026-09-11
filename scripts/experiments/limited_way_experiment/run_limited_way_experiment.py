#!/usr/bin/env python3
"""
Single-core limited-way L2 experiment launcher.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Mapping, Optional

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = SCRIPT_DIR.parent
SCRIPTS_ROOT = REPO_ROOT / "scripts"
RUN_DIR = SCRIPTS_ROOT / "run"
EXPERIMENTS_DIR = SCRIPTS_ROOT / "experiments"
for path in (SCRIPTS_ROOT, RUN_DIR, EXPERIMENTS_DIR):
    if str(path) not in sys.path:
        sys.path.append(str(path))

from experiment_utils import single_core_result_roots, step_trace_dir  # noqa: E402
from single_core_queue import prepare_single_core_tasks, run_single_core_task_queue  # noqa: E402
from workloads import workloads_all  # noqa: E402


DEFAULT_RESERVED_WAYS = [1]
REQUIRED_PREFETCHERS = [
    "no",
    "gaze",
    "step",
    "bingo_streaming_disable_overlap_pht_16x64",
]
DEFAULT_PREFETCHERS = REQUIRED_PREFETCHERS


def binary_name(prefetcher: str, reserved_ways: int) -> str:
    if prefetcher == "no":
        return "champsim_1core_l2_no"
    return f"champsim_1core_l2_limited_way_{reserved_ways}way_{prefetcher}"


def binary_path(prefetcher: str, reserved_ways: int) -> Path:
    return REPO_ROOT / "ChampSim" / "bin" / binary_name(prefetcher, reserved_ways)


def build_env(prefetcher: str, run_stem: str, prefetch_log_root: Path) -> Mapping[str, str]:
    if "step" not in prefetcher:
        return {}
    trace_root = step_trace_dir(prefetch_log_root.parent, prefetcher)
    return {
        "STEP_TRACE_OUTPUT_DIR": str(trace_root),
        "STEP_TRACE_BASENAME": run_stem,
    }


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run limited-way single-core L2 experiments.")
    parser.add_argument("--prefetchers", nargs="*", default=DEFAULT_PREFETCHERS, help="Prefetchers to evaluate.")
    parser.add_argument("--prefix", default="lw", help="Output prefix.")
    parser.add_argument(
        "--reserved-ways",
        type=int,
        nargs="*",
        default=DEFAULT_RESERVED_WAYS,
        help="Reserved L2 ways for prefetch fills. Defaults to 1.",
    )
    parser.add_argument("--warmup", type=int, default=50_000_000, help="Warmup instruction count.")
    parser.add_argument("--simulation", type=int, default=100_000_000, help="Simulation instruction count.")
    parser.add_argument("--begin", type=int, default=0, help="Workload list starting index.")
    parser.add_argument("--count", type=int, default=0, help="Number of workloads to run (0 means full list).")
    parser.add_argument("--max-jobs", type=int, default=64, help="Maximum number of parallel ChampSim processes.")
    parser.add_argument("--poll-seconds", type=float, default=30.0, help="Polling interval for job completion.")
    parser.add_argument("--retries", type=int, default=1, help="Retries per failed run.")
    parser.add_argument(
        "--no-skip-completed",
        dest="skip_completed",
        action="store_false",
        help="Do not skip runs that already have log/json outputs.",
    )
    parser.add_argument(
        "--no-skip-missing",
        dest="skip_missing",
        action="store_false",
        help="Abort instead of skipping missing binaries.",
    )
    parser.set_defaults(skip_completed=True, skip_missing=True)
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    prefetchers = list(dict.fromkeys(args.prefetchers))
    reserved_way_values = list(dict.fromkeys(args.reserved_ways))

    if not reserved_way_values:
        raise ValueError("--reserved-ways must provide at least one value")
    if any(reserved_ways <= 0 for reserved_ways in reserved_way_values):
        raise ValueError("--reserved-ways must all be > 0")
    if args.max_jobs <= 0:
        raise ValueError("--max-jobs must be > 0")
    if args.poll_seconds <= 0:
        raise ValueError("--poll-seconds must be > 0")
    if args.retries < 0:
        raise ValueError("--retries must be >= 0")

    total_workloads = len(workloads_all)
    if args.begin < 0 or args.begin >= total_workloads:
        raise ValueError(f"--begin must be in [0, {total_workloads - 1}]")
    max_count_from_begin = total_workloads - args.begin
    count = max_count_from_begin if args.count == 0 else min(args.count, max_count_from_begin)
    selected_workloads = workloads_all[args.begin : args.begin + count]

    overall_failed = 0
    any_tasks = False
    for reserved_ways in reserved_way_values:
        experiment_name = f"limited_way_experiment/ways_{reserved_ways}"
        log_root, json_root = single_core_result_roots("l2", experiment_name, args.warmup, args.simulation)
        tasks, skipped_missing, skipped_completed_runs = prepare_single_core_tasks(
            prefetchers=prefetchers,
            workloads=selected_workloads,
            prefix=args.prefix,
            log_root=log_root,
            json_root=json_root,
            binary_path_builder=lambda prefetcher, reserved_ways=reserved_ways: binary_path(prefetcher, reserved_ways),
            skip_missing=args.skip_missing,
            skip_completed=args.skip_completed,
            run_label=f"limited-way-{reserved_ways}way",
            env_builder=build_env,
        )

        print(
            f"[limited-way-{reserved_ways}way] workloads={count}, prefetchers={len(prefetchers)}, "
            f"queued_runs={len(tasks)}, skipped_missing_binaries={skipped_missing}, "
            f"skipped_completed_runs={skipped_completed_runs}, max_jobs={args.max_jobs}",
            file=sys.stderr,
            flush=True,
        )

        if not tasks:
            print(f"[limited-way-{reserved_ways}way] Nothing to run.", file=sys.stderr, flush=True)
            continue

        any_tasks = True
        failed = run_single_core_task_queue(
            tasks=tasks,
            warmup=args.warmup,
            simulation=args.simulation,
            max_jobs=args.max_jobs,
            poll_seconds=args.poll_seconds,
            retries=args.retries,
            run_label=f"limited-way-{reserved_ways}way",
        )
        overall_failed += failed

    if not any_tasks:
        print("[limited-way] Nothing to run across all reserved-way configurations.", file=sys.stderr, flush=True)
        return 0

    return 1 if overall_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
