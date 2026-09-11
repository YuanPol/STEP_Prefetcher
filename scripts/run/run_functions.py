from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List, Mapping, Optional, Sequence

from experiment_utils import (
    CHAMPSIM_DIR,
    artifact_paths,
    is_completed_run,
    multicore_result_roots,
    single_core_result_roots,
    step_trace_dir,
)
from workloads import (
    workloads_all,
    workloads_all_2core_heterogeneous,
    workloads_all_4core_heterogeneous,
    workloads_all_8core_heterogeneous,
)


REPO_ROOT = CHAMPSIM_DIR.parent


def _launch(
    *,
    binary_name: str,
    log_path: Path,
    json_path: Path,
    trace_files: Sequence[str],
    compressed_trace: bool,
    num_warmup: int,
    num_simulation: int,
    extra_env: Optional[Mapping[str, str]] = None,
) -> None:
    binary_path = CHAMPSIM_DIR / "bin" / binary_name
    if not binary_path.exists():
        raise FileNotFoundError(f"Binary not found: {binary_path}")

    command: List[str] = [
        str(binary_path),
        f"--json={json_path}",
        "--warmup_instructions",
        str(num_warmup),
        "--simulation_instructions",
        str(num_simulation),
    ]
    if compressed_trace:
        command.append("-c")
    command.extend(trace_files)

    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("w")
    subprocess.Popen(
        command,
        cwd=CHAMPSIM_DIR,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )


def _trace_path(trace_file: str) -> str:
    path = REPO_ROOT / "traces" / trace_file
    if not path.exists():
        raise FileNotFoundError(f"Trace not found: {path}")
    return str(path)


def run_1core(
    prefetcher: str,
    prefix: str,
    num_warmup: int,
    num_simulation: int,
    begin: int,
    num: int,
    *,
    experiment: str = "l1_level",
    skip_completed: bool = True,
) -> None:
    log_root, json_root = single_core_result_roots("l1", experiment, num_warmup, num_simulation)
    binary_name = f"champsim_1core_{prefetcher}"

    for trace_file, trace_name, compressed_trace in workloads_all[begin : begin + num]:
        log_path, json_path = artifact_paths(log_root, prefetcher, prefix, trace_name)
        if skip_completed and is_completed_run(log_path, json_path):
            continue
        _launch(
            binary_name=binary_name,
            log_path=log_path,
            json_path=json_path,
            trace_files=[_trace_path(trace_file)],
            compressed_trace=compressed_trace,
            num_warmup=num_warmup,
            num_simulation=num_simulation,
        )


def run_1core_l2(
    prefetcher: str,
    prefix: str,
    num_warmup: int,
    num_simulation: int,
    begin: int,
    num: int,
    *,
    experiment: str = "single_core_performance",
    skip_completed: bool = True,
) -> None:
    log_root, json_root = single_core_result_roots("l2", experiment, num_warmup, num_simulation)
    binary_name = f"champsim_1core_l2_{prefetcher}"
    trace_root = step_trace_dir(log_root, prefetcher) if "step" in prefetcher else None

    for trace_file, trace_name, compressed_trace in workloads_all[begin : begin + num]:
        log_path, json_path = artifact_paths(log_root, prefetcher, prefix, trace_name)
        if skip_completed and is_completed_run(log_path, json_path):
            continue

        extra_env = None
        if trace_root is not None:
            extra_env = {
                "STEP_TRACE_OUTPUT_DIR": str(trace_root),
                "STEP_TRACE_BASENAME": f"{prefix}-{trace_name}",
            }

        _launch(
            binary_name=binary_name,
            log_path=log_path,
            json_path=json_path,
            trace_files=[_trace_path(trace_file)],
            compressed_trace=compressed_trace,
            num_warmup=num_warmup,
            num_simulation=num_simulation,
            extra_env=extra_env,
        )


def run_1core_l2_system_sensitivity(
    prefetcher: str,
    bw: int,
    l2c_size: float,
    llc_size: float,
    prefix: str,
    num_warmup: int,
    num_simulation: int,
    begin: int,
    num: int,
    *,
    experiment: str = "system_parameter_experiment",
    skip_completed: bool = True,
) -> None:
    tag = f"{prefetcher}_bw_{bw}_l2c_{l2c_size}_llc_{llc_size}"
    log_root, json_root = single_core_result_roots("l2", experiment, num_warmup, num_simulation)
    binary_name = f"champsim_1core_l2_{tag}"

    for trace_file, trace_name, compressed_trace in workloads_all[begin : begin + num]:
        log_path, json_path = artifact_paths(log_root, tag, prefix, trace_name)
        if skip_completed and is_completed_run(log_path, json_path):
            continue
        _launch(
            binary_name=binary_name,
            log_path=log_path,
            json_path=json_path,
            trace_files=[_trace_path(trace_file)],
            compressed_trace=compressed_trace,
            num_warmup=num_warmup,
            num_simulation=num_simulation,
        )


def run_multicore_homo_l2(
    num_cores: int,
    prefetcher: str,
    prefix: str,
    num_warmup: int,
    num_simulation: int,
    begin: int,
    num: int,
    *,
    skip_completed: bool = True,
) -> None:
    log_root, json_root = multicore_result_roots("homo", num_cores, num_warmup, num_simulation)
    binary_name = f"champsim_{num_cores}core_l2_{prefetcher}"

    for trace_file, trace_name, compressed_trace in workloads_all[begin : begin + num]:
        log_path, json_path = artifact_paths(log_root, prefetcher, prefix, trace_name)
        if skip_completed and is_completed_run(log_path, json_path):
            continue
        traces = [_trace_path(trace_file) for _ in range(num_cores)]
        _launch(
            binary_name=binary_name,
            log_path=log_path,
            json_path=json_path,
            trace_files=traces,
            compressed_trace=compressed_trace,
            num_warmup=num_warmup,
            num_simulation=num_simulation,
        )


def run_multicore_hete_l2(
    num_cores: int,
    prefetcher: str,
    prefix: str,
    num_warmup: int,
    num_simulation: int,
    begin: int,
    num: int,
    *,
    skip_completed: bool = True,
) -> None:
    hetero_workloads = {
        2: workloads_all_2core_heterogeneous,
        4: workloads_all_4core_heterogeneous,
        8: workloads_all_8core_heterogeneous,
    }.get(num_cores)
    if hetero_workloads is None:
        raise ValueError(f"Unsupported heterogeneous core count: {num_cores}")

    log_root, json_root = multicore_result_roots("heter", num_cores, num_warmup, num_simulation)
    binary_name = f"champsim_{num_cores}core_l2_{prefetcher}"

    for workload in hetero_workloads[begin : begin + num]:
        trace_files = [_trace_path(entry[0]) for entry in workload]
        trace_name = "-".join(entry[1] for entry in workload)
        compressed_trace = any(entry[2] for entry in workload)
        log_path, json_path = artifact_paths(log_root, prefetcher, prefix, trace_name)
        if skip_completed and is_completed_run(log_path, json_path):
            continue
        _launch(
            binary_name=binary_name,
            log_path=log_path,
            json_path=json_path,
            trace_files=trace_files,
            compressed_trace=compressed_trace,
            num_warmup=num_warmup,
            num_simulation=num_simulation,
        )
