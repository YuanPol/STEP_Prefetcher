#!/usr/bin/env python3
"""
System sensitivity experiment launcher.

Executes the same BW/L2/LLC sweeps as before, but throttles concurrent jobs
and waits for completion instead of launching everything at once.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Deque, Dict, IO, List, Optional, Sequence, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = SCRIPT_DIR.parent
CHAMPSIM_DIR = REPO_ROOT / "ChampSim"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
RUN_DIR = SCRIPTS_ROOT / "run"
for path in (SCRIPTS_ROOT, RUN_DIR):
    if str(path) not in sys.path:
        sys.path.append(str(path))

from experiment_utils import is_completed_run, single_core_result_roots  # type: ignore
from workloads import workloads_all  # type: ignore


DEFAULT_PREFETCHERS = [

    "no",
    "gaze",
    "step",
    "berti",
    "spp_ppf",
    "bingo_streaming_disable_overlap_pht_16x64",
]

# Keep the same sweep points as the existing script.
BW_SWEEP = [800, 1600, 3200, 6400, 12800]
L2_SWEEP = [0.125, 0.25, 1, 1.5]
LLC_SWEEP = [0.5, 1, 4]

@dataclass
class SystemTask:
    prefetcher: str
    bw: int
    l2c: float
    llc: float
    prefix: str
    trace_file: str
    trace_name: str
    compressed_trace: bool
    binary_path: Path
    log_path: Path
    json_path: Path
    attempts: int = 0


def binary_path(prefetcher: str, bw: int, l2c: float, llc: float) -> Path:
    return CHAMPSIM_DIR / "bin" / f"champsim_1core_l2_{prefetcher}_bw_{bw}_l2c_{l2c}_llc_{llc}"


def _config_tag(prefetcher: str, bw: int, l2c: float, llc: float) -> str:
    return f"{prefetcher}_bw_{bw}_l2c_{l2c}_llc_{llc}"


def _run_directories(prefetcher: str, bw: int, l2c: float, llc: float, warmup: int, simulation: int) -> Tuple[Path, Path]:
    tag = _config_tag(prefetcher, bw, l2c, llc)
    log_root, json_root = single_core_result_roots("l2", "system_parameter_experiment", warmup, simulation)
    log_dir = log_root / tag
    json_dir = json_root / tag
    log_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)
    return log_dir, json_dir


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run system sensitivity experiments.")
    parser.add_argument(
        "--prefetchers",
        nargs="*",
        default=DEFAULT_PREFETCHERS,
        help="Prefetcher names compiled with system-sensitivity variants.",
    )
    parser.add_argument(
        "--prefix",
        default="sys",
        help="Output prefix.",
    )
    parser.add_argument("--warmup", type=int, default=50_000_000, help="Warmup instruction count.")
    parser.add_argument("--simulation", type=int, default=100_000_000, help="Simulation instruction count.")
    parser.add_argument("--begin", type=int, default=0, help="Workload list starting index.")
    parser.add_argument("--count", type=int, default=0, help="Number of workloads to run (0 means full list).")
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=128,
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
        help="Abort when a binary is missing instead of skipping.",
    )
    parser.set_defaults(skip_missing=True)
    parser.set_defaults(skip_completed=True)
    return parser.parse_args(argv)


def default_workload_count() -> int:
    return len(workloads_all)


def build_sweep_configs(prefetcher: str, prefix: str) -> List[Tuple[int, float, float, str]]:
    """Return (bw, l2c, llc, output_prefix) tuples."""
    configs: List[Tuple[int, float, float, str]] = []
    for bw in BW_SWEEP:
        configs.append((bw, 0.5, 2, prefix))
    for l2c in L2_SWEEP:
        configs.append((3200, l2c, 2, prefix))
    for llc in LLC_SWEEP:
        configs.append((3200, 0.5, llc, prefix))
    return configs


def prepare_tasks(
    prefetchers: Sequence[str],
    prefix: str,
    warmup: int,
    simulation: int,
    begin: int,
    count: int,
    skip_missing: bool,
    skip_completed: bool,
) -> Tuple[List[SystemTask], int, int]:
    selected_workloads = workloads_all[begin : begin + count]
    tasks: List[SystemTask] = []
    skipped_missing = 0
    skipped_completed_runs = 0

    for prefetcher in prefetchers:
        sweep_configs = build_sweep_configs(prefetcher, prefix)
        for bw, l2c, llc, out_prefix in sweep_configs:
            binary = binary_path(prefetcher, bw, l2c, llc)
            if not binary.exists():
                if skip_missing:
                    skipped_missing += 1
                    print(
                        f"[system-sensitivity] Skipping missing binary: {binary.name}",
                        file=sys.stderr,
                        flush=True,
                    )
                    continue
                raise FileNotFoundError(f"Binary not found: {binary}")

            log_dir, json_dir = _run_directories(prefetcher, bw, l2c, llc, warmup, simulation)
            for trace_file, trace_name, compressed_trace in selected_workloads:
                log_path = log_dir / f"{out_prefix}-{trace_name}.log"
                json_path = json_dir / f"{out_prefix}-{trace_name}.json"

                if skip_completed and is_completed_run(log_path, json_path):
                    skipped_completed_runs += 1
                    continue

                tasks.append(
                    SystemTask(
                        prefetcher=prefetcher,
                        bw=bw,
                        l2c=l2c,
                        llc=llc,
                        prefix=out_prefix,
                        trace_file=trace_file,
                        trace_name=trace_name,
                        compressed_trace=compressed_trace,
                        binary_path=binary,
                        log_path=log_path,
                        json_path=json_path,
                    )
                )

    return tasks, skipped_missing, skipped_completed_runs


def launch_task(task: SystemTask, warmup: int, simulation: int) -> Tuple[subprocess.Popen, IO[str]]:
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
    tasks: List[SystemTask],
    warmup: int,
    simulation: int,
    max_jobs: int,
    poll_seconds: float,
    retries: int,
) -> int:
    pending: Deque[SystemTask] = deque(tasks)
    running: Dict[int, Tuple[SystemTask, subprocess.Popen, IO[str], float]] = {}
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
                        f"[system-sensitivity] Launch failed {task.prefetcher}/"
                        f"bw{task.bw}_l2{task.l2c}_llc{task.llc}/{task.trace_name} "
                        f"(attempt {task.attempts}/{max_attempts}): {exc}. Retrying.",
                        file=sys.stderr,
                        flush=True,
                    )
                    pending.append(task)
                else:
                    failed += 1
                    print(
                        f"[system-sensitivity] Launch failed {task.prefetcher}/"
                        f"bw{task.bw}_l2{task.l2c}_llc{task.llc}/{task.trace_name} "
                        f"after {task.attempts} attempts: {exc}",
                        file=sys.stderr,
                        flush=True,
                    )
                continue

            running[process.pid] = (task, process, log_file, time.time())
            print(
                f"[system-sensitivity] Launched {task.prefetcher}/bw{task.bw}_l2{task.l2c}_llc{task.llc}/"
                f"{task.trace_name} ({finished + failed + len(running)}/{total}, running={len(running)})",
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
                    f"[system-sensitivity] Completed {task.prefetcher}/bw{task.bw}_l2{task.l2c}_llc{task.llc}/"
                    f"{task.trace_name} in {elapsed/60:.1f} min ({finished}/{total})",
                    file=sys.stderr,
                    flush=True,
                )
                continue

            if task.attempts < max_attempts:
                pending.append(task)
                print(
                    f"[system-sensitivity] Failed {task.prefetcher}/bw{task.bw}_l2{task.l2c}_llc{task.llc}/"
                    f"{task.trace_name} (rc={return_code}, attempt {task.attempts}/{max_attempts}). Retrying.",
                    file=sys.stderr,
                    flush=True,
                )
            else:
                failed += 1
                print(
                    f"[system-sensitivity] Failed {task.prefetcher}/bw{task.bw}_l2{task.l2c}_llc{task.llc}/"
                    f"{task.trace_name} (rc={return_code}) after {task.attempts} attempts.",
                    file=sys.stderr,
                    flush=True,
                )

        for pid in done_pids:
            running.pop(pid, None)

    print(
        f"[system-sensitivity] Summary: total={total}, finished={finished}, failed={failed}",
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
        f"[system-sensitivity] Workloads={count}, prefetchers={len(prefetchers)}, "
        f"queued_runs={len(tasks)}, skipped_missing_binaries={skipped_missing}, "
        f"skipped_completed_runs={skipped_completed_runs}, max_jobs={args.max_jobs}",
        file=sys.stderr,
        flush=True,
    )

    if not tasks:
        print("[system-sensitivity] Nothing to run.", file=sys.stderr, flush=True)
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
