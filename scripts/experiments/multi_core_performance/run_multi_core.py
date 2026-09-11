#!/usr/bin/env python3
"""
Multi-core experiment launcher.

This runner throttles concurrent jobs and waits for completion, so one launch
can reliably finish on machines with limited CPU/RAM/IO resources.
"""

import argparse
import json
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

from workloads import (  # noqa: E402
    workloads_all,
    workloads_all_2core_heterogeneous,
    workloads_all_4core_heterogeneous,
    workloads_all_8core_heterogeneous,
)
from experiment_utils import is_completed_run, multicore_result_roots  # noqa: E402


DEFAULT_PREFETCHERS = [
    "no",
    "dspatch",
    "gaze",
    "step",
    "bingo_streaming_disable_overlap_pht_16x64",
]

HETEROGENEOUS_WORKLOADS = {
    2: workloads_all_2core_heterogeneous,
    4: workloads_all_4core_heterogeneous,
    8: workloads_all_8core_heterogeneous,
}

@dataclass
class ExperimentTask:
    num_cores: int
    prefetcher: str
    trace_files: List[str]
    trace_label: str
    compressed_trace: bool
    binary_path: Path
    log_path: Path
    json_path: Path
    attempts: int = 0


def binary_path(num_cores: int, prefetcher: str) -> Path:
    return CHAMPSIM_DIR / "bin" / f"champsim_{num_cores}core_l2_{prefetcher}"


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run multi-core performance experiments.")
    parser.add_argument("--cores", type=int, choices=(2, 4, 8), default=None, help="Number of CPU cores.")
    parser.add_argument(
        "--prefetchers",
        nargs="*",
        default=DEFAULT_PREFETCHERS,
        help="Prefetcher names to evaluate.",
    )
    parser.add_argument("--prefix", default="mc", help="Output prefix.")
    parser.add_argument("--warmup", type=int, default=50_000_000, help="Warmup instruction count.")
    parser.add_argument("--simulation", type=int, default=100_000_000, help="Simulation instruction count.")
    parser.add_argument("--begin", type=int, default=0, help="Workload list starting index.")
    parser.add_argument("--count", type=int, default=0, help="Number of workloads to run (0 means full list).")
    parser.add_argument(
        "--heterogeneous",
        action="store_true",
        help="Run heterogeneous mixes (uses predefined random groups for 2/4/8 cores).",
    )
    parser.add_argument(
        "--heterogeneous-mix-file",
        type=Path,
        default=None,
        help="Optional JSON file with custom heterogeneous mixes. Preserves the built-in mix groups.",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=80,
        help="Maximum number of parallel ChampSim processes.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=30.0,
        help="Polling interval for job completion.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=1,
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


def default_heterogeneous_workload_count(num_cores: Optional[int]) -> int:
    if num_cores in HETEROGENEOUS_WORKLOADS:
        return len(HETEROGENEOUS_WORKLOADS[num_cores])
    return min(len(groups) for groups in HETEROGENEOUS_WORKLOADS.values())


def load_custom_heterogeneous_workloads(path: Optional[Path]) -> Optional[Dict[int, List[List[List[object]]]]]:
    if path is None:
        return None

    data = json.loads(path.read_text())
    if isinstance(data, dict):
        num_cores = int(data["num_cores"])
        mixes = data["mixes"]
    else:
        raise ValueError("Custom heterogeneous mix file must be a JSON object with 'num_cores' and 'mixes'.")

    normalized: List[List[List[object]]] = []
    for mix in mixes:
        normalized_mix: List[List[object]] = []
        for entry in mix:
            if isinstance(entry, dict):
                normalized_mix.append(
                    [
                        entry["trace_file"],
                        entry["trace_name"],
                        bool(entry["compressed"]),
                    ]
                )
            else:
                if len(entry) != 3:
                    raise ValueError(f"Invalid mix entry in {path}: {entry}")
                normalized_mix.append([entry[0], entry[1], bool(entry[2])])
        normalized.append(normalized_mix)

    return {num_cores: normalized}


def _run_directories(num_cores: int, prefetcher: str, warmup: int, simulation: int, heterogeneous: bool) -> Tuple[Path, Path]:
    mode = "heter" if heterogeneous else "homo"
    log_root, json_root = multicore_result_roots(mode, num_cores, warmup, simulation)
    log_dir = log_root / prefetcher
    json_dir = json_root / prefetcher
    log_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)
    return log_dir, json_dir


def selected_cores(requested_core: Optional[int]) -> List[int]:
    return [requested_core] if requested_core is not None else [2, 4, 8]


def prepare_tasks(
    num_cores: Optional[int],
    prefetchers: List[str],
    prefix: str,
    warmup: int,
    simulation: int,
    begin: int,
    count: int,
    heterogeneous: bool,
    skip_missing: bool,
    skip_completed: bool,
    custom_heterogeneous_workloads: Optional[Dict[int, List[List[List[object]]]]] = None,
) -> Tuple[List[ExperimentTask], int, int]:
    tasks: List[ExperimentTask] = []
    skipped_missing = 0
    skipped_completed_runs = 0
    cores_to_run = selected_cores(num_cores)

    for current_cores in cores_to_run:
        if heterogeneous:
            heter_workloads = custom_heterogeneous_workloads or HETEROGENEOUS_WORKLOADS
            if current_cores not in heter_workloads:
                raise ValueError(f"No heterogeneous workload definition for {current_cores} cores.")
            work_items = heter_workloads[current_cores][begin : begin + count]
        else:
            work_items = workloads_all[begin : begin + count]

        for name in prefetchers:
            binary = binary_path(current_cores, name)
            if not binary.exists():
                if skip_missing:
                    skipped_missing += 1
                    print(
                        f"[multi-core] Skipping {name} ({current_cores} cores): binary not found.",
                        file=sys.stderr,
                        flush=True,
                    )
                    continue
                raise FileNotFoundError(f"Binary not found: {binary}")

            log_dir, json_dir = _run_directories(current_cores, name, warmup, simulation, heterogeneous)

            for workload in work_items:
                if heterogeneous:
                    trace_files = [entry[0] for entry in workload]
                    trace_names = [entry[1] for entry in workload]
                    compressed = any(entry[2] for entry in workload)
                    trace_label = "-".join(trace_names)
                else:
                    trace_file, trace_name, compressed = workload
                    trace_files = [trace_file for _ in range(current_cores)]
                    trace_label = trace_name

                log_path = log_dir / f"{prefix}-{trace_label}.log"
                json_path = json_dir / f"{prefix}-{trace_label}.json"

                if skip_completed and is_completed_run(log_path, json_path):
                    skipped_completed_runs += 1
                    continue

                tasks.append(
                    ExperimentTask(
                        num_cores=current_cores,
                        prefetcher=name,
                        trace_files=trace_files,
                        trace_label=trace_label,
                        compressed_trace=compressed,
                        binary_path=binary,
                        log_path=log_path,
                        json_path=json_path,
                    )
                )

    return tasks, skipped_missing, skipped_completed_runs


def launch_task(task: ExperimentTask, warmup: int, simulation: int) -> Tuple[subprocess.Popen, IO[str]]:
    trace_paths: List[str] = []
    for trace_file in task.trace_files:
        trace_path = REPO_ROOT / "traces" / trace_file
        if not trace_path.exists():
            raise FileNotFoundError(f"Trace not found: {trace_path}")
        trace_paths.append(str(trace_path))

    command = [
        str(task.binary_path),
        "--warmup_instructions",
        str(warmup),
        "--simulation_instructions",
        str(simulation),
        f"--json={task.json_path}",
    ]
    if task.compressed_trace:
        command.append("-c")
    command.extend(trace_paths)

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
                        f"[multi-core] Launch failed {task.prefetcher}/{task.num_cores}c/{task.trace_label} "
                        f"(attempt {task.attempts}/{max_attempts}): {exc}. Retrying.",
                        file=sys.stderr,
                        flush=True,
                    )
                    pending.append(task)
                else:
                    failed += 1
                    print(
                        f"[multi-core] Launch failed {task.prefetcher}/{task.num_cores}c/{task.trace_label} "
                        f"after {task.attempts} attempts: {exc}",
                        file=sys.stderr,
                        flush=True,
                    )
                continue

            running[process.pid] = (task, process, log_file, time.time())
            print(
                f"[multi-core] Launched {task.prefetcher}/{task.num_cores}c/{task.trace_label} "
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
                    f"[multi-core] Completed {task.prefetcher}/{task.num_cores}c/{task.trace_label} "
                    f"in {elapsed/60:.1f} min ({finished}/{total})",
                    file=sys.stderr,
                    flush=True,
                )
                continue

            if task.attempts < max_attempts:
                pending.append(task)
                print(
                    f"[multi-core] Failed {task.prefetcher}/{task.num_cores}c/{task.trace_label} "
                    f"(rc={return_code}, attempt {task.attempts}/{max_attempts}). Retrying.",
                    file=sys.stderr,
                    flush=True,
                )
            else:
                failed += 1
                print(
                    f"[multi-core] Failed {task.prefetcher}/{task.num_cores}c/{task.trace_label} "
                    f"(rc={return_code}) after {task.attempts} attempts.",
                    file=sys.stderr,
                    flush=True,
                )

        for pid in done_pids:
            running.pop(pid, None)

    print(
        f"[multi-core] Summary: total={total}, finished={finished}, failed={failed}",
        file=sys.stderr,
        flush=True,
    )
    return failed


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    prefetchers = list(dict.fromkeys(args.prefetchers))
    custom_heterogeneous_workloads = load_custom_heterogeneous_workloads(args.heterogeneous_mix_file)
    effective_prefix = args.prefix
    if effective_prefix == "mc":
        effective_prefix = "het" if args.heterogeneous else "homo"

    if args.heterogeneous_mix_file is not None and not args.heterogeneous:
        raise ValueError("--heterogeneous-mix-file requires --heterogeneous")

    if args.max_jobs <= 0:
        raise ValueError("--max-jobs must be > 0")
    if args.poll_seconds <= 0:
        raise ValueError("--poll-seconds must be > 0")
    if args.retries < 0:
        raise ValueError("--retries must be >= 0")

    if args.heterogeneous and custom_heterogeneous_workloads is not None:
        if args.cores is None:
            if len(custom_heterogeneous_workloads) != 1:
                raise ValueError("Custom heterogeneous mix files currently require a single core-count definition.")
            args.cores = next(iter(custom_heterogeneous_workloads))
        total_workloads = len(custom_heterogeneous_workloads[args.cores])
    else:
        total_workloads = default_heterogeneous_workload_count(args.cores) if args.heterogeneous else default_workload_count()
    if args.begin < 0 or args.begin >= total_workloads:
        raise ValueError(f"--begin must be in [0, {total_workloads - 1}]")

    max_count_from_begin = total_workloads - args.begin
    count = max_count_from_begin if args.count == 0 else min(args.count, max_count_from_begin)

    tasks, skipped_missing, skipped_completed_runs = prepare_tasks(
        num_cores=args.cores,
        prefetchers=prefetchers,
        prefix=effective_prefix,
        warmup=args.warmup,
        simulation=args.simulation,
        begin=args.begin,
        count=count,
        heterogeneous=args.heterogeneous,
        skip_missing=args.skip_missing,
        skip_completed=args.skip_completed,
        custom_heterogeneous_workloads=custom_heterogeneous_workloads,
    )

    mode = "heterogeneous" if args.heterogeneous else "homogeneous"
    core_desc = ",".join(str(core) for core in selected_cores(args.cores))
    print(
        f"[multi-core] Mode={mode}, cores={core_desc}, workload_groups={count}, prefetchers={len(prefetchers)}, "
        f"queued_runs={len(tasks)}, skipped_missing_binaries={skipped_missing}, prefix={effective_prefix}, "
        f"skipped_completed_runs={skipped_completed_runs}, max_jobs={args.max_jobs}",
        file=sys.stderr,
        flush=True,
    )

    if not tasks:
        print("[multi-core] Nothing to run.", file=sys.stderr, flush=True)
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
