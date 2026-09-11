#!/usr/bin/env python3
"""
Plot per-core speedups for heterogeneous 4-core mixes.

This expects a metrics CSV produced by collect_metrics.py that contains per-core
instruction/cycle IPC and speedup columns (coreN_*). For each heterogeneous mix
(benchmark name), the script renders a panel with grouped bars: one bar per
core and an extra bar for the geometric mean across cores for each prefetcher.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = SCRIPT_DIR.parents[0]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from scripts.results_analysis.plot_utils import (  # type: ignore
    apply_standard_style,
    ensure_dir,
    filter_prefetchers,
    load_metrics,
    _prefetcher_handles,
    _prefetcher_order,
    _prefetcher_palette,
)

DEFAULT_METRICS = REPO_ROOT / "scripts" / "results_analysis" / "results" / "four_core_l2_heter_results.csv"
GEOM_COLUMN = "geom_mean_core_speedup"
CLOUD_PREFIXES = ("cass_", "nutch_", "stream_", "cloud_")


def infer_core_columns(df: pd.DataFrame) -> List[str]:
    core_columns = [col for col in df.columns if col.startswith("core") and col.endswith("_speedup")]
    core_columns.sort(key=lambda name: int(name[len("core") : name.index("_")]))
    return core_columns


def classify_mix_suite(trace_name: str) -> str:
    trace = str(trace_name)
    mix_name = trace.split("-", 1)[-1] if trace.startswith("het-") else trace
    components = mix_name.split("-")
    if any(component.startswith(CLOUD_PREFIXES) for component in components):
        return "cloudsuite"
    return "spec"


def collect_mix_data(
    df: pd.DataFrame,
    mixes: Optional[Sequence[str]],
    prefix: str = "het-",
    suite: str = "all",
) -> tuple[pd.DataFrame, List[str]]:
    if "benchmark" not in df.columns and "trace" in df.columns:
        df = df.copy()
        df["benchmark"] = df["trace"]
    if "prefetcher_label" not in df.columns and "prefetcher" in df.columns:
        df = df.copy()
        df["prefetcher_label"] = df["prefetcher"]
    # Force heterogeneous mixes to use the full trace name (starts with given prefix) as benchmark, and drop others.
    if "trace" in df.columns and "benchmark" in df.columns:
        df = df.copy()
        het_mask = df["trace"].str.startswith(prefix)
        df = df[het_mask | df["benchmark"].str.startswith(prefix)]
        df.loc[het_mask, "benchmark"] = df["trace"]
        df.loc[df["benchmark"] == "Unknown", "benchmark"] = df["trace"]
    subset = df.copy()
    if mixes:
        wanted = {m.lower() for m in mixes}
        benchmark_match = subset["benchmark"].str.lower().isin(wanted)
        trace_match = subset["trace"].str.lower().isin(wanted)
        subset = subset[benchmark_match | trace_match]
    if suite != "all":
        suite_mask = subset["benchmark"].map(classify_mix_suite) == suite
        subset = subset[suite_mask]
    if subset.empty:
        raise ValueError("No data after filtering mixes/prefetchers.")
    # Keep only rows that have per-core speedups
    core_columns = infer_core_columns(subset)
    if not core_columns:
        raise ValueError("Metrics CSV missing per-core columns.")
    cols_needed = core_columns + [GEOM_COLUMN]
    missing_cols = [c for c in cols_needed if c not in subset.columns]
    if missing_cols:
        raise ValueError(f"Metrics CSV missing per-core columns: {missing_cols}")
    subset = subset.dropna(subset=cols_needed, how="all")
    if subset.empty:
        raise ValueError("No per-core data available (all speedups are NaN/zero).")
    return subset, core_columns


def plot_per_core_inline(
    df: pd.DataFrame,
    output: Path,
    ylabel: str,
    title: Optional[str],
    mix_order: Sequence[str],
    mix_labels: Sequence[str],
    core_columns: Sequence[str],
) -> None:
    mixes = list(dict.fromkeys(mix_order)) if mix_order else list(dict.fromkeys(df["benchmark"]))
    order = _prefetcher_order(df, override=["eBingo", "STEP"])
    palette = _prefetcher_palette(order)
    handles = _prefetcher_handles(order, palette)

    apply_standard_style()
    plt.rcParams.update(
        {
            "axes.labelsize": 13,
            "axes.titlesize": 12,
            "xtick.labelsize": 11,
            "ytick.labelsize": 11,
            "legend.fontsize": 11,
            "figure.titlesize": 15,
        }
    )

    num_positions = len(core_columns) + 1
    gap = 1.0
    pref_count = max(len(order), 1)
    width = min(0.28, 0.8 / pref_count)
    fig_width = max(8.0, 3.0 * len(mixes) * max(1.0, pref_count / 3.0))
    fig, ax = plt.subplots(figsize=(fig_width, 4.5))

    xticks: List[float] = []
    xtick_labels: List[str] = []
    mix_centers: List[float] = []

    for mix_idx, mix in enumerate(mixes):
        subset = df[(df["benchmark"] == mix) | (df["trace"] == mix)]
        if subset.empty:
            continue
        base = mix_idx * (num_positions + gap)
        positions = base + np.arange(num_positions)
        mix_centers.append(base + (num_positions - 1) / 2)
        xticks.extend(positions)
        xtick_labels.extend([f"c{idx}" for idx in range(len(core_columns))] + ["avg"])

        for p_idx, prefetcher_label in enumerate(order):
            row = subset[subset["prefetcher_label"] == prefetcher_label]
            if row.empty:
                continue
            row = row.iloc[0]
            vals = [row[c] if pd.notna(row[c]) else 0.0 for c in core_columns]
            vals.append(row.get(GEOM_COLUMN, 0.0))
            offset = (p_idx - (len(order) - 1) / 2) * width
            bars = ax.bar(positions + offset, vals, width=width, color=palette.get(prefetcher_label), edgecolor="black")
            for idx, (bar, val) in enumerate(zip(bars, vals)):
                # annotate overflow bars
                if val > 2.0:
                    ax.text(
                        bar.get_x() + bar.get_width() / 2,
                        min(val, 2.0) + 0.02,
                        f"{val:.2f}",
                        ha="center",
                        va="bottom",
                        fontsize=9,
                        rotation=90,
                    )
                # always annotate the avg bar (last entry)
                if idx == len(vals) - 1:
                    ax.text(
                        bar.get_x() + bar.get_width() / 2,
                        min(val, 2.0) + 0.03,
                        f"{val:.2f}",
                        ha="center",
                        va="bottom",
                        fontsize=9,
                        rotation=90,
                        color="black",
                    )

        # divider and band
        if mix_idx % 2 == 1:
            ax.axvspan(base - 0.5, base + num_positions - 0.5, color="#000000", alpha=0.05, zorder=0)
        ax.axvline(base - 0.5, color="black", linestyle="--", linewidth=0.8)
    if mixes:
        ax.axvline(mix_centers[-1] + num_positions / 2, color="black", linestyle="--", linewidth=0.8)

    ax.set_xticks(xticks)
    ax.set_xticklabels(xtick_labels)
    label_lookup = dict(zip(mixes, mix_labels))
    for center, mix in zip(mix_centers, mixes):
        label = label_lookup.get(mix, mix)
        ax.text(center, -0.12, label, ha="center", va="top", transform=ax.get_xaxis_transform(), fontsize=11)
    ax.set_ylabel(ylabel)
    ax.set_ylim(0.0, 2.0)
    ax.grid(True, axis="y", linestyle="--", alpha=0.4)
    if title:
        ax.set_title(title)
    ax.legend(handles=handles, ncol=min(len(order), 4), loc="upper center", bbox_to_anchor=(0.5, 1.05))

    fig.tight_layout()
    ensure_dir(output.parent)
    # Avoid exceeding Agg's per-dimension pixel limit on wide heter-mix plots.
    max_png_pixels = 65000
    png_dpi = min(300, max(72, int(max_png_pixels / max(fig.get_figwidth(), 1.0))))
    fig.savefig(output, dpi=png_dpi, bbox_inches="tight")
    try:
        fig.savefig(output.with_suffix(".pdf"), bbox_inches="tight")
    except Exception:
        pass
    print(f"Wrote per-core heterogeneous figure to {output}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Plot per-core speedups for heterogeneous mixes.")
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS, help="Metrics CSV with per-core columns.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "figures" / "multicore_heterogeneous_per_core.png",
        help="Output image path.",
    )
    parser.add_argument("--prefetchers", nargs="*", help="Prefetcher names to include (CSV prefetcher column).")
    parser.add_argument("--mixes", nargs="*", help="Benchmark/mix names to include (defaults to all). Order also controls labeling.")
    parser.add_argument("--mix-prefix", default="het-", help="Prefix that identifies heterogeneous mixes (default: het-).")
    parser.add_argument(
        "--suite",
        choices=["all", "spec", "cloudsuite"],
        default="all",
        help="Filter heterogeneous mixes by suite family.",
    )
    parser.add_argument("--ylabel", default="Speedup over no prefetching", help="Y-axis label.")
    parser.add_argument("--title", help="Optional plot title.")
    args = parser.parse_args(argv)

    df = load_metrics(args.metrics)
    df = filter_prefetchers(df, args.prefetchers)
    df, core_columns = collect_mix_data(df, args.mixes, prefix=args.mix_prefix, suite=args.suite)
    mix_order = args.mixes or list(dict.fromkeys(df["benchmark"]))
    mix_labels = [f"mix{i+1}" for i in range(len(mix_order))]

    plot_per_core_inline(df, args.output, args.ylabel, args.title, mix_order, mix_labels, core_columns)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
