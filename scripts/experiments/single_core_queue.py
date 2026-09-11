#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Deque, Dict, IO, List, Mapping, Optional, Sequence, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SCRIPT_DIR.parent
SCRIPTS_ROOT = REPO_ROOT / "scripts"
RUN_DIR = SCRIPTS_ROOT / "run"
for path in (SCRIPTS_ROOT, RUN_DIR):
    if str(path) not in sys.path:
        sys.path.append(str(path))

from experiment_utils import CHAMPSIM_DIR, is_completed_run  # noqa: E402


@dataclass
class SingleCoreTask:
    prefetcher: str
    trace_file: str
    trace_name: str
    compressed_trace: bool
    binary_path: Path
    log_path: Path
    json_path: Path
    env: Dict[str, str] = field(default_factory=dict)
    attempts: int = 0


EnvBuilder = Callable[[str, str, Path], Mapping[str, str]]


def prepare_single_core_tasks(
    *,
    prefetchers: Sequence[str],
    workloads: Sequence[Sequence],
    prefix: str,
    log_root: Path,
    json_root: Path,
    binary_path_builder: Callable[[str], Path],
    skip_missing: bool,
    skip_completed: bool,
    run_label: str,
    env_builder: Optional[EnvBuilder] = None,
) -> Tuple[List[SingleCoreTask], int, int]:
    tasks: List[SingleCoreTask] = []
    skipped_missing = 0
    skipped_completed_runs = 0

    for name in prefetchers:
        binary = binary_path_builder(name)
        if not binary.exists():
            if skip_missing:
                skipped_missing += 1
                print(f"[{run_label}] Skipping {name}: binary not found.", file=sys.stderr, flush=True)
                continue
            raise FileNotFoundError(f"Binary not found: {binary}")

        prefetch_log_root = log_root / name
        prefetch_json_root = json_root / name
        prefetch_log_root.mkdir(parents=True, exist_ok=True)
        prefetch_json_root.mkdir(parents=True, exist_ok=True)

        for trace_file, trace_name, compressed_trace in workloads:
            log_path = prefetch_log_root / f"{prefix}-{trace_name}.log"
            json_path = prefetch_json_root / f"{prefix}-{trace_name}.json"

            if skip_completed and is_completed_run(log_path, json_path):
                skipped_completed_runs += 1
                continue

            env = dict(env_builder(name, f"{prefix}-{trace_name}", prefetch_log_root) if env_builder else {})
            tasks.append(
                SingleCoreTask(
                    prefetcher=name,
                    trace_file=trace_file,
                    trace_name=trace_name,
                    compressed_trace=compressed_trace,
                    binary_path=binary,
                    log_path=log_path,
                    json_path=json_path,
                    env=env,
                )
            )

    return tasks, skipped_missing, skipped_completed_runs


def launch_single_core_task(task: SingleCoreTask, warmup: int, simulation: int) -> Tuple[subprocess.Popen, IO[str]]:
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

    env = None
    if task.env:
        env = os.environ.copy()
        env.update(task.env)

    log_file = task.log_path.open("w")
    process = subprocess.Popen(
        command,
        cwd=CHAMPSIM_DIR,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    return process, log_file


def run_single_core_task_queue(
    *,
    tasks: List[SingleCoreTask],
    warmup: int,
    simulation: int,
    max_jobs: int,
    poll_seconds: float,
    retries: int,
    run_label: str,
) -> int:
    pending: Deque[SingleCoreTask] = deque(tasks)
    running: Dict[int, Tuple[SingleCoreTask, subprocess.Popen, IO[str], float]] = {}
    finished = 0
    failed = 0
    total = len(tasks)
    max_attempts = retries + 1

    while pending or running:
        while pending and len(running) < max_jobs:
            task = pending.popleft()
            task.attempts += 1
            try:
                process, log_file = launch_single_core_task(task, warmup, simulation)
            except Exception as exc:
                if task.attempts < max_attempts:
                    print(
                        f"[{run_label}] Launch failed {task.prefetcher}/{task.trace_name} "
                        f"(attempt {task.attempts}/{max_attempts}): {exc}. Retrying.",
                        file=sys.stderr,
                        flush=True,
                    )
                    pending.append(task)
                else:
                    failed += 1
                    print(
                        f"[{run_label}] Launch failed {task.prefetcher}/{task.trace_name} "
                        f"after {task.attempts} attempts: {exc}",
                        file=sys.stderr,
                        flush=True,
                    )
                continue

            running[process.pid] = (task, process, log_file, time.time())
            print(
                f"[{run_label}] Launched {task.prefetcher}/{task.trace_name} "
                f"({finished + failed + len(running)}/{total}, running={len(running)})",
                file=sys.stderr,
                flush=True,
            )

        if not running:
            continue

        time.sleep(poll_seconds)

        done_pids: List[int] = []
        for pid, (task, process, log_file, start_time) in list(running.items()):
            return_code = process.poll()
            if return_code is None:
                continue

            done_pids.append(pid)
            elapsed = time.time() - start_time
            log_file.close()

            if return_code == 0 and is_completed_run(task.log_path, task.json_path):
                finished += 1
                print(
                    f"[{run_label}] Completed {task.prefetcher}/{task.trace_name} "
                    f"in {elapsed/60:.1f} min ({finished}/{total})",
                    file=sys.stderr,
                    flush=True,
                )
                continue

            if task.attempts < max_attempts:
                pending.append(task)
                print(
                    f"[{run_label}] Failed {task.prefetcher}/{task.trace_name} "
                    f"(rc={return_code}, attempt {task.attempts}/{max_attempts}). Retrying.",
                    file=sys.stderr,
                    flush=True,
                )
            else:
                failed += 1
                print(
                    f"[{run_label}] Failed {task.prefetcher}/{task.trace_name} "
                    f"(rc={return_code}) after {task.attempts} attempts.",
                    file=sys.stderr,
                    flush=True,
                )

        for pid in done_pids:
            running.pop(pid, None)

    print(
        f"[{run_label}] Summary: total={total}, finished={finished}, failed={failed}",
        file=sys.stderr,
        flush=True,
    )
    return failed
