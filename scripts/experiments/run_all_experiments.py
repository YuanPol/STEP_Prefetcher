#!/usr/bin/env python3
"""
Global experiment launcher with a shared task queue.

Unlike the previous implementation, this script does not wait for one
experiment suite to finish before looking at the next one. It prepares the
unfinished tasks from each enabled suite, then schedules them together under a
single global ``--max-jobs`` limit.
"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Deque, Dict, IO, List, Sequence, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPTS_ROOT = SCRIPT_DIR.parent
RUN_DIR = SCRIPTS_ROOT / "run"
for path in (SCRIPTS_ROOT, RUN_DIR):
    if str(path) not in sys.path:
        sys.path.append(str(path))

from experiment_utils import is_completed_run, single_core_result_roots  # type: ignore  # noqa: E402
from single_core_queue import prepare_single_core_tasks  # type: ignore  # noqa: E402
from workloads import workloads_all  # type: ignore  # noqa: E402


POLL_SECONDS_DEFAULT = 30.0


@dataclass
class SuiteRunner:
    name: str
    pending: Deque[object]
    launch_task: Callable[[object, int, int], Tuple[subprocess.Popen, IO[str]]]
    describe_task: Callable[[object], str]
    max_attempts: int
    skipped_missing: int = 0
    skipped_completed: int = 0
    total: int = 0
    finished: int = 0
    failed: int = 0


def _load_module(module_name: str, relative_path: str):
    module_path = SCRIPT_DIR / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module {module_name} from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _resolve_count(total_workloads: int, begin: int = 0, count: int = 0) -> int:
    if begin < 0 or begin >= total_workloads:
        raise ValueError(f"--begin must be in [0, {total_workloads - 1}]")
    max_count_from_begin = total_workloads - begin
    return max_count_from_begin if count == 0 else min(count, max_count_from_begin)


def _launch_global_queue(
    *,
    suites: Sequence[SuiteRunner],
    warmup: int,
    simulation: int,
    max_jobs: int,
    poll_seconds: float,
) -> int:
    running: Dict[int, Tuple[SuiteRunner, object, subprocess.Popen, IO[str], float]] = {}
    next_suite_idx = 0
    total_tasks = sum(suite.total for suite in suites)

    if total_tasks == 0:
        print("[run-all] Nothing to run.", file=sys.stderr, flush=True)
        return 0

    while any(suite.pending for suite in suites) or running:
        while len(running) < max_jobs and any(suite.pending for suite in suites):
            launched = False
            for _ in range(len(suites)):
                suite = suites[next_suite_idx]
                next_suite_idx = (next_suite_idx + 1) % len(suites)
                if not suite.pending:
                    continue

                task = suite.pending.popleft()
                task.attempts += 1
                try:
                    process, log_file = suite.launch_task(task, warmup, simulation)
                except Exception as exc:
                    task_desc = suite.describe_task(task)
                    if task.attempts < suite.max_attempts:
                        suite.pending.append(task)
                        print(
                            f"[run-all] Launch failed {suite.name}:{task_desc} "
                            f"(attempt {task.attempts}/{suite.max_attempts}): {exc}. Retrying.",
                            file=sys.stderr,
                            flush=True,
                        )
                    else:
                        suite.failed += 1
                        print(
                            f"[run-all] Launch failed {suite.name}:{task_desc} "
                            f"after {task.attempts} attempts: {exc}",
                            file=sys.stderr,
                            flush=True,
                        )
                    launched = True
                    break

                running[process.pid] = (suite, task, process, log_file, time.time())
                print(
                    f"[run-all] Launched {suite.name}:{suite.describe_task(task)} "
                    f"(running={len(running)}/{max_jobs})",
                    file=sys.stderr,
                    flush=True,
                )
                launched = True
                break

            if not launched:
                break

        if not running:
            continue

        time.sleep(poll_seconds)

        done_pids: List[int] = []
        for pid, (suite, task, process, log_file, start_time) in list(running.items()):
            return_code = process.poll()
            if return_code is None:
                continue

            done_pids.append(pid)
            elapsed = time.time() - start_time
            log_file.close()
            task_desc = suite.describe_task(task)

            if return_code == 0 and is_completed_run(task.log_path, task.json_path):
                suite.finished += 1
                print(
                    f"[run-all] Completed {suite.name}:{task_desc} "
                    f"in {elapsed/60:.1f} min ({suite.finished}/{suite.total})",
                    file=sys.stderr,
                    flush=True,
                )
                continue

            if task.attempts < suite.max_attempts:
                suite.pending.append(task)
                print(
                    f"[run-all] Failed {suite.name}:{task_desc} "
                    f"(rc={return_code}, attempt {task.attempts}/{suite.max_attempts}). Retrying.",
                    file=sys.stderr,
                    flush=True,
                )
            else:
                suite.failed += 1
                print(
                    f"[run-all] Failed {suite.name}:{task_desc} "
                    f"(rc={return_code}) after {task.attempts} attempts.",
                    file=sys.stderr,
                    flush=True,
                )

        for pid in done_pids:
            running.pop(pid, None)

    total_failed = 0
    for suite in suites:
        total_failed += suite.failed
        print(
            f"[run-all] Summary {suite.name}: queued={suite.total}, finished={suite.finished}, "
            f"failed={suite.failed}, skipped_missing={suite.skipped_missing}, "
            f"skipped_completed={suite.skipped_completed}",
            file=sys.stderr,
            flush=True,
        )

    return total_failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run all experiment suites with a shared global task queue.")
    parser.add_argument("--warmup", type=int, default=50_000_000, help="Warmup instructions (default: 50M).")
    parser.add_argument("--simulation", type=int, default=100_000_000, help="Simulation instructions (default: 100M).")
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=64,
        help="Maximum number of parallel ChampSim processes across all experiment suites.",
    )
    parser.add_argument("--prefix", default="mc", help="Prefix used by the homogeneous multi-core suite.")
    parser.add_argument("--skip-single-core", action="store_true", help="Skip single-core runs.")
    parser.add_argument("--skip-multi-core", action="store_true", help="Skip multi-core runs.")
    parser.add_argument("--skip-multi-core-hetero", action="store_true", help="Skip heterogeneous multi-core runs.")
    parser.add_argument("--skip-multi-level", action="store_true", help="Skip multi-level L1+L2 runs.")
    parser.add_argument("--skip-storage", action="store_true", help="Skip storage sensitivity runs.")
    parser.add_argument("--skip-parameter-sweep", action="store_true", help="Skip parameter sweep runs.")
    parser.add_argument("--skip-l1", action="store_true", help="Skip L1-level experiments.")
    parser.add_argument("--skip-ablation", action="store_true", help="Skip ablation experiments.")
    parser.add_argument("--skip-limited-way", action="store_true", help="Skip limited-way L2 experiments.")
    parser.add_argument("--skip-system", action="store_true", help="Skip system parameter sensitivity experiments.")
    parser.add_argument(
        "--hetero-cores",
        type=int,
        choices=(2, 4, 8),
        default=None,
        help="Optional core count for heterogeneous multi-core runs. Defaults to all 2/4/8 core groups.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=POLL_SECONDS_DEFAULT,
        help="Global polling interval for job completion.",
    )
    parser.add_argument(
        "--no-skip-completed",
        dest="skip_completed",
        action="store_false",
        help="Do not skip tasks that already have completed log/json outputs.",
    )
    parser.set_defaults(skip_completed=True)
    args = parser.parse_args(argv)

    if args.max_jobs <= 0:
        raise ValueError("--max-jobs must be > 0")
    if args.poll_seconds <= 0:
        raise ValueError("--poll-seconds must be > 0")

    single_core_queue_mod = _load_module("run_all_single_core_queue", "single_core_queue.py")
    single_core_mod = _load_module("run_all_single_core", "single_core_performance/run_single_core.py")
    multi_level_mod = _load_module("run_all_multi_level", "multi_level_prefetching/run_multi_level_prefetching.py")
    parameter_mod = _load_module("run_all_parameter", "parameter_experiment/run_parameter_sweep.py")
    l1_mod = _load_module("run_all_l1", "l1_level/run_l1.py")
    ablation_mod = _load_module("run_all_ablation", "ablation_experiment/run_ablation.py")
    limited_way_mod = _load_module("run_all_limited_way", "limited_way_experiment/run_limited_way_experiment.py")
    storage_mod = _load_module("run_all_storage", "storage_sensitivity/run_storage_sensitivity.py")
    system_mod = _load_module("run_all_system", "system_parameter_experiment/run_system_sensitivity.py")
    multi_core_mod = _load_module("run_all_multicore", "multi_core_performance/run_multi_core.py")

    suites: List[SuiteRunner] = []
    single_core_launch = single_core_queue_mod.launch_single_core_task

    single_core_workloads = workloads_all
    single_core_count = _resolve_count(len(single_core_workloads))
    selected_single_core_workloads = single_core_workloads[:single_core_count]

    if not args.skip_single_core:
        log_root, json_root = single_core_result_roots("l2", "single_core_performance", args.warmup, args.simulation)
        tasks, skipped_missing, skipped_completed_runs = prepare_single_core_tasks(
            prefetchers=list(dict.fromkeys(single_core_mod.DEFAULT_PREFETCHERS)),
            workloads=selected_single_core_workloads,
            prefix="sc",
            log_root=log_root,
            json_root=json_root,
            binary_path_builder=single_core_mod.binary_path,
            skip_missing=True,
            skip_completed=args.skip_completed,
            run_label="single-core",
            env_builder=single_core_mod.build_env,
        )
        suites.append(
            SuiteRunner(
                name="single-core",
                pending=deque(tasks),
                launch_task=single_core_launch,
                describe_task=lambda task: f"{task.prefetcher}/{task.trace_name}",
                max_attempts=single_core_mod.parse_args([]).retries + 1,
                skipped_missing=skipped_missing,
                skipped_completed=skipped_completed_runs,
                total=len(tasks),
            )
        )

    if not args.skip_multi_level:
        log_root, json_root = single_core_result_roots("l2", "multi_level_prefetching", args.warmup, args.simulation)
        tasks, skipped_missing, skipped_completed_runs = prepare_single_core_tasks(
            prefetchers=list(dict.fromkeys(multi_level_mod.DEFAULT_PREFETCHERS)),
            workloads=selected_single_core_workloads,
            prefix="ml",
            log_root=log_root,
            json_root=json_root,
            binary_path_builder=multi_level_mod.binary_path,
            skip_missing=True,
            skip_completed=args.skip_completed,
            run_label="multi-level",
            env_builder=multi_level_mod.build_env,
        )
        suites.append(
            SuiteRunner(
                name="multi-level",
                pending=deque(tasks),
                launch_task=single_core_launch,
                describe_task=lambda task: f"{task.prefetcher}/{task.trace_name}",
                max_attempts=multi_level_mod.parse_args([]).retries + 1,
                skipped_missing=skipped_missing,
                skipped_completed=skipped_completed_runs,
                total=len(tasks),
            )
        )

    if not args.skip_l1:
        log_root, json_root = single_core_result_roots("l1", "l1_level", args.warmup, args.simulation)
        tasks, skipped_missing, skipped_completed_runs = prepare_single_core_tasks(
            prefetchers=list(dict.fromkeys(l1_mod.DEFAULT_PREFETCHERS)),
            workloads=selected_single_core_workloads,
            prefix="l1",
            log_root=log_root,
            json_root=json_root,
            binary_path_builder=l1_mod.binary_path,
            skip_missing=True,
            skip_completed=args.skip_completed,
            run_label="l1",
        )
        suites.append(
            SuiteRunner(
                name="l1",
                pending=deque(tasks),
                launch_task=single_core_launch,
                describe_task=lambda task: f"{task.prefetcher}/{task.trace_name}",
                max_attempts=l1_mod.parse_args([]).retries + 1,
                skipped_missing=skipped_missing,
                skipped_completed=skipped_completed_runs,
                total=len(tasks),
            )
        )

    if not args.skip_parameter_sweep:
        log_root, json_root = single_core_result_roots("l2", "parameter_sweep", args.warmup, args.simulation)
        tasks, skipped_missing, skipped_completed_runs = prepare_single_core_tasks(
            prefetchers=list(dict.fromkeys(parameter_mod.DEFAULT_PREFETCHERS)),
            workloads=selected_single_core_workloads,
            prefix="param",
            log_root=log_root,
            json_root=json_root,
            binary_path_builder=parameter_mod.binary_path,
            skip_missing=True,
            skip_completed=args.skip_completed,
            run_label="parameter-sweep",
        )
        suites.append(
            SuiteRunner(
                name="parameter-sweep",
                pending=deque(tasks),
                launch_task=single_core_launch,
                describe_task=lambda task: f"{task.prefetcher}/{task.trace_name}",
                max_attempts=parameter_mod.parse_args([]).retries + 1,
                skipped_missing=skipped_missing,
                skipped_completed=skipped_completed_runs,
                total=len(tasks),
            )
        )

    if not args.skip_ablation:
        log_root, json_root = single_core_result_roots("l2", "ablation_experiment", args.warmup, args.simulation)
        tasks, skipped_missing, skipped_completed_runs = prepare_single_core_tasks(
            prefetchers=list(dict.fromkeys(ablation_mod.DEFAULT_PREFETCHERS)),
            workloads=selected_single_core_workloads,
            prefix="abl",
            log_root=log_root,
            json_root=json_root,
            binary_path_builder=ablation_mod.binary_path,
            skip_missing=True,
            skip_completed=args.skip_completed,
            run_label="ablation",
        )
        suites.append(
            SuiteRunner(
                name="ablation",
                pending=deque(tasks),
                launch_task=single_core_launch,
                describe_task=lambda task: f"{task.prefetcher}/{task.trace_name}",
                max_attempts=ablation_mod.parse_args([]).retries + 1,
                skipped_missing=skipped_missing,
                skipped_completed=skipped_completed_runs,
                total=len(tasks),
            )
        )

    if not args.skip_limited_way:
        limited_defaults = limited_way_mod.parse_args([])
        for reserved_ways in limited_defaults.reserved_ways:
            experiment_name = f"limited_way_experiment/ways_{reserved_ways}"
            log_root, json_root = single_core_result_roots("l2", experiment_name, args.warmup, args.simulation)
            tasks, skipped_missing, skipped_completed_runs = prepare_single_core_tasks(
                prefetchers=list(dict.fromkeys(limited_defaults.prefetchers)),
                workloads=selected_single_core_workloads,
                prefix="lw",
                log_root=log_root,
                json_root=json_root,
                binary_path_builder=lambda prefetcher, ways=reserved_ways: limited_way_mod.binary_path(prefetcher, ways),
                skip_missing=True,
                skip_completed=args.skip_completed,
                run_label=f"limited-way-{reserved_ways}way",
                env_builder=limited_way_mod.build_env,
            )
            suites.append(
                SuiteRunner(
                    name=f"limited-way-{reserved_ways}way",
                    pending=deque(tasks),
                    launch_task=single_core_launch,
                    describe_task=lambda task: f"{task.prefetcher}/{task.trace_name}",
                    max_attempts=limited_defaults.retries + 1,
                    skipped_missing=skipped_missing,
                    skipped_completed=skipped_completed_runs,
                    total=len(tasks),
                )
            )

    if not args.skip_storage:
        storage_defaults = storage_mod.parse_args([])
        storage_count = _resolve_count(storage_mod.default_workload_count())
        tasks, skipped_missing, skipped_completed_runs = storage_mod.prepare_tasks(
            prefetchers=list(dict.fromkeys(storage_defaults.prefetchers)),
            prefix="stor",
            warmup=args.warmup,
            simulation=args.simulation,
            begin=0,
            count=storage_count,
            skip_missing=True,
            skip_completed=args.skip_completed,
        )
        suites.append(
            SuiteRunner(
                name="storage-sensitivity",
                pending=deque(tasks),
                launch_task=storage_mod.launch_task,
                describe_task=lambda task: f"{task.prefetcher}/{task.trace_name}",
                max_attempts=storage_defaults.retries + 1,
                skipped_missing=skipped_missing,
                skipped_completed=skipped_completed_runs,
                total=len(tasks),
            )
        )

    if not args.skip_system:
        system_defaults = system_mod.parse_args([])
        system_count = _resolve_count(system_mod.default_workload_count())
        tasks, skipped_missing, skipped_completed_runs = system_mod.prepare_tasks(
            prefetchers=list(dict.fromkeys(system_defaults.prefetchers)),
            prefix="sys",
            warmup=args.warmup,
            simulation=args.simulation,
            begin=0,
            count=system_count,
            skip_missing=True,
            skip_completed=args.skip_completed,
        )
        suites.append(
            SuiteRunner(
                name="system-sensitivity",
                pending=deque(tasks),
                launch_task=system_mod.launch_task,
                describe_task=lambda task: f"{task.prefetcher}/bw{task.bw}_l2{task.l2c}_llc{task.llc}/{task.trace_name}",
                max_attempts=system_defaults.retries + 1,
                skipped_missing=skipped_missing,
                skipped_completed=skipped_completed_runs,
                total=len(tasks),
            )
        )

    if not args.skip_multi_core:
        multi_defaults = multi_core_mod.parse_args([])
        homo_prefix = args.prefix if args.prefix != "mc" else "homo"
        homo_count = _resolve_count(multi_core_mod.default_workload_count())
        tasks, skipped_missing, skipped_completed_runs = multi_core_mod.prepare_tasks(
            num_cores=None,
            prefetchers=list(dict.fromkeys(multi_defaults.prefetchers)),
            prefix=homo_prefix,
            warmup=args.warmup,
            simulation=args.simulation,
            begin=0,
            count=homo_count,
            heterogeneous=False,
            skip_missing=True,
            skip_completed=args.skip_completed,
        )
        suites.append(
            SuiteRunner(
                name="multi-core-homo",
                pending=deque(tasks),
                launch_task=multi_core_mod.launch_task,
                describe_task=lambda task: f"{task.prefetcher}/{task.num_cores}c/{task.trace_label}",
                max_attempts=multi_defaults.retries + 1,
                skipped_missing=skipped_missing,
                skipped_completed=skipped_completed_runs,
                total=len(tasks),
            )
        )

    if not args.skip_multi_core_hetero:
        multi_defaults = multi_core_mod.parse_args([])
        heter_count = _resolve_count(multi_core_mod.default_heterogeneous_workload_count(args.hetero_cores))
        tasks, skipped_missing, skipped_completed_runs = multi_core_mod.prepare_tasks(
            num_cores=args.hetero_cores,
            prefetchers=list(dict.fromkeys(multi_defaults.prefetchers)),
            prefix="het",
            warmup=args.warmup,
            simulation=args.simulation,
            begin=0,
            count=heter_count,
            heterogeneous=True,
            skip_missing=True,
            skip_completed=args.skip_completed,
        )
        suites.append(
            SuiteRunner(
                name="multi-core-heter",
                pending=deque(tasks),
                launch_task=multi_core_mod.launch_task,
                describe_task=lambda task: f"{task.prefetcher}/{task.num_cores}c/{task.trace_label}",
                max_attempts=multi_defaults.retries + 1,
                skipped_missing=skipped_missing,
                skipped_completed=skipped_completed_runs,
                total=len(tasks),
            )
        )

    enabled_suites = [suite for suite in suites if suite.total > 0 or suite.skipped_missing > 0 or suite.skipped_completed > 0]
    if not enabled_suites:
        print("[run-all] No suites enabled.", file=sys.stderr, flush=True)
        return 0

    for suite in enabled_suites:
        print(
            f"[run-all] Prepared {suite.name}: queued={suite.total}, skipped_missing={suite.skipped_missing}, "
            f"skipped_completed={suite.skipped_completed}, max_attempts={suite.max_attempts}",
            file=sys.stderr,
            flush=True,
        )

    failed = _launch_global_queue(
        suites=enabled_suites,
        warmup=args.warmup,
        simulation=args.simulation,
        max_jobs=args.max_jobs,
        poll_seconds=args.poll_seconds,
    )
    if failed:
        print(f"[run-all] Completed with failures: {failed} tasks failed.", file=sys.stderr, flush=True)
        return 1

    print("[run-all] Completed all requested runs.", file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
