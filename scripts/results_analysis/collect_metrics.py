#!/usr/bin/env python3
"""
Collect derived metrics from ChampSim log and/or JSON outputs.

The script walks result directories, extracts per-trace statistics such as IPC,
speedup, coverage, prefetch accuracy (two definitions), and mechanism-specific
breakdowns required for the STEP prefetcher analysis.

Example usage:
    python collect_metrics.py \
        --log-root ../../log/1core_l2/withwarm_0_withsim_200000000 \
        --json-root ../../json/1core_l2/withwarm_0_withsim_200000000 \
        --baseline no \
        --output out.csv
"""

import argparse
import csv
import json
import math
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Sequence


# ---------- Helpers ----------


DEFAULT_LOG_TAIL_LINES = 5000


def safe_div(numerator: float, denominator: float) -> float:
    """Return numerator / denominator or 0.0 if denominator is zero."""
    if denominator == 0:
        return 0.0
    return numerator / denominator


def geometric_mean(values: Iterable[float]) -> float:
    """Return the geometric mean of positive values."""
    vals = [v for v in values if v > 0]
    if not vals:
        return 0.0
    log_sum = sum(math.log(v) for v in vals)
    return math.exp(log_sum / len(vals))


def geometric_mean_strict(values: Iterable[float]) -> float:
    """
    Return geometric mean across all values.

    Unlike ``geometric_mean``, this requires every value to be strictly
    positive. If any value is zero/negative (or the iterable is empty), the
    result is ``0.0``.
    """
    vals = [float(v) for v in values]
    if not vals:
        return 0.0
    if any(v <= 0 for v in vals):
        return 0.0
    log_sum = sum(math.log(v) for v in vals)
    return math.exp(log_sum / len(vals))


def normalize_label(raw: str) -> str:
    """Normalise mechanism labels into snake_case keys."""
    label = raw.strip().lower().replace("/", "_").replace(" ", "_")
    if label.endswith("_prefetch"):
        label = label[: -len("_prefetch")]
    if label == "prefetch":
        return "overall"
    return label


def sanitise_cache_name(name: str) -> str:
    """Convert cache names into safe column prefixes."""
    return name.replace("->", "_").replace("/", "_")


def normalize_trace_id(raw: str) -> str:
    """Strip the experiment/run prefix from a trace identifier."""
    return raw.split("-", 1)[-1] if "-" in raw else raw


def sum_counter(value) -> int:
    """Accept scalar or per-core counter payloads from ChampSim JSON."""
    if isinstance(value, list):
        return sum(int(item) for item in value)
    if isinstance(value, dict):
        return sum(int(item) for item in value.values())
    if value is None:
        return 0
    return int(value)


def iter_log_lines(log_path: Path, tail_lines: Optional[int]) -> Iterable[str]:
    """
    Yield log lines, optionally restricted to the last ``tail_lines`` lines.

    When ``tail_lines`` is ``None`` or <= 0, the whole file is streamed.
    Otherwise only the file tail is read by seeking from the end, which avoids
    scanning large multicore logs in full.
    """
    if tail_lines is None or tail_lines <= 0:
        with log_path.open("r", encoding="utf-8", errors="ignore") as handle:
            yield from handle
        return

    chunk_size = 1 << 20
    with log_path.open("rb") as handle:
        handle.seek(0, 2)
        file_size = handle.tell()
        position = file_size
        newline_count = 0
        buffer = b""

        while position > 0 and newline_count <= tail_lines:
            read_size = min(chunk_size, position)
            position -= read_size
            handle.seek(position)
            chunk = handle.read(read_size)
            buffer = chunk + buffer
            newline_count += chunk.count(b"\n")

        lines = buffer.splitlines()
        if len(lines) > tail_lines:
            lines = lines[-tail_lines:]

        for line in lines:
            yield line.decode("utf-8", errors="ignore")


VIRTUAL_CACHE_SPECS = {
    # For L1 experiments that prefetch into both L1D and L2C, use combined
    # prefetch outcomes for accuracy while evaluating coverage from LLC misses.
    "cpu0_L1D_L2C": {
        "prefetch_sources": ("cpu0_L1D", "cpu0_L2C"),
        "demand_sources": ("cpu0_LLC", "LLC"),
    }
}


@dataclass
class MechanismStats:
    requested: int = 0
    issued: int = 0
    useful: int = 0
    useless: int = 0
    fill: int = 0
    late: int = 0

    def update(self, **kwargs: int) -> None:
        for key, value in kwargs.items():
            if hasattr(self, key):
                current = getattr(self, key)
                setattr(self, key, max(current, int(value)))

    def accuracy_useful_total(self) -> float:
        total = self.useful + self.useless
        return safe_div(self.useful, total)

    def accuracy_useful_issued(self) -> float:
        return safe_div(self.useful, self.issued)


@dataclass
class CacheStats:
    load_access: int = 0
    load_hit: int = 0
    load_miss: int = 0
    prefetch_access: int = 0
    prefetch_hit: int = 0
    prefetch_miss: int = 0
    overall: MechanismStats = field(default_factory=MechanismStats)
    mechanisms: Dict[str, MechanismStats] = field(default_factory=dict)

    def ensure_mechanism(self, label: str) -> MechanismStats:
        if label not in self.mechanisms:
            self.mechanisms[label] = MechanismStats()
        return self.mechanisms[label]


@dataclass
class RunRecord:
    prefetcher: str
    trace: str
    cpu_stats: Dict[int, Tuple[int, int]] = field(default_factory=dict)
    per_core_ipc: Dict[int, float] = field(default_factory=dict)
    per_core_speedup: Dict[int, float] = field(default_factory=dict)
    ipc: float = 0.0
    total_instructions: int = 0
    total_cycles: int = 0
    runtime_cycles: int = 0
    caches: Dict[str, CacheStats] = field(default_factory=dict)
    coverage: Dict[str, float] = field(default_factory=dict)
    speedup: float = 0.0
    sources: Dict[str, List[str]] = field(default_factory=lambda: defaultdict(list))

    def cache(self, name: str) -> CacheStats:
        if name not in self.caches:
            self.caches[name] = CacheStats()
        return self.caches[name]

    def finalise_ipc(self) -> None:
        if not self.cpu_stats:
            self.ipc = 0.0
            self.total_instructions = 0
            self.total_cycles = 0
            self.runtime_cycles = 0
            return
        self.total_instructions = sum(inst for inst, _ in self.cpu_stats.values())
        self.total_cycles = sum(cyc for _, cyc in self.cpu_stats.values())
        self.runtime_cycles = max(cyc for _, cyc in self.cpu_stats.values())
        self.ipc = safe_div(self.total_instructions, self.total_cycles)
        self.per_core_ipc = {core: safe_div(inst, cyc) for core, (inst, cyc) in self.cpu_stats.items()}


# ---------- Parsing ----------


CPU_SUMMARY_RE = re.compile(
    r"CPU\s+(?P<cpu>\d+)\s+cumulative IPC:\s+(?P<ipc>[0-9.]+)\s+instructions:\s+(?P<inst>\d+)\s+cycles:\s+(?P<cycles>\d+)"
)

SIM_FINISH_RE = re.compile(
    r"Simulation finished CPU\s+(?P<cpu>\d+)\s+instructions:\s+(?P<inst>\d+)\s+cycles:\s+(?P<cycles>\d+)\s+cumulative IPC:\s+(?P<ipc>[0-9.]+)"
)

CACHE_ACCESS_RE = re.compile(
    r"cpu(?P<cpu>\d+)->(?P<cache>\S+)\s+(?P<kind>LOAD|PREFETCH)\s+ACCESS:\s+(?P<access>\d+)\s+HIT:\s+(?P<hit>\d+)\s+MISS:\s+(?P<miss>\d+)"
)

PREFETCH_REQ_RE = re.compile(
    r"cpu(?P<cpu>\d+)->(?P<cache>\S+)\s+(?P<label>[A-Z ]*PREFETCH)\s+(?:REQUESTED|REQ):\s+(?P<requested>\d+)\s+ISSUED:\s+(?P<issued>\d+)\s+USEFUL:\s+(?P<useful>\d+)\s+USELESS:\s+(?P<useless>\d+)(?:\s+FILL:\s+(?P<fill>\d+)\s+LATE:\s+(?P<late>\d+))?"
)

PREFETCH_FILL_RE = re.compile(
    r"cpu(?P<cpu>\d+)->(?P<cache>\S+)\s+(?P<label>[A-Z ]*PREFETCH)\s+FILL:\s+(?P<fill>\d+)\s+LATE:\s+(?P<late>\d+)"
)


def parse_log_file(log_path: Path, run: "RunRecord", tail_lines: Optional[int] = DEFAULT_LOG_TAIL_LINES) -> None:
    """Populate run record using a ChampSim log."""
    run.sources["log"].append(str(log_path))
    try:
        for line in iter_log_lines(log_path, tail_lines):
            cpu_match = CPU_SUMMARY_RE.search(line)
            if cpu_match:
                cpu_idx = int(cpu_match.group("cpu"))
                inst = int(cpu_match.group("inst"))
                cyc = int(cpu_match.group("cycles"))
                run.cpu_stats[cpu_idx] = (inst, cyc)
                continue

            sim_finish_match = SIM_FINISH_RE.search(line)
            if sim_finish_match:
                cpu_idx = int(sim_finish_match.group("cpu"))
                inst = int(sim_finish_match.group("inst"))
                cyc = int(sim_finish_match.group("cycles"))
                run.cpu_stats[cpu_idx] = (inst, cyc)
                continue

            cache_match = CACHE_ACCESS_RE.search(line)
            if cache_match:
                cache_name = cache_match.group("cache")
                kind = cache_match.group("kind")
                stats = run.cache(cache_name)
                access = int(cache_match.group("access"))
                hit = int(cache_match.group("hit"))
                miss = int(cache_match.group("miss"))
                if kind == "LOAD":
                    stats.load_access = access
                    stats.load_hit = hit
                    stats.load_miss = miss
                else:
                    stats.prefetch_access = access
                    stats.prefetch_hit = hit
                    stats.prefetch_miss = miss
                continue

            req_match = PREFETCH_REQ_RE.search(line)
            if req_match:
                cache_name = req_match.group("cache")
                label = normalize_label(req_match.group("label"))
                stats = run.cache(cache_name)
                target = stats.overall if label == "overall" else stats.ensure_mechanism(label)
                target.update(
                    requested=int(req_match.group("requested")),
                    issued=int(req_match.group("issued")),
                    useful=int(req_match.group("useful")),
                    useless=int(req_match.group("useless")),
                )
                if req_match.group("fill"):
                    target.fill = max(target.fill, int(req_match.group("fill")))
                if req_match.group("late"):
                    target.late = max(target.late, int(req_match.group("late")))
                continue

            fill_match = PREFETCH_FILL_RE.search(line)
            if fill_match:
                cache_name = fill_match.group("cache")
                label = normalize_label(fill_match.group("label"))
                stats = run.cache(cache_name)
                target = stats.overall if label == "overall" else stats.ensure_mechanism(label)
                target.fill = max(target.fill, int(fill_match.group("fill")))
                target.late = max(target.late, int(fill_match.group("late")))
                continue
    except FileNotFoundError:
        return


def parse_json_payload(data, run: "RunRecord") -> None:
    """Populate run record using ChampSim JSON content (dict or list)."""
    if isinstance(data, list) and data:
        root = data[0]
    elif isinstance(data, dict):
        root = data
    else:
        return

    roi = root.get("roi") or root.get("sim") or {}
    cores = roi.get("cores", [])
    for idx, core in enumerate(cores):
        inst = int(core.get("instructions", 0))
        cyc = int(core.get("cycles", 0))
        run.cpu_stats[idx] = (inst, cyc)

    for cache_name, payload in roi.items():
        if cache_name in {"cores", "DRAM", "traces"}:
            continue
        if not isinstance(payload, dict):
            continue

        stats = run.cache(cache_name)

        load_info = payload.get("LOAD")
        if isinstance(load_info, dict):
            hit = sum_counter(load_info.get("hit", 0))
            miss = sum_counter(load_info.get("miss", 0))
            stats.load_hit = hit
            stats.load_miss = miss
            stats.load_access = hit + miss

        prefetch_info = payload.get("PREFETCH")
        if isinstance(prefetch_info, dict):
            hit = sum_counter(prefetch_info.get("hit", 0))
            miss = sum_counter(prefetch_info.get("miss", 0))
            stats.prefetch_hit = hit
            stats.prefetch_miss = miss
            stats.prefetch_access = hit + miss

        if "prefetch requested" in payload:
            stats.overall.requested = max(stats.overall.requested, int(payload.get("prefetch requested", 0)))
        if "prefetch issued" in payload:
            stats.overall.issued = max(stats.overall.issued, int(payload.get("prefetch issued", 0)))

        useful_value = payload.get("useful prefetch", payload.get("prefetch useful"))
        if useful_value is not None:
            stats.overall.useful = max(stats.overall.useful, int(useful_value))

        useless_value = payload.get("useless prefetch", payload.get("prefetch useless"))
        if useless_value is not None:
            stats.overall.useless = max(stats.overall.useless, int(useless_value))

        fill_value = payload.get("prefetch fill", payload.get("prefetch filled"))
        if fill_value is not None:
            stats.overall.fill = max(stats.overall.fill, int(fill_value))

        late_value = payload.get("late prefetch", payload.get("prefetch late"))
        if late_value is not None:
            stats.overall.late = max(stats.overall.late, int(late_value))

        for json_label in ("stride", "first offset", "second offset", "third offset", "stream"):
            target = stats.ensure_mechanism(normalize_label(json_label))
            for attribute, suffix in (
                ("requested", "requested"),
                ("issued", "issued"),
                ("fill", "filled"),
                ("useful", "useful"),
                ("useless", "useless"),
                ("late", "late"),
            ):
                key = f"{json_label} prefetch {suffix}"
                if key in payload:
                    setattr(target, attribute, max(getattr(target, attribute), sum_counter(payload[key])))

        lower_level_useful = int(payload.get("pf_useful_at_l2_from_l1", 0))
        lower_level_useless = int(payload.get("pf_useless_at_l2_from_l1", 0))
        lower_level_late = int(payload.get("pf_late_at_l2_from_l1", 0))
        lower_level_fill = int(payload.get("pf_fill_this_level", 0))
        if (
            stats.overall.requested == 0
            and stats.overall.issued == 0
            and (lower_level_useful or lower_level_useless or lower_level_late or lower_level_fill)
        ):
            derived_issued = lower_level_fill if lower_level_fill > 0 else (lower_level_useful + lower_level_useless)
            stats.overall.requested = max(stats.overall.requested, derived_issued)
            stats.overall.issued = max(stats.overall.issued, derived_issued)
            stats.overall.useful = max(stats.overall.useful, lower_level_useful)
            stats.overall.useless = max(stats.overall.useless, lower_level_useless)
            stats.overall.late = max(stats.overall.late, lower_level_late)


def parse_json_file(json_path: Path, run: "RunRecord") -> None:
    """Populate run record using ChampSim JSON output."""
    run.sources["json"].append(str(json_path))
    try:
        with json_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return

    parse_json_payload(data, run)


# ---------- Collection ----------


def init_run(prefetcher: str, trace: str) -> "RunRecord":
    return RunRecord(prefetcher=prefetcher, trace=trace)


def populate_virtual_caches(record: "RunRecord") -> None:
    for virtual_name, spec in VIRTUAL_CACHE_SPECS.items():
        prefetch_sources = [record.caches[name] for name in spec["prefetch_sources"] if name in record.caches]
        demand_stats = None
        for demand_name in spec.get("demand_sources", ()):
            demand_stats = record.caches.get(demand_name)
            if demand_stats is not None:
                break
        if demand_stats is None and prefetch_sources:
            demand_stats = prefetch_sources[0]
        if demand_stats is None and not prefetch_sources:
            continue

        combined = CacheStats()
        if demand_stats is not None:
            combined.load_access = demand_stats.load_access
            combined.load_hit = demand_stats.load_hit
            combined.load_miss = demand_stats.load_miss

        for stats in prefetch_sources:
            combined.prefetch_access += stats.prefetch_access
            combined.prefetch_hit += stats.prefetch_hit
            combined.prefetch_miss += stats.prefetch_miss
            combined.overall.requested += stats.overall.requested
            combined.overall.issued += stats.overall.issued
            combined.overall.useful += stats.overall.useful
            combined.overall.useless += stats.overall.useless
            combined.overall.fill += stats.overall.fill
            combined.overall.late += stats.overall.late

            for mech, mech_stats in stats.mechanisms.items():
                target = combined.ensure_mechanism(mech)
                target.requested += mech_stats.requested
                target.issued += mech_stats.issued
                target.useful += mech_stats.useful
                target.useless += mech_stats.useless
                target.fill += mech_stats.fill
                target.late += mech_stats.late

        record.caches[virtual_name] = combined


def collect_runs(
    log_root: Optional[Path],
    json_root: Optional[Path],
    include_prefetchers: Optional[Iterable[str]],
    program_filter: Optional[Iterable[str]],
    verbose: bool,
    log_tail_lines: Optional[int] = DEFAULT_LOG_TAIL_LINES,
) -> Dict[Tuple[str, str], "RunRecord"]:
    runs: Dict[Tuple[str, str], "RunRecord"] = {}

    def should_skip(prefetcher: str, trace: str) -> bool:
        if include_prefetchers and prefetcher not in include_prefetchers:
            return True
        if program_filter and trace not in program_filter:
            return True
        return False

    if json_root:
        for prefetch_dir in sorted(json_root.glob("*")):
            if not prefetch_dir.is_dir():
                continue
            prefetcher = prefetch_dir.name
            for json_file in sorted(prefetch_dir.glob("*.json")):
                trace = json_file.stem
                if should_skip(prefetcher, trace):
                    continue
                key = (prefetcher, trace)
                run = runs.setdefault(key, init_run(prefetcher, trace))
                parse_json_file(json_file, run)

    if log_root:
        for prefetch_dir in sorted(log_root.glob("*")):
            if not prefetch_dir.is_dir():
                continue
            prefetcher = prefetch_dir.name
            for log_file in sorted(prefetch_dir.glob("*.log")):
                trace = log_file.stem
                if should_skip(prefetcher, trace):
                    continue
                key = (prefetcher, trace)
                run = runs.setdefault(key, init_run(prefetcher, trace))
                parse_log_file(log_file, run, tail_lines=log_tail_lines)

    if verbose:
        print(f"[collect] Parsed {len(runs)} traces", file=sys.stderr)
    return runs


def compute_derived_metrics(runs: Dict[Tuple[str, str], "RunRecord"], baseline: str) -> None:
    baseline_map: Dict[str, "RunRecord"] = {}
    normalized_baseline_map: Dict[str, List["RunRecord"]] = defaultdict(list)
    for record in runs.values():
        record.finalise_ipc()
        populate_virtual_caches(record)
        if record.prefetcher == baseline:
            baseline_map[record.trace] = record
            normalized_baseline_map[normalize_trace_id(record.trace)].append(record)

    for key, record in runs.items():
        base = baseline_map.get(record.trace)
        if base is None:
            candidates = normalized_baseline_map.get(normalize_trace_id(record.trace), [])
            if len(candidates) == 1:
                base = candidates[0]
            elif len(candidates) > 1:
                same_core_count = [cand for cand in candidates if len(cand.cpu_stats) == len(record.cpu_stats)]
                if len(same_core_count) == 1:
                    base = same_core_count[0]
                elif same_core_count:
                    exact_instruction_matches = [
                        cand for cand in same_core_count if cand.total_instructions == record.total_instructions
                    ]
                    if len(exact_instruction_matches) == 1:
                        base = exact_instruction_matches[0]

        record.per_core_speedup = {}
        if base is None:
            record.speedup = 0.0
        elif base is record:
            record.speedup = 1.0
            record.per_core_speedup = {core: 1.0 for core in record.cpu_stats}
            record.coverage = {name: 0.0 for name in record.caches}
        else:
            # Multi-core speedup definition:
            # 1) compute per-core speedup vs baseline
            # 2) geometric-mean those per-core speedups for the workload group
            # This avoids max-time based aggregation.
            baseline_cores = sorted(base.cpu_stats.keys())
            for core in baseline_cores:
                base_stats = base.cpu_stats.get(core)
                run_stats = record.cpu_stats.get(core)
                if not base_stats or not run_stats:
                    record.per_core_speedup[core] = 0.0
                    continue

                _, base_cyc = base_stats
                _, cyc = run_stats
                record.per_core_speedup[core] = safe_div(base_cyc, cyc) if (base_cyc > 0 and cyc > 0) else 0.0

            record.speedup = geometric_mean_strict(record.per_core_speedup.values())
            record.coverage = {}
            for cache_name, stats in record.caches.items():
                base_stats = base.caches.get(cache_name)
                if not base_stats:
                    continue
                base_miss = base_stats.load_miss
                miss = stats.load_miss
                record.coverage[cache_name] = safe_div(
                    base_miss - miss, base_miss
                ) if base_miss else 0.0


# ---------- Output ----------


def build_output_rows(
    runs: Dict[Tuple[str, str], "RunRecord"], force_cache_prefixes: Optional[Sequence[str]] = None
) -> Tuple[List[str], List[Dict[str, object]]]:
    max_core_idx = -1
    for record in runs.values():
        if record.cpu_stats:
            max_core_idx = max(max_core_idx, max(record.cpu_stats.keys()))
    num_cores = max_core_idx + 1 if max_core_idx >= 0 else 0

    cache_names = {
        name
        for record in runs.values()
        for name in record.caches
        if any(tag in name for tag in ("L1", "L2", "LLC"))
    }
    if force_cache_prefixes:
        cache_names.update(force_cache_prefixes)
    cache_names = sorted(cache_names)
    mechanism_keys = sorted(
        {
            (cache, mech)
            for record in runs.values()
            for cache, stats in record.caches.items()
            if cache in cache_names
            for mech in stats.mechanisms
        }
    )

    columns: List[str] = [
        "prefetcher",
        "trace",
        "total_instructions",
        "total_cycles",
        "ipc",
        "speedup",
    ]

    for core in range(num_cores):
        columns.extend(
            [
                f"core{core}_instructions",
                f"core{core}_cycles",
                f"core{core}_ipc",
                f"core{core}_speedup",
            ]
        )
    if num_cores:
        columns.append("geom_mean_core_speedup")

    for cache_name in cache_names:
        cache_col = sanitise_cache_name(cache_name)
        columns.extend(
            [
                f"{cache_col}_load_access",
                f"{cache_col}_load_miss",
                f"{cache_col}_prefetch_access",
                f"{cache_col}_prefetch_hit",
                f"{cache_col}_prefetch_miss",
                f"{cache_col}_prefetch_requested",
                f"{cache_col}_prefetch_issued",
                f"{cache_col}_prefetch_useful",
                f"{cache_col}_prefetch_useless",
                f"{cache_col}_prefetch_fill",
                f"{cache_col}_prefetch_late",
                f"{cache_col}_accuracy_useful_total",
                f"{cache_col}_accuracy_useful_issued",
                f"coverage_{cache_col}",
            ]
        )

    for cache_name, mech in mechanism_keys:
        cache_col = sanitise_cache_name(cache_name)
        columns.extend(
            [
                f"{cache_col}_{mech}_requested",
                f"{cache_col}_{mech}_issued",
                f"{cache_col}_{mech}_useful",
                f"{cache_col}_{mech}_useless",
                f"{cache_col}_{mech}_fill",
                f"{cache_col}_{mech}_late",
                f"{cache_col}_{mech}_accuracy_useful_total",
                f"{cache_col}_{mech}_accuracy_useful_issued",
            ]
        )

    rows: List[Dict[str, object]] = []
    for key in sorted(runs.keys()):
        record = runs[key]
        row: Dict[str, object] = {
            "prefetcher": record.prefetcher,
            "trace": record.trace,
            "total_instructions": record.total_instructions,
            "total_cycles": record.total_cycles,
            "ipc": record.ipc,
            "speedup": record.speedup,
        }

        core_speedups: List[float] = []
        for core in range(num_cores):
            inst_cyc = record.cpu_stats.get(core, (0, 0))
            inst, cyc = inst_cyc
            ipc_core = record.per_core_ipc.get(core, 0.0)
            speedup_core = record.per_core_speedup.get(core, 0.0)
            row[f"core{core}_instructions"] = inst
            row[f"core{core}_cycles"] = cyc
            row[f"core{core}_ipc"] = ipc_core
            row[f"core{core}_speedup"] = speedup_core
            core_speedups.append(speedup_core)
        if num_cores:
            row["geom_mean_core_speedup"] = geometric_mean_strict(core_speedups)

        for cache_name in cache_names:
            cache_col = sanitise_cache_name(cache_name)
            stats = record.caches.get(cache_name)
            coverage = record.coverage.get(cache_name, 0.0)
            if stats:
                row[f"{cache_col}_load_access"] = stats.load_access
                row[f"{cache_col}_load_miss"] = stats.load_miss
                row[f"{cache_col}_prefetch_access"] = stats.prefetch_access
                row[f"{cache_col}_prefetch_hit"] = stats.prefetch_hit
                row[f"{cache_col}_prefetch_miss"] = stats.prefetch_miss
                row[f"{cache_col}_prefetch_requested"] = stats.overall.requested
                row[f"{cache_col}_prefetch_issued"] = stats.overall.issued
                row[f"{cache_col}_prefetch_useful"] = stats.overall.useful
                row[f"{cache_col}_prefetch_useless"] = stats.overall.useless
                row[f"{cache_col}_prefetch_fill"] = stats.overall.fill
                row[f"{cache_col}_prefetch_late"] = stats.overall.late
                row[f"{cache_col}_accuracy_useful_total"] = stats.overall.accuracy_useful_total()
                row[f"{cache_col}_accuracy_useful_issued"] = stats.overall.accuracy_useful_issued()
                row[f"coverage_{cache_col}"] = coverage
            else:
                row[f"{cache_col}_load_access"] = 0
                row[f"{cache_col}_load_miss"] = 0
                row[f"{cache_col}_prefetch_access"] = 0
                row[f"{cache_col}_prefetch_hit"] = 0
                row[f"{cache_col}_prefetch_miss"] = 0
                row[f"{cache_col}_prefetch_requested"] = 0
                row[f"{cache_col}_prefetch_issued"] = 0
                row[f"{cache_col}_prefetch_useful"] = 0
                row[f"{cache_col}_prefetch_useless"] = 0
                row[f"{cache_col}_prefetch_fill"] = 0
                row[f"{cache_col}_prefetch_late"] = 0
                row[f"{cache_col}_accuracy_useful_total"] = 0.0
                row[f"{cache_col}_accuracy_useful_issued"] = 0.0
                row[f"coverage_{cache_col}"] = coverage

        for cache_name, mech in mechanism_keys:
            cache_col = sanitise_cache_name(cache_name)
            stats = record.caches.get(cache_name)
            mech_stats = stats.mechanisms.get(mech) if stats else None
            key_prefix = f"{cache_col}_{mech}"
            if mech_stats:
                row[f"{key_prefix}_requested"] = mech_stats.requested
                row[f"{key_prefix}_issued"] = mech_stats.issued
                row[f"{key_prefix}_useful"] = mech_stats.useful
                row[f"{key_prefix}_useless"] = mech_stats.useless
                row[f"{key_prefix}_fill"] = mech_stats.fill
                row[f"{key_prefix}_late"] = mech_stats.late
                row[f"{key_prefix}_accuracy_useful_total"] = mech_stats.accuracy_useful_total()
                row[f"{key_prefix}_accuracy_useful_issued"] = mech_stats.accuracy_useful_issued()
            else:
                row[f"{key_prefix}_requested"] = 0
                row[f"{key_prefix}_issued"] = 0
                row[f"{key_prefix}_useful"] = 0
                row[f"{key_prefix}_useless"] = 0
                row[f"{key_prefix}_fill"] = 0
                row[f"{key_prefix}_late"] = 0
                row[f"{key_prefix}_accuracy_useful_total"] = 0.0
                row[f"{key_prefix}_accuracy_useful_issued"] = 0.0

        rows.append(row)

    return columns, rows


def write_csv(columns: List[str], rows: List[Dict[str, object]], output_path: Optional[Path]) -> None:
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


# ---------- CLI ----------


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect ChampSim metrics from log/JSON outputs.")
    parser.add_argument("--log-root", type=Path, help="Directory containing per-prefetcher log folders.")
    parser.add_argument("--json-root", type=Path, help="Directory containing per-prefetcher JSON folders.")
    parser.add_argument(
        "--baseline-log-root",
        type=Path,
        help="Optional separate log root containing baseline runs (e.g., shared single-core 'no' results).",
    )
    parser.add_argument(
        "--baseline-json-root",
        type=Path,
        help="Optional separate JSON root containing baseline runs (e.g., shared single-core 'no' results).",
    )
    parser.add_argument("--baseline", type=str, default="no", help="Prefetcher name to use as baseline for speedup/coverage.")
    parser.add_argument("--include-prefetchers", nargs="*", help="Optional subset of prefetchers to include.")
    parser.add_argument("--program-filter", nargs="*", help="Optional subset of trace stems to include.")
    parser.add_argument(
        "--force-cache-prefixes",
        default=["cpu0_L2C"],
        nargs="*",
        help="Optional cache prefixes to force into the output columns (e.g., cpu0_L2C) even if stats are missing.",
    )
    parser.add_argument("--output", type=Path, help="Optional CSV output path. Defaults to stdout.")
    parser.add_argument(
        "--log-tail-lines",
        type=int,
        default=DEFAULT_LOG_TAIL_LINES,
        help="Only parse the last N lines of each log file. Use 0 or a negative value to scan the whole file.",
    )
    parser.add_argument("--verbose", action="store_true", help="Print progress messages to stderr.")
    args = parser.parse_args(argv)

    if not args.log_root and not args.json_root:
        parser.error("At least one of --log-root or --json-root must be provided.")
    return args


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    runs = collect_runs(
        log_root=args.log_root,
        json_root=args.json_root,
        include_prefetchers=args.include_prefetchers,
        program_filter=args.program_filter,
        verbose=args.verbose,
        log_tail_lines=args.log_tail_lines,
    )
    if not runs:
        print("No runs found with the provided arguments.", file=sys.stderr)
        return 1

    if args.baseline_log_root or args.baseline_json_root:
        baseline_runs = collect_runs(
            log_root=args.baseline_log_root,
            json_root=args.baseline_json_root,
            include_prefetchers=[args.baseline],
            program_filter=args.program_filter,
            verbose=args.verbose,
            log_tail_lines=args.log_tail_lines,
        )
        runs.update(baseline_runs)

    compute_derived_metrics(runs, baseline=args.baseline)
    columns, rows = build_output_rows(runs, force_cache_prefixes=args.force_cache_prefixes)
    write_csv(columns, rows, args.output)
    if args.verbose:
        print(f"[collect] Wrote {len(rows)} rows.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
