from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[2]
CHAMPSIM_DIR = REPO_ROOT / "ChampSim"

SIM_DONE_MARKERS = (
    b"ChampSim completed all CPUs",
    b"Simulation complete CPU 0 instructions",
)


def single_core_result_roots(
    level: str,
    experiment: str,
    warmup: int,
    simulation: int,
) -> Tuple[Path, Path]:
    if level not in {"l1", "l2"}:
        raise ValueError(f"Unsupported single-core level: {level}")

    suffix = f"withwarm_{warmup}_withsim_{simulation}"
    log_root = REPO_ROOT / "log" / level / experiment / suffix
    json_root = REPO_ROOT / "json" / level / experiment / suffix
    return log_root, json_root


def multicore_result_roots(
    mode: str,
    num_cores: int,
    warmup: int,
    simulation: int,
) -> Tuple[Path, Path]:
    if mode not in {"homo", "heter"}:
        raise ValueError(f"Unsupported multicore mode: {mode}")

    suffix = f"withwarm_{warmup}_withsim_{simulation}"
    core_dir = f"{num_cores}core_l2"
    log_root = REPO_ROOT / "log" / "multicore" / mode / core_dir / suffix
    json_root = REPO_ROOT / "json" / "multicore" / mode / core_dir / suffix
    return log_root, json_root


def artifact_paths(root: Path, prefetcher: str, prefix: str, trace_label: str) -> Tuple[Path, Path]:
    prefetcher_root = root / prefetcher
    prefetcher_root.mkdir(parents=True, exist_ok=True)
    return (
        prefetcher_root / f"{prefix}-{trace_label}.log",
        prefetcher_root / f"{prefix}-{trace_label}.json",
    )


def step_trace_dir(root: Path, prefetcher: str) -> Path:
    trace_root = root / prefetcher / "step_trace"
    trace_root.mkdir(parents=True, exist_ok=True)
    return trace_root


def _file_contains_marker(path: Path, marker: bytes) -> bool:
    if not path.exists():
        return False

    carry = b""
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                combined = carry + chunk
                if marker in combined:
                    return True
                keep = len(marker) - 1
                carry = combined[-keep:] if keep > 0 else b""
    except OSError:
        return False

    return False


def _json_is_complete(json_path: Path) -> bool:
    if not json_path.exists() or json_path.stat().st_size <= 0:
        return False

    try:
        with json_path.open("r", encoding="utf-8") as handle:
            json.load(handle)
    except (OSError, json.JSONDecodeError):
        return False

    return True


def is_completed_run(log_path: Path, json_path: Path) -> bool:
    if not log_path.exists() or log_path.stat().st_size <= 0:
        return False
    if not _json_is_complete(json_path):
        return False

    return True


def normalise_trace_label(stem: str) -> str:
    return stem.split("-", 1)[1] if "-" in stem else stem


def default_single_core_baseline_roots(
    warmup: int,
    simulation: int,
) -> Tuple[Path, Path]:
    return single_core_result_roots("l2", "single_core_performance", warmup, simulation)
