#!/usr/bin/env python3
"""
Storage sensitivity experiment launcher (single-core).

This runner throttles concurrent jobs and waits for completion, so one launch
can reliably finish on machines with limited CPU/RAM/IO resources.
"""

import argparse
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Deque, Dict, IO, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = SCRIPT_DIR.parent
CHAMPSIM_DIR = REPO_ROOT / "ChampSim"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
RUN_DIR = SCRIPTS_ROOT / "run"
for path in (SCRIPTS_ROOT, RUN_DIR):
    if str(path) not in sys.path:
        sys.path.append(str(path))

from experiment_utils import is_completed_run, single_core_result_roots  # type: ignore
from workloads import (
    workloads_all,
)


def build_step_storage_variants(prefix: str) -> List[str]:
    return [
        f"{prefix}_ft256_at128_pt2",
        f"{prefix}_ft256_at128_pt4",
        f"{prefix}_ft256_at128_pt8",
        f"{prefix}_ft256_at128_pt16",
        f"{prefix}_ft256_at128_pt32",
        f"{prefix}_ft256_at128_pt64",
        f"{prefix}_ft256_at128_pt128",
        f"{prefix}_ft256_at128_pt256",
        f"step_small",
    ]


STEP_STORAGE_VARIANTS = build_step_storage_variants("step_disable_second")
GAZE_STORAGE_VARIANTS = [
    "gaze_ptway_2",
    "gaze_ptway_4",
    "gaze_ptway_8",
    "gaze_ptway_16",
    "gaze_ptway_32",
    "gaze_ptway_64",
    "gaze_ptway_128",
    "gaze_ptway_256",
]
VBERTI_STORAGE_VARIANTS = [
    "berti_bts_16_hts_8",
    "berti_bts_32_hts_16",
    "berti_bts_64_hts_32",
    "berti_bts_128_hts_64",
    "berti_bts_256_hts_128",
    "berti_bts_512_hts_256",
]
BINGO_STORAGE_VARIANTS = [
    "bingo_pht_16x16",
    "bingo_pht_16x32",
    "bingo_pht_16x64",
    "bingo_pht_16x128",
    "bingo_pht_16x256",
    "bingo_pht_16x512",
    "bingo_pht_16x1024",
]
EBINGO_STORAGE_VARIANTS = [
    "bingo_streaming_disable_overlap_pht_16x16",
    "bingo_streaming_disable_overlap_pht_16x32",
    "bingo_streaming_disable_overlap_pht_16x64",
    "bingo_streaming_disable_overlap_pht_16x128",
    "bingo_streaming_disable_overlap_pht_16x256",
    "bingo_streaming_disable_overlap_pht_16x512",
    "bingo_streaming_disable_overlap_pht_16x1024",
]
IPCP_STORAGE_VARIANTS = [
    "ipcp_l1_it128_ipcp_l2",
    "ipcp_l1_it256_ipcp_l2",
    "ipcp_l1_it512_ipcp_l2",
    "ipcp_l1_it1024_ipcp_l2",
    "ipcp_l1_it2048_ipcp_l2",
    "ipcp_l1_it4096_ipcp_l2",
    "ipcp_l1_it8192_ipcp_l2",
]

DEFAULT_PREFETCHERS = [
    *STEP_STORAGE_VARIANTS,
    *GAZE_STORAGE_VARIANTS,
    *VBERTI_STORAGE_VARIANTS,
    *BINGO_STORAGE_VARIANTS,
    *EBINGO_STORAGE_VARIANTS,
    *IPCP_STORAGE_VARIANTS,
]


@dataclass
class ExperimentTask:
    prefetcher: str
    trace_file: str
    trace_name: str
    compressed_trace: bool
    binary_path: Path
    log_path: Path
    json_path: Path
    attempts: int = 0


def binary_path(prefetcher: str) -> Path:
    return CHAMPSIM_DIR / "bin" / f"champsim_1core_l2_{prefetcher}"


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run storage sensitivity experiments.")
    parser.add_argument(
        "--prefetchers",
        nargs="*",
        default=DEFAULT_PREFETCHERS,
        help="Prefetcher names to evaluate.",
    )
    parser.add_argument("--prefix", default="stor", help="Output prefix.")
    parser.add_argument("--warmup", type=int, default=50_000_000, help="Warmup instruction count.")
    parser.add_argument("--simulation", type=int, default=100_000_000, help="Simulation instruction count.")
    parser.add_argument("--begin", type=int, default=0, help="Workload list starting index.")
    parser.add_argument("--count", type=int, default=0, help="Number of workloads to run (0 means full list).")
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=64,
        help="Maximum number of parallel ChampSim processes.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=30,
        help="Polling interval for job completion.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Retries per failed run (total attempts = retries + 1).",
    )
    parser.add_argument(
        "--no-skip-completed",
        dest="skip_completed",
        action="store_false",
        help="Do not skip runs that already have completed logs/json.",
    )
    parser.add_argument(
        "--no-skip-missing",
        dest="skip_missing",
        action="store_false",
        help="Abort instead of skipping when a binary is missing.",
    )
    parser.set_defaults(skip_missing=True)
    parser.set_defaults(skip_completed=True)
    return parser.parse_args(argv)


def default_workload_count() -> int:
    return len(workloads_all)


def _run_directories(prefetcher: str, warmup: int, simulation: int) -> Tuple[Path, Path]:
    log_root, json_root = single_core_result_roots("l2", "storage_sensitivity", warmup, simulation)
    log_dir = log_root / prefetcher
    json_dir = json_root / prefetcher
    log_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)
    return log_dir, json_dir


def prepare_tasks(
    prefetchers: List[str],
    prefix: str,
    warmup: int,
    simulation: int,
    begin: int,
    count: int,
    skip_missing: bool,
    skip_completed: bool,
) -> Tuple[List[ExperimentTask], int, int]:
    selected_workloads = workloads_all[begin : begin + count]
    tasks: List[ExperimentTask] = []
    skipped_missing = 0
    skipped_completed_runs = 0

    for name in prefetchers:
        binary = binary_path(name)
        if not binary.exists():
            if skip_missing:
                skipped_missing += 1
                print(f"[storage-sensitivity] Skipping {name}: binary not found.", file=sys.stderr, flush=True)
                continue
            raise FileNotFoundError(f"Binary not found: {binary}")

        log_dir, json_dir = _run_directories(name, warmup, simulation)

        for workload in selected_workloads:
            trace_file, trace_name, compressed_trace = workload
            log_path = log_dir / f"{prefix}-{trace_name}.log"
            json_path = json_dir / f"{prefix}-{trace_name}.json"

            if skip_completed and is_completed_run(log_path, json_path):
                skipped_completed_runs += 1
                continue

            tasks.append(
                ExperimentTask(
                    prefetcher=name,
                    trace_file=trace_file,
                    trace_name=trace_name,
                    compressed_trace=compressed_trace,
                    binary_path=binary,
                    log_path=log_path,
                    json_path=json_path,
                )
            )

    return tasks, skipped_missing, skipped_completed_runs


def launch_task(task: ExperimentTask, warmup: int, simulation: int) -> Tuple[subprocess.Popen, IO[str]]:
    trace_path = REPO_ROOT / "traces" / task.trace_file
    if not trace_path.exists():
        raise FileNotFoundError(f"Trace not found: {trace_path}")

    command = [
        str(task.binary_path),
        f"--json={task.json_path}",
        "--warmup_instructions",
        str(warmup),
        "--simulation_instructions",
        str(simulation),
    ]
    if task.compressed_trace:
        command.append("-c")
    command.append(str(trace_path))

    log_file = task.log_path.open("w")
    process = subprocess.Popen(
        command,
        cwd=CHAMPSIM_DIR,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    return process, log_file


def run_task_queue(
    tasks: List[ExperimentTask],
    warmup: int,
    simulation: int,
    max_jobs: int,
    poll_seconds: float,
    retries: int,
) -> int:
    pending: Deque[ExperimentTask] = deque(tasks)
    running: Dict[int, Tuple[ExperimentTask, subprocess.Popen, IO[str], float]] = {}
    finished = 0
    failed = 0
    total = len(tasks)
    max_attempts = retries + 1

    while pending or running:
        while pending and len(running) < max_jobs:
            task = pending.popleft()
            task.attempts += 1
            try:
                process, log_file = launch_task(task, warmup, simulation)
            except Exception as exc:
                if task.attempts < max_attempts:
                    print(
                        f"[storage-sensitivity] Launch failed {task.prefetcher}/{task.trace_name} "
                        f"(attempt {task.attempts}/{max_attempts}): {exc}. Retrying.",
                        file=sys.stderr,
                        flush=True,
                    )
                    pending.append(task)
                else:
                    failed += 1
                    print(
                        f"[storage-sensitivity] Launch failed {task.prefetcher}/{task.trace_name} "
                        f"after {task.attempts} attempts: {exc}",
                        file=sys.stderr,
                        flush=True,
                    )
                continue

            running[process.pid] = (task, process, log_file, time.time())
            print(
                f"[storage-sensitivity] Launched {task.prefetcher}/{task.trace_name} "
                f"({finished + failed + len(running)}/{total}, running={len(running)})",
                file=sys.stderr,
                flush=True,
            )

        if not running:
            continue

        time.sleep(poll_seconds)

        done_pids: List[int] = []
        for pid, (task, process, log_file, start_time) in running.items():
            return_code = process.poll()
            if return_code is None:
                continue

            done_pids.append(pid)
            elapsed = time.time() - start_time
            log_file.close()

            if return_code == 0 and is_completed_run(task.log_path, task.json_path):
                finished += 1
                print(
                    f"[storage-sensitivity] Completed {task.prefetcher}/{task.trace_name} "
                    f"in {elapsed/60:.1f} min ({finished}/{total})",
                    file=sys.stderr,
                    flush=True,
                )
                continue

            if task.attempts < max_attempts:
                pending.append(task)
                print(
                    f"[storage-sensitivity] Failed {task.prefetcher}/{task.trace_name} "
                    f"(rc={return_code}, attempt {task.attempts}/{max_attempts}). Retrying.",
                    file=sys.stderr,
                    flush=True,
                )
            else:
                failed += 1
                print(
                    f"[storage-sensitivity] Failed {task.prefetcher}/{task.trace_name} "
                    f"(rc={return_code}) after {task.attempts} attempts.",
                    file=sys.stderr,
                    flush=True,
                )

        for pid in done_pids:
            running.pop(pid, None)

    print(
        f"[storage-sensitivity] Summary: total={total}, finished={finished}, failed={failed}",
        file=sys.stderr,
        flush=True,
    )
    return failed


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    prefetchers = list(dict.fromkeys(args.prefetchers))
    total_workloads = default_workload_count()
    if args.begin < 0 or args.begin >= total_workloads:
        raise ValueError(f"--begin must be in [0, {total_workloads - 1}]")
    if args.max_jobs <= 0:
        raise ValueError("--max-jobs must be > 0")
    if args.poll_seconds <= 0:
        raise ValueError("--poll-seconds must be > 0")
    if args.retries < 0:
        raise ValueError("--retries must be >= 0")

    max_count_from_begin = total_workloads - args.begin
    count = max_count_from_begin if args.count == 0 else min(args.count, max_count_from_begin)

    tasks, skipped_missing, skipped_completed_runs = prepare_tasks(
        prefetchers=prefetchers,
        prefix=args.prefix,
        warmup=args.warmup,
        simulation=args.simulation,
        begin=args.begin,
        count=count,
        skip_missing=args.skip_missing,
        skip_completed=args.skip_completed,
    )

    print(
        f"[storage-sensitivity] Workloads={count}, prefetchers={len(prefetchers)}, "
        f"queued_runs={len(tasks)}, skipped_missing_prefetchers={skipped_missing}, "
        f"skipped_completed_runs={skipped_completed_runs}, max_jobs={args.max_jobs}",
        file=sys.stderr,
        flush=True,
    )

    if not tasks:
        print("[storage-sensitivity] Nothing to run.", file=sys.stderr, flush=True)
        return 0

    failed = run_task_queue(
        tasks=tasks,
        warmup=args.warmup,
        simulation=args.simulation,
        max_jobs=args.max_jobs,
        poll_seconds=args.poll_seconds,
        retries=args.retries,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
