#!/usr/bin/env python3
"""
Plot single-core L2 system sensitivity curves (DRAM BW, LLC, and L2 size sweeps).

The data is collected from the runs launched via
``scripts/run/run_single_core_l2_system_sensitivity.py``.  For each configuration
we compute the geometric-mean speedup (cycles(no) / cycles(prefetcher)) across all
traces and render line charts similar to Figure 16 but with a refreshed style.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = SCRIPT_DIR.parents[0]

if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from scripts.results_analysis.plot_utils import (  # type: ignore
    PREFETCHER_COLOURS,
    PREFETCHER_DISPLAY_NAMES,
    apply_standard_style,
    load_metrics,
)

DEFAULT_PREFETCHERS = [
    "gaze",
    "berti",
    "spp_ppf",
    "bingo_streaming_disable_overlap_pht_16x64",
    "step",
]
BASELINE_PREFETCHER = "no"
DEFAULT_METRICS_CSV = REPO_ROOT / "scripts" / "results_analysis" / "results" / "system_sensitivity_results.csv"

DRAM_SWEEP = [
    {"value": 800, "label": "800", "prefix": "v11"},
    {"value": 1600, "label": "1600", "prefix": "v12"},
    {"value": 3200, "label": "3200", "prefix": "v00", "baseline": True},
    {"value": 6400, "label": "6400", "prefix": "v13"},
    {"value": 12800, "label": "12800", "prefix": "v14"},
]

LLC_SWEEP = [
    {"value": 0.5, "label": "0.5", "prefix": "v24"},
    {"value": 1.0, "label": "1", "prefix": "v21"},
    {"value": 2.0, "label": "2", "prefix": "v00", "baseline": True},
    {"value": 4.0, "label": "4", "prefix": "v22"},
]

L2C_SWEEP = [
    {"value": 128, "label": "128", "prefix": "v25"},
    {"value": 256, "label": "256", "prefix": "v26"},
    {"value": 512, "label": "512", "prefix": "v00", "baseline": True},
    {"value": 1024, "label": "1024", "prefix": "v27"},
    {"value": 1536, "label": "1536", "prefix": "v28"},
]

MARKERS = ["o", "s", "^", "D", "v", "P", "X"]
LINESTYLES = ["-", "--", "-.", ":"]


SYS_CONFIG_RE = re.compile(
    r"_bw_(?P<bw>[0-9.]+)_l2c?_?(?P<l2c>[0-9.]+)_llc_(?P<llc>[0-9.]+)"
)
TRACE_CONFIG_RE = re.compile(
    r"bw(?P<bw>[0-9.]+)_l2c?_?(?P<l2c>[0-9.]+)_llc_(?P<llc>[0-9.]+)"
)


def normalise_l2c_size(raw: float) -> int:
    """Return the L2 size in KB regardless of whether the input is in MB or KB."""
    if raw > 8:
        return int(round(raw))
    return int(round(raw * 1024))


def normalise_llc_size(raw: float) -> int:
    """Return the LLC size scaled to avoid floating comparison issues."""
    return int(round(raw * 1000))


def parse_config_from_prefetcher(prefetcher: str) -> Optional[Tuple[str, int, int, int]]:
    match = SYS_CONFIG_RE.search(prefetcher)
    if not match:
        return None
    bw = int(float(match.group("bw")))
    l2c_kb = normalise_l2c_size(float(match.group("l2c")))
    llc_key = normalise_llc_size(float(match.group("llc")))
    base = prefetcher.split("_bw_", 1)[0]
    return base, bw, l2c_kb, llc_key


def parse_config_from_trace(trace_base: str) -> Optional[Tuple[int, int, int]]:
    match = TRACE_CONFIG_RE.search(trace_base)
    if not match:
        return None
    bw = int(float(match.group("bw")))
    l2c_kb = normalise_l2c_size(float(match.group("l2c")))
    llc_key = normalise_llc_size(float(match.group("llc")))
    return bw, l2c_kb, llc_key


def extract_workload_id(trace_base: str) -> str:
    return trace_base.split("-", 1)[-1] if "-" in trace_base else trace_base


def geometric_mean(values: Sequence[float]) -> float:
    arr = np.asarray([v for v in values if v > 0], dtype=np.float64)
    if arr.size == 0:
        raise ValueError("Cannot compute geomean of empty/invalid values.")
    return float(np.exp(np.log(arr).mean()))


def gather_sweep(
    points: Sequence[Dict[str, object]],
    prefetchers: Sequence[str],
    compute_speedup_fn,
) -> Tuple[List[Dict[str, object]], Dict[str, List[float]]]:
    """
    Return (filtered_points, series) where filtered_points includes only the
    configurations for which every requested prefetcher has data.
    """
    series: Dict[str, List[float]] = {pref: [] for pref in prefetchers}
    kept_points: List[Dict[str, object]] = []
    for point in points:
        point_values: Dict[str, float] = {}
        missing = False
        for pref in prefetchers:
            try:
                point_values[pref] = compute_speedup_fn(pref, point)
            except RuntimeError as exc:
                print(f"[warn] Skipping point {point} for {pref}: {exc}", file=sys.stderr)
                missing = True
                break
        if missing:
            continue
        kept_points.append(point)
        for pref, value in point_values.items():
            series[pref].append(value)
    if not kept_points:
        raise RuntimeError("No valid data available for the requested sweep.")
    return kept_points, series


def log_sweep(name: str, points: Sequence[Dict[str, object]], series: Dict[str, List[float]]) -> None:
    labels = [str(point["label"]) for point in points]
    print(f"[{name}]")
    for pref, values in series.items():
        formatted = ", ".join(f"{label}:{value:.4f}" for label, value in zip(labels, values))
        print(f"  {format_label(pref)} -> {formatted}")


def format_label(prefetcher: str) -> str:
    return PREFETCHER_DISPLAY_NAMES.get(prefetcher, prefetcher)


def resolve_colour(label: str, fallback_cycle: Iterable[str]) -> str:
    colour = PREFETCHER_COLOURS.get(label)
    if colour:
        return colour
    return next(fallback_cycle)


def plot_axis(
    ax: plt.Axes,
    points: Sequence[Dict[str, object]],
    series: Dict[str, List[float]],
    prefetchers: Sequence[str],
    xlabel: str,
    title: str,
    baseline_label: str,
) -> None:
    x_positions = list(range(len(points)))
    tick_labels = [str(point["label"]) for point in points]
    try:
        baseline_idx = next(
            idx
            for idx, point in enumerate(points)
            if point.get("baseline") or str(point["label"]) == baseline_label
        )
    except StopIteration:
        baseline_idx = x_positions[len(x_positions) // 2]
    ax.axvspan(
        baseline_idx - 0.2,
        baseline_idx + 0.2,
        facecolor="#f9c2c2",
        alpha=0.35,
        zorder=0,
    )
    colour_cycle = iter(["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"])
    marker_cycle = iter(MARKERS)
    linestyle_cycle = iter(LINESTYLES)
    for pref in prefetchers:
        label = format_label(pref)
        colour = resolve_colour(label, colour_cycle)
        marker = next(marker_cycle, "o")
        linestyle = next(linestyle_cycle, "-")
        speeds = series[pref]
        ax.plot(
            x_positions,
            speeds,
            label=label,
            color=colour,
            marker=marker,
            linestyle=linestyle,
            markersize=7.5,
            linewidth=2.3,
            alpha=0.95,
        )
    ax.set_xlabel(xlabel)
    ax.set_title(title, fontsize=16, pad=12)
    ax.set_xticks(x_positions)
    ax.set_xticklabels(tick_labels)
    ax.grid(axis="y", linestyle=":", alpha=0.6)


def build_metrics_frame(csv_path: Path) -> pd.DataFrame:
    df = load_metrics(csv_path)
    records: List[Dict[str, object]] = []
    for _, row in df.iterrows():
        trace_base = str(row.get("trace_base", ""))
        parsed = parse_config_from_prefetcher(str(row["prefetcher"]))
        if parsed:
            base, bw, l2c_kb, llc_key = parsed
        else:
            trace_config = parse_config_from_trace(trace_base)
            if not trace_config:
                continue
            bw, l2c_kb, llc_key = trace_config
            base = str(row["prefetcher"])
        records.append(
            {
                "prefetcher": str(row["prefetcher"]),
                "prefetcher_base": base,
                "bw": bw,
                "l2c_kb": l2c_kb,
                "llc_key": llc_key,
                "workload": extract_workload_id(trace_base),
                "benchmark": str(row.get("benchmark", "")),
                "total_cycles": int(row.get("total_cycles", 0)),
            }
        )
    if not records:
        raise ValueError(f"No system sensitivity rows found in {csv_path}.")
    return pd.DataFrame.from_records(records)


def _cycles_by_workload(frame: pd.DataFrame) -> Dict[str, Tuple[int, str]]:
    grouped = (
        frame.groupby(["workload", "benchmark"], as_index=False)["total_cycles"]
        .min()
    )
    return {
        str(row["workload"]): (int(row["total_cycles"]), str(row["benchmark"]))
        for _, row in grouped.iterrows()
    }


def compute_speedup_from_metrics(df: pd.DataFrame, prefetcher: str, point: Dict[str, object]) -> float:
    bw = int(point["bw"])
    l2c_kb = normalise_l2c_size(float(point["l2c_kb"]))
    llc_key = normalise_llc_size(float(point["llc"]))
    base_frame = df[
        (df["prefetcher_base"] == BASELINE_PREFETCHER)
        & (df["bw"] == bw)
        & (df["l2c_kb"] == l2c_kb)
        & (df["llc_key"] == llc_key)
    ]
    target_frame = df[
        (df["prefetcher_base"] == prefetcher)
        & (df["bw"] == bw)
        & (df["l2c_kb"] == l2c_kb)
        & (df["llc_key"] == llc_key)
    ]
    if base_frame.empty or target_frame.empty:
        raise RuntimeError(f"Missing data for {prefetcher} (bw={bw}, l2={l2c_kb}KB, llc={point['llc']}).")

    baseline_map = _cycles_by_workload(base_frame)
    target_map = _cycles_by_workload(target_frame)
    shared = sorted(set(baseline_map) & set(target_map))
    if not shared:
        raise RuntimeError(f"No shared workloads for {prefetcher} (bw={bw}, l2={l2c_kb}KB, llc={point['llc']}).")

    # Aggregate as one geomean over all shared workloads (no per-category reweighting).
    ratios: List[float] = []
    for workload in shared:
        base_cycles, _ = baseline_map[workload]
        target_cycles, _ = target_map[workload]
        if base_cycles <= 0 or target_cycles <= 0:
            continue
        ratios.append(base_cycles / target_cycles)

    if not ratios:
        raise RuntimeError(f"No valid ratios for {prefetcher} (bw={bw}, l2={l2c_kb}KB, llc={point['llc']}).")

    return geometric_mean(ratios)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Plot L2 system sensitivity curves.")
    parser.add_argument(
        "--prefetchers",
        nargs="*",
        default=DEFAULT_PREFETCHERS,
        help="Prefetchers to include (baseline 'no' is implicit and omitted from the plot).",
    )
    parser.add_argument(
        "--metrics",
        type=Path,
        default=DEFAULT_METRICS_CSV,
        help="Path to a metrics CSV (default: single_core_l2_results_short.csv).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "figures" / "l2_system_sensitivity.png",
        help="Destination path for the generated figure.",
    )
    args = parser.parse_args(argv)

    prefetchers = [p for p in args.prefetchers if p != BASELINE_PREFETCHER]
    if not prefetchers:
        raise ValueError("At least one non-baseline prefetcher must be specified.")

    if args.metrics is None or str(args.metrics) == "":
        raise RuntimeError("A metrics CSV path is required when JSON data is disabled.")
    if not args.metrics.exists():
        raise FileNotFoundError(f"Metrics CSV not found: {args.metrics}")
    metrics_df = build_metrics_frame(args.metrics)
    print(f"[info] Loaded {len(metrics_df)} rows from metrics CSV {args.metrics}", file=sys.stderr)
    available_prefetchers = {str(p) for p in metrics_df["prefetcher_base"].unique()}
    missing = [p for p in prefetchers if p not in available_prefetchers]
    if missing:
        print(
            f"[warn] Dropping prefetchers not present in metrics CSV: {', '.join(missing)}",
            file=sys.stderr,
        )
    prefetchers = [p for p in prefetchers if p in available_prefetchers]
    if BASELINE_PREFETCHER not in available_prefetchers:
        raise RuntimeError(
            f"Baseline '{BASELINE_PREFETCHER}' not found in metrics CSV {args.metrics}"
        )
    if not prefetchers:
        raise RuntimeError("No requested prefetchers are present in the metrics CSV.")

    def compute_speedup_dispatch(prefetcher: str, point: Dict[str, object]) -> float:
        return compute_speedup_from_metrics(metrics_df, prefetcher, point)

    apply_standard_style()
    plt.rcParams.update(
        {
            "axes.labelsize": 18,
            "axes.titlesize": 16,
            "xtick.labelsize": 15,
            "ytick.labelsize": 15,
            "legend.fontsize": 14,
            "figure.titlesize": 18,
        }
    )
    dram_points = [
        {**point, "bw": point["value"], "l2c_kb": 512, "llc": 2.0}
        for point in DRAM_SWEEP
    ]
    llc_points = [
        {**point, "bw": 3200, "l2c_kb": 512, "llc": point["value"]}
        for point in LLC_SWEEP
    ]
    l2c_points = [
        {**point, "bw": 3200, "l2c_kb": point["value"], "llc": 2.0}
        for point in L2C_SWEEP
    ]

    dram_points, dram_series = gather_sweep(dram_points, prefetchers, compute_speedup_dispatch)
    llc_points, llc_series = gather_sweep(llc_points, prefetchers, compute_speedup_dispatch)
    l2c_points, l2c_series = gather_sweep(l2c_points, prefetchers, compute_speedup_dispatch)

    log_sweep("DRAM bandwidth sweep", dram_points, dram_series)
    log_sweep("LLC size sweep", llc_points, llc_series)
    log_sweep("L2 size sweep", l2c_points, l2c_series)

    all_speeds = dram_series.copy()
    for pref in prefetchers:
        all_speeds[pref] = (
            dram_series[pref]
            + llc_series.get(pref, [])
            + l2c_series.get(pref, [])
        )
    flat_values = [value for speeds in all_speeds.values() for value in speeds]
    ymin = min(flat_values)
    ymax = max(flat_values)
    margin = max(0.01, 0.05 * (ymax - ymin))

    fig, axes = plt.subplots(1, 3, figsize=(12, 4.5), sharey=True)
    plot_axis(
        axes[0],
        dram_points,
        dram_series,
        prefetchers,
        xlabel="DRAM bandwidth (MT/s)",
        title="(a) DRAM bandwidth",
        baseline_label="3200",
    )
    plot_axis(
        axes[1],
        llc_points,
        llc_series,
        prefetchers,
        xlabel="LLC size per core (MB)",
        title="(b) LLC size",
        baseline_label="2",
    )
    plot_axis(
        axes[2],
        l2c_points,
        l2c_series,
        prefetchers,
        xlabel="L2 size per core (KB)",
        title="(c) L2 size",
        baseline_label="512",
    )

    for ax in axes:
        ax.set_ylim(max(1.05, ymin - margin), ymax + margin)
        ax.set_ylabel("")
    axes[0].set_ylabel("Speedup over no prefetching")

    handles, labels = axes[0].get_legend_handles_labels()
    leg = fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.1),
        ncol=len(handles),
        frameon=False,
    )
    for text in leg.get_texts():
        text.set_fontsize(14)

    fig.tight_layout()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=300, bbox_inches="tight")
    try:
        fig.savefig(args.output.with_suffix(".pdf"), bbox_inches="tight")
    except Exception:
        pass
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
