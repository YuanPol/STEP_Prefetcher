#!/usr/bin/env python3
"""
Plot STEP prefetcher parameter sweeps from the collected metrics CSV.

Given a list of prefetcher configuration names (e.g.,
``footprint_step_prefetcher_..._ft32_at64_pt8``), the script infers which table
parameter (FT/AT/PHT) varies across the selection and renders a line chart with
that parameter on the X axis and a speedup aggregated the same way as
``plot_single_core_metrics.py`` (geomean over per-trace speedups for all
available traces) on the Y axis.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
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
    _aggregate_metric,
    apply_standard_style,
    ensure_dir,
    load_metrics,
)

DEFAULT_METRICS = SCRIPT_DIR / "results_analysis" / "results" / "parameter_sweep_results.csv"

SUFFIX_PATTERN = re.compile(r"_ft(?P<ft>\d+)_at(?P<at>\d+)_pt(?P<pt>\d+)(?:$|_)")

# Some historical STEP names omit the ft/at/pt suffixes; treat them as aliases.
DEFAULT_SUFFIXES: Dict[str, Tuple[int, int, int]] = {
    "step_disable_second": (256, 128, 8),
}

STEP_SWEEP_PRESETS = {
    "ft": [
        "step_disable_second_ft32_at128_pt8",
        "step_disable_second_ft64_at128_pt8",
        "step_disable_second_ft128_at128_pt8",
        "step_disable_second_ft256_at128_pt8",
        "step_disable_second_ft512_at128_pt8",
        "step_disable_second_ft1024_at128_pt8",
    ],
    "at": [
        "step_disable_second_ft256_at32_pt8",
        "step_disable_second_ft256_at64_pt8",
        "step_disable_second_ft256_at128_pt8",
        "step_disable_second_ft256_at256_pt8",
        "step_disable_second_ft256_at512_pt8",
    ],
    "pt": [
        "step_disable_second_ft256_at128_pt4",
        "step_disable_second_ft256_at128_pt8",
        "step_disable_second_ft256_at128_pt16",
        "step_disable_second_ft256_at128_pt32",
        "step_disable_second_ft256_at128_pt64",
        "step_disable_second_ft256_at128_pt128",
    ],
}

SWEEP_PRESETS = {
    "step": STEP_SWEEP_PRESETS,
}

PARAM_LABELS = {
    "ft": "FT size",
    "at": "AT size",
    "pt": "PHT ways",
}

BASELINE_VALUES = {
    "ft": 256,
    "at": 128,
    "pt": 8,
}


@dataclass(frozen=True)
class SweepPoint:
    """Container for a single parameter/value pair."""

    key: str
    label: str
    ft: int
    at: int
    pt: int
    speedup: float


def aggregate_prefetcher_metric(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    """
    Aggregate each prefetcher over all traces.

    For speedup-like metrics, this computes:
      1) per-trace aggregated value (handles duplicate rows/runs safely), then
      2) geometric mean across all traces.
    """
    per_trace = (
        df.groupby(["prefetcher", "prefetcher_label", "trace_base"])[metric]
        .apply(lambda series: _aggregate_metric(series, metric))
        .reset_index(name="trace_value")
    )
    per_trace = per_trace.dropna(subset=["trace_value"])
    if per_trace.empty:
        raise ValueError("No trace-level data remains after filtering invalid values.")

    aggregated = (
        per_trace.groupby(["prefetcher", "prefetcher_label"])["trace_value"]
        .apply(lambda series: _aggregate_metric(series, metric))
        .reset_index(name=metric)
    )
    return aggregated


def parse_suffix(prefetcher_name: str) -> Tuple[int, int, int]:
    """Extract (FT, AT, PT) from the configuration name."""
    match = SUFFIX_PATTERN.search(prefetcher_name)
    if match:
        return tuple(int(match.group(field)) for field in ("ft", "at", "pt"))
    if prefetcher_name in DEFAULT_SUFFIXES:
        return DEFAULT_SUFFIXES[prefetcher_name]
    raise ValueError(f"Cannot infer FT/AT/PT values from '{prefetcher_name}'.")


def build_parse_token(prefetcher_name: str) -> str:
    """
    Return the string used for suffix parsing, expanding aliases that omit the
    explicit ft/at/pt tokens.
    """
    if SUFFIX_PATTERN.search(prefetcher_name):
        return prefetcher_name
    if prefetcher_name in DEFAULT_SUFFIXES:
        ft, at, pt = DEFAULT_SUFFIXES[prefetcher_name]
        return f"{prefetcher_name}_ft{ft}_at{at}_pt{pt}"
    return prefetcher_name


def resolve_prefetcher_name(name: str, available: Iterable[str]) -> Tuple[str, str]:
    """
    Map the requested identifier to an actual name present in the CSV and return
    the lookup key along with the string that should be used for suffix parsing.
    """
    available_set = set(available)
    if name in available_set:
        return name, build_parse_token(name)
    if name in DEFAULT_SUFFIXES:
        ft, at, pt = DEFAULT_SUFFIXES[name]
        candidate = f"{name}_ft{ft}_at{at}_pt{pt}"
        if candidate in available_set:
            return candidate, build_parse_token(candidate)
    raise ValueError(f"Prefetcher '{name}' was not found in the metrics CSV.")


def collect_points(df: pd.DataFrame, requested: Sequence[str]) -> List[SweepPoint]:
    """
    Aggregate the requested configurations using geomean over all traces.
    """
    aggregated = aggregate_prefetcher_metric(df, "speedup")
    aggregated_map = {
        row["prefetcher"]: (row["prefetcher_label"], float(row["speedup"]))
        for _, row in aggregated.iterrows()
    }
    if not aggregated_map:
        raise ValueError("No prefetcher data available after aggregation.")

    available_names = list(aggregated_map.keys())
    points: List[SweepPoint] = []
    for name in requested:
        lookup_name, parse_token = resolve_prefetcher_name(name, available_names)
        if lookup_name not in aggregated_map:
            raise ValueError(f"Prefetcher '{lookup_name}' was filtered out during aggregation.")
        label, speedup = aggregated_map[lookup_name]
        ft, at, pt = parse_suffix(parse_token)
        points.append(SweepPoint(lookup_name, label, ft, at, pt, speedup))
    return points


def determine_sweep_axis(points: Sequence[SweepPoint]) -> str:
    """Return the name of the parameter that varies across the selection."""
    unique_values = {
        "ft": sorted({point.ft for point in points}),
        "at": sorted({point.at for point in points}),
        "pt": sorted({point.pt for point in points}),
    }
    varying = [axis for axis, values in unique_values.items() if len(values) > 1]
    if len(varying) != 1:
        detail = ", ".join(f"{axis}={values}" for axis, values in unique_values.items())
        raise ValueError(
            "Expected exactly one varying parameter across the provided configurations. "
            f"Observed: {detail}."
        )
    return varying[0]


def _prepare_entries(points: Sequence[SweepPoint], axis: str) -> Tuple[List[int], Dict[int, SweepPoint]]:
    axis_label = PARAM_LABELS[axis]
    entries: Dict[int, SweepPoint] = {}
    for point in points:
        value = getattr(point, axis)
        if value in entries:
            raise ValueError(
                f"Multiple configurations map to {axis_label} value {value}. "
                "Please ensure each size is unique."
            )
        entries[value] = point
    ordered_values = sorted(entries)
    return ordered_values, entries


def render_axis(
    ax: plt.Axes,
    points: Sequence[SweepPoint],
    axis: str,
    ylabel: str,
    title: Optional[str],
    baseline_value: Optional[int] = None,
) -> Tuple[Optional[float], Optional[float]]:
    ordered_values, entries = _prepare_entries(points, axis)
    positions = np.arange(len(ordered_values))
    y_values = [entries[val].speedup for val in ordered_values]
    if baseline_value is not None and ordered_values:
        if baseline_value in ordered_values:
            base_idx = ordered_values.index(baseline_value)
            ax.axvspan(
                base_idx - 0.2,
                base_idx + 0.2,
                facecolor="#f9c2c2",
                alpha=0.35,
                zorder=0,
            )

    ax.plot(
        positions,
        y_values,
        marker="o",
        linewidth=2.0,
        markersize=8,
        color="#1f77b4",
    )
    ax.set_xlabel(PARAM_LABELS[axis])
    if ylabel:
        ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title)
    ax.set_xticks(positions)
    ax.set_xticklabels([str(value) for value in ordered_values])
    ax.grid(True, which="both", axis="y", linestyle="--", alpha=0.4)
    ax.set_xlim(-0.5, len(ordered_values) - 0.5 if ordered_values else 0.5)
    label = title or f"{PARAM_LABELS[axis]} sweep"
    summary = ", ".join(f"{value}: {speed:.4f}" for value, speed in zip(ordered_values, y_values))
    print(f"[{label}] {summary}")
    if y_values:
        return min(y_values), max(y_values)
    return None, None


def plot_parameter_sweep(points: Sequence[SweepPoint], axis: str, ylabel: str, title: str | None) -> plt.Figure:
    """Render the line chart and return the matplotlib Figure."""
    fig, ax = plt.subplots(figsize=(7.0, 5.0))
    y_min, y_max = render_axis(
        ax,
        points,
        axis,
        ylabel,
        title,
        baseline_value=BASELINE_VALUES.get(axis),
    )
    if y_min is not None and y_max is not None:
        margin = max(0.01, 0.05 * (y_max - y_min))
        ax.set_ylim(max(0.0, y_min - margin), y_max + margin)
    return fig


def plot_multi_panel(
    ft_points: Optional[Sequence[SweepPoint]],
    at_points: Optional[Sequence[SweepPoint]],
    pt_points: Optional[Sequence[SweepPoint]],
    ylabel: str,
    title: Optional[str],
    output: Path,
) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 5.0), sharey=True)
    axis_payloads = [
        ("ft", ft_points, "(a) FT sweep", BASELINE_VALUES.get("ft")),
        ("at", at_points, "(b) AT sweep", BASELINE_VALUES.get("at")),
        ("pt", pt_points, "(c) PHT sweep", BASELINE_VALUES.get("pt")),
    ]
    per_axis_ranges: List[Tuple[Optional[float], Optional[float]]] = []
    for ax, (axis_name, data, panel_title, baseline_value) in zip(axes, axis_payloads):
        if data:
            y_min, y_max = render_axis(
                ax,
                data,
                axis_name,
                ylabel if ax is axes[0] else "",
                panel_title,
                baseline_value=baseline_value,
            )
            per_axis_ranges.append((y_min, y_max))
        else:
            ax.set_axis_off()
            ax.text(0.5, 0.5, "No data", ha="center", va="center")
            per_axis_ranges.append((None, None))
    valid_ranges = [(lo, hi) for lo, hi in per_axis_ranges if lo is not None and hi is not None]
    if valid_ranges:
        global_min = min(lo for lo, _ in valid_ranges if lo is not None)
        global_max = max(hi for _, hi in valid_ranges if hi is not None)
        margin = max(0.01, 0.05 * (global_max - global_min))
        lower = max(0.0, global_min - margin)
        upper = global_max + margin
        for ax in axes:
            if ax.has_data():
                ax.set_ylim(lower, upper)
    if title:
        fig.suptitle(title)
    fig.tight_layout()
    ensure_dir(output.parent)
    fig.savefig(output, dpi=300, bbox_inches="tight")
    try:
        fig.savefig(output.with_suffix(".pdf"), bbox_inches="tight")
    except Exception:
        pass
    print(f"Wrote sweep figure to {output}")


def _select_default_sweeps(preset: str) -> Dict[str, List[str]]:
    selected = SWEEP_PRESETS[preset]
    return {axis: list(values) for axis, values in selected.items()}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plot STEP parameter sweeps from collected metrics.")
    parser.add_argument(
        "--preset",
        choices=sorted(SWEEP_PRESETS),
        default="step",
        help="Which built-in sweep family to use for default --ft/--at/--pt lists.",
    )
    parser.add_argument(
        "--metrics",
        type=Path,
        default=DEFAULT_METRICS,
        help="Path to the metrics CSV (default: single_core_l2_results.csv).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "figures" / "parameter_sweep.png",
        help="Output image path.",
    )
    parser.add_argument(
        "--ylabel",
        default="Speedup over no prefetching",
        help="Y-axis label.",
    )
    parser.add_argument(
        "--title",
        help="Optional plot title.",
    )
    parser.add_argument(
        "prefetchers",
        nargs="*",
        help="Prefetcher configuration names to include in a single sweep.",
    )
    parser.add_argument(
        "--ft",
        nargs="*",
        default=None,
        help="Prefetcher configs comprising an FT-size sweep.",
    )
    parser.add_argument(
        "--at",
        nargs="*",
        default=None,
        help="Prefetcher configs comprising an AT-size sweep.",
    )
    parser.add_argument(
        "--pt",
        nargs="*",
        default=None,
        help="Prefetcher configs comprising a PHT-size sweep.",
    )
    args = parser.parse_args(argv)

    default_sweeps = _select_default_sweeps(args.preset)
    if args.ft is None:
        args.ft = default_sweeps["ft"]
    if args.at is None:
        args.at = default_sweeps["at"]
    if args.pt is None:
        args.pt = default_sweeps["pt"]

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
    df = load_metrics(args.metrics)

    def prepare_axis(names: Optional[Sequence[str]], expected_axis: str) -> Optional[Sequence[SweepPoint]]:
        if not names:
            return None
        pts = collect_points(df, names)
        axis = determine_sweep_axis(pts)
        if axis != expected_axis:
            raise ValueError(f"{expected_axis.upper()} sweep expected {expected_axis} axis, got {axis}.")
        return pts

    multi_mode = any([args.ft, args.at, args.pt])
    if multi_mode:
        ft_points = prepare_axis(args.ft, "ft")
        at_points = prepare_axis(args.at, "at")
        pt_points = prepare_axis(args.pt, "pt")
        if not any([ft_points, at_points, pt_points]):
            raise ValueError("At least one of --ft/--at/--pt must have entries.")
        title = args.title
        plot_multi_panel(ft_points, at_points, pt_points, args.ylabel, title, args.output)
        if not args.prefetchers:
            return 0

    if not args.prefetchers:
        return 0

    points = collect_points(df, args.prefetchers)
    sweep_axis = determine_sweep_axis(points)

    title = args.title
    if not title:
        title = f"{PARAM_LABELS[sweep_axis]} sweep"

    fig = plot_parameter_sweep(points, sweep_axis, args.ylabel, title)

    ensure_dir(args.output.parent)
    fig.savefig(args.output, dpi=300)
    try:
        fig.savefig(args.output.with_suffix(".pdf"), bbox_inches="tight")
    except Exception:
        pass
    print(f"Wrote sweep figure to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
