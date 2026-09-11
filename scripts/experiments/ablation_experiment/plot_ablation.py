#!/usr/bin/env python3
"""
Generate summary figures for single-core experiments.

The script consumes the CSV produced by ``collect_metrics.py`` and renders:

* Speedup / accuracy / coverage bar charts aggregated by benchmark family
* Per-program breakdowns for the selected workloads
* Prefetch request composition (useful, useless, cache hits, late arrivals)

Example usage:

    python plot_single_core_metrics.py \
        --metrics ../../results_analysis/results/all_results.csv \
        --prefetchers no ip_stride sms bingo dspatch pmp gaze step_prefetcher_so_fallback_8way_pc
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.patches import Patch
from matplotlib.ticker import PercentFormatter

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = SCRIPT_DIR.parents[0]

if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from scripts.results_analysis.plot_utils import (  # type: ignore
    PREFETCHER_COLOURS,
    PREFETCHER_DISPLAY_NAMES,
    PREFETCHER_HATCHES,
    apply_standard_style,
    ensure_dir,
    filter_prefetchers,
    get_trace_display_name,
    load_metrics,
    plot_metric_by_category,
    plot_metric_by_program,
    plot_prefetch_composition,
    select_programs_by_category,
    select_regression_programs,
    select_top_programs,
)

GEOMEAN_LABEL = "Geomean"
DEFAULT_MECHANISM_PREFETCHERS = [
    "step_full_ft256_at128_pt8",
    "step_disable_first_ft256_at128_pt8",
    "step_disable_second_ft256_at128_pt8",
    "step_disable_third_ft256_at128_pt8",
]
MECHANISM_PREFETCHER_LABELS = {
    "step_full_ft256_at128_pt8": "STEP FULL",
    "step_disable_first_ft256_at128_pt8": "STEP FOE off",
    "step_disable_second_ft256_at128_pt8": "STEP SOE off",
    "step_disable_third_ft256_at128_pt8": "STEP TOE off",
}


def _first_present_column(df: pd.DataFrame, candidates: Sequence[str]) -> Optional[str]:
    for column in candidates:
        if column in df.columns:
            return column
    return None


def _speedup_geomean(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    values = values[values > 0]
    if values.empty:
        return float("nan")
    return float(np.exp(np.log(values).mean()))


def _resolve_prefetcher_labels(
    df: pd.DataFrame,
    prefetcher_order: Optional[Sequence[str]] = None,
) -> List[str]:
    observed = list(dict.fromkeys(df["prefetcher_label"].astype(str)))
    if prefetcher_order:
        ordered = [label for label in prefetcher_order if label in observed]
        ordered.extend(label for label in observed if label not in ordered)
        return ordered
    return observed


def print_speedup_tables(
    df: pd.DataFrame,
    *,
    prefetcher_order: Optional[Sequence[str]] = None,
    program_list: Optional[Sequence[str]] = None,
    average_source_df: Optional[pd.DataFrame] = None,
) -> None:
    subset = df[(df["prefetcher"] != "no") & (df["benchmark"] != "Unknown")].copy()
    if subset.empty:
        return

    hue_order = _resolve_prefetcher_labels(subset, prefetcher_order=prefetcher_order)
    benchmark_priority = ["SPEC06", "SPEC17", "CloudSuite"]

    benchmark_values = (
        subset.groupby(["benchmark", "prefetcher_label"])["speedup"]
        .apply(_speedup_geomean)
        .reset_index(name="speedup")
    )
    benchmark_order = [name for name in benchmark_priority if name in benchmark_values["benchmark"].unique()]
    benchmark_order.extend(
        name for name in benchmark_values["benchmark"].unique() if name not in benchmark_order
    )
    benchmark_table = (
        benchmark_values.pivot(index="benchmark", columns="prefetcher_label", values="speedup")
        .reindex(index=benchmark_order)
        .reindex(columns=hue_order)
    )

    overall_gmean = (
        subset.groupby("prefetcher_label")["speedup"]
        .apply(_speedup_geomean)
        .reindex(hue_order)
    )

    print("\n=== Speedup by benchmark ===")
    print(benchmark_table.to_string(float_format=lambda value: f"{value:.4f}"))
    print("\n=== Speedup Overall GMean ===")
    print(overall_gmean.to_string(float_format=lambda value: f"{value:.4f}"))

    if not program_list:
        return

    ordered_programs = list(dict.fromkeys(program_list))
    program_values = subset[subset["trace_base"].isin(ordered_programs)].copy()
    if program_values.empty:
        return

    display_order = [get_trace_display_name(name) for name in ordered_programs]
    display_map = dict(zip(ordered_programs, display_order))
    program_values["display_label"] = program_values["trace_base"].map(display_map)
    program_table = (
        program_values.pivot_table(
            index="display_label",
            columns="prefetcher_label",
            values="speedup",
            aggfunc="mean",
        )
        .reindex(index=display_order)
        .reindex(columns=hue_order)
    )

    average_scope = average_source_df if average_source_df is not None else subset
    average_scope = average_scope[
        (average_scope["prefetcher"] != "no") & (average_scope["benchmark"] != "Unknown")
    ].copy()
    if not average_scope.empty:
        program_table.loc[GEOMEAN_LABEL] = (
            average_scope.groupby("prefetcher_label")["speedup"]
            .apply(_speedup_geomean)
            .reindex(hue_order)
        )

    print("\n=== Speedup by program ===")
    print(program_table.to_string(float_format=lambda value: f"{value:.4f}"))


def plot_accuracy_coverage_by_category(
    df: pd.DataFrame,
    accuracy_col: str,
    coverage_col: str,
    output: Path,
    prefetcher_order: Optional[Sequence[str]] = None,
) -> None:
    """Render a 2-row benchmark summary (accuracy on top, coverage below) with one legend."""
    subset = df[(df["prefetcher"] != "no") & (df["benchmark"] != "Unknown")].copy()
    if subset.empty:
        return

    grouped = (
        subset.groupby(["benchmark", "prefetcher_label"], as_index=False)[[accuracy_col, coverage_col]]
        .mean()
    )
    if grouped.empty:
        return

    benchmark_totals = grouped.groupby("benchmark")[[accuracy_col, coverage_col]].sum(min_count=1).fillna(0.0)
    active_benchmarks = benchmark_totals[
        (benchmark_totals[accuracy_col] != 0.0) | (benchmark_totals[coverage_col] != 0.0)
    ].index.tolist()
    grouped = grouped[grouped["benchmark"].isin(active_benchmarks)].copy()
    if grouped.empty:
        return

    avg = grouped.groupby("prefetcher_label", as_index=False)[[accuracy_col, coverage_col]].mean()
    avg["benchmark"] = "Avg"
    grouped = pd.concat([grouped, avg], ignore_index=True, sort=False)

    benchmark_priority = ["SPEC06", "SPEC17", "CloudSuite", "Avg"]
    observed_benchmarks = list(dict.fromkeys(grouped["benchmark"].astype(str)))
    benchmark_order = [name for name in benchmark_priority if name in observed_benchmarks]
    benchmark_order.extend(name for name in observed_benchmarks if name not in benchmark_order)

    observed_prefetchers = list(dict.fromkeys(subset["prefetcher_label"]))
    if prefetcher_order:
        hue_order = [label for label in prefetcher_order if label in observed_prefetchers]
        hue_order.extend(label for label in observed_prefetchers if label not in hue_order)
    else:
        hue_order = observed_prefetchers
    if not hue_order:
        return

    fallback = iter(sns.color_palette("colorblind", len(hue_order)))
    palette = {}
    for label in hue_order:
        palette[label] = PREFETCHER_COLOURS.get(label, next(fallback))

    value_table = grouped.pivot_table(
        index="benchmark",
        columns="prefetcher_label",
        values=[accuracy_col, coverage_col],
        aggfunc="mean",
    )

    num_prefetchers = max(len(hue_order), 1)
    bar_width = 0.2
    group_width = bar_width * num_prefetchers
    group_gap = max(0.10, bar_width * 1.2)
    group_stride = group_width + group_gap
    x_centers = np.arange(len(benchmark_order), dtype=float) * group_stride

    fig_width = max(10.0, len(benchmark_order) * group_stride * 1.15 + 2.0)
    fig, axes = plt.subplots(2, 1, figsize=(fig_width, 8.0), sharex=True)

    metric_layout = [
        (accuracy_col, "Prefetch accuracy"),
        (coverage_col, "Prefetch coverage"),
    ]
    present_metrics = value_table.columns.get_level_values(0)
    for ax, (metric_col, ylabel) in zip(axes, metric_layout):
        if metric_col not in present_metrics:
            continue
        metric_table = value_table[metric_col].reindex(index=benchmark_order).reindex(columns=hue_order)

        for idx, prefetcher in enumerate(hue_order):
            if prefetcher not in metric_table.columns:
                continue
            x_positions = x_centers - (group_width / 2.0) + (idx + 0.5) * bar_width
            series = metric_table[prefetcher]
            valid = series.notna()
            if not valid.any():
                continue
            bars = ax.bar(
                x_positions[valid.to_numpy()],
                series[valid].to_numpy(),
                width=bar_width,
                color=palette[prefetcher],
                edgecolor="black",
                linewidth=1.0,
            )
            hatch = PREFETCHER_HATCHES.get(prefetcher, "")
            if hatch:
                for patch in bars:
                    patch.set_hatch(hatch)
            for patch in bars:
                height = patch.get_height()
                if np.isnan(height) or np.isclose(height, 0.0, atol=1e-6):
                    continue
                ax.annotate(
                    f"{height:.0%}",
                    (patch.get_x() + patch.get_width() / 2.0, height),
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    xytext=(0, 3),
                    textcoords="offset points",
                )

        values = metric_table.to_numpy(dtype=float).ravel()
        finite_values = values[np.isfinite(values)]
        if finite_values.size:
            upper = max(float(finite_values.max()) * 1.12, 0.10)
            if upper <= 1.0:
                upper = min(1.02, upper + 0.02)
            ax.set_ylim(0.0, upper)
        ax.set_ylabel(ylabel)
        ax.yaxis.set_major_formatter(PercentFormatter(xmax=1.0))
        ax.grid(axis="y", linestyle="--", alpha=0.3)

    axes[-1].set_xticks(x_centers)
    axes[-1].set_xticklabels(benchmark_order)
    axes[-1].set_xlabel("Benchmark")

    legend_handles = [
        Patch(
            facecolor=palette[label],
            edgecolor="black",
            hatch=PREFETCHER_HATCHES.get(label, ""),
            label=label,
        )
        for label in hue_order
    ]
    fig.legend(
        legend_handles,
        [handle.get_label() for handle in legend_handles],
        loc="upper center",
        bbox_to_anchor=(0.5, 0.995),
        ncol=min(len(hue_order), 8),
        framealpha=0.95,
    )
    fig.subplots_adjust(top=0.86, hspace=0.20)

    ensure_dir(output.parent)
    fig.savefig(output, dpi=300)
    try:
        fig.savefig(output.with_suffix(".pdf"), bbox_inches="tight")
    except Exception:
        pass
    plt.close(fig)


def plot_mechanism_useful_useless_by_program(
    df: pd.DataFrame,
    output: Path,
    cache_prefix: str,
    prefetchers: Sequence[str],
    programs: Optional[Sequence[str]] = None,
    random_sample_size: int = 40,
    random_seed: int = 7,
    cloudsuite_ratio_target: float = 0.25,
    suite_averages: Optional[Sequence[str]] = None,
    append_average: bool = True,
) -> bool:
    """
    Plot per-workload STREAM/FOE/SOE/TOE useful-ratio breakdown for multiple prefetchers.

    Returns ``True`` if the figure is generated, otherwise ``False``.
    """
    mechanism_columns = {
        "STREAM": {
            "useful": [
                f"{cache_prefix}_stream_useful",
                f"{cache_prefix}_st_useful",
            ],
            "useless": [
                f"{cache_prefix}_stream_useless",
                f"{cache_prefix}_st_useless",
            ],
        },
        "FOE": {
            "useful": [
                f"{cache_prefix}_first_offset_useful",
                f"{cache_prefix}_first_order_useful",
                f"{cache_prefix}_fo_useful",
            ],
            "useless": [
                f"{cache_prefix}_first_offset_useless",
                f"{cache_prefix}_first_order_useless",
                f"{cache_prefix}_fo_useless",
            ],
        },
        "SOE": {
            "useful": [
                f"{cache_prefix}_second_offset_useful",
                f"{cache_prefix}_second_order_useful",
                f"{cache_prefix}_so_useful",
            ],
            "useless": [
                f"{cache_prefix}_second_offset_useless",
                f"{cache_prefix}_second_order_useless",
                f"{cache_prefix}_so_useless",
            ],
        },
        "TOE": {
            "useful": [
                f"{cache_prefix}_third_offset_useful",
                f"{cache_prefix}_third_order_useful",
                f"{cache_prefix}_to_useful",
            ],
            "useless": [
                f"{cache_prefix}_third_offset_useless",
                f"{cache_prefix}_third_order_useless",
                f"{cache_prefix}_to_useless",
            ],
        },
    }

    resolved: dict[str, dict[str, str]] = {}
    for mechanism, parts in mechanism_columns.items():
        useful_col = _first_present_column(df, parts["useful"])
        if useful_col is None:
            print(
                f"[WARN] Skipping mechanism ratio plot: missing useful column for {mechanism}.",
                file=sys.stderr,
            )
            return False
        resolved[mechanism] = {"useful": useful_col}

    prefetcher_order = list(dict.fromkeys(prefetchers))
    if not prefetcher_order:
        print("[WARN] Skipping mechanism ratio plot: no prefetchers selected.", file=sys.stderr)
        return False

    subset = df[df["prefetcher"].isin(prefetcher_order)].copy()
    if subset.empty:
        print(
            "[WARN] Skipping mechanism ratio plot: selected prefetchers have no matching rows.",
            file=sys.stderr,
        )
        return False

    trace_sets: dict[str, set[str]] = {}
    for prefetcher in prefetcher_order:
        traces = set(subset.loc[subset["prefetcher"] == prefetcher, "trace_base"].unique().tolist())
        if traces:
            trace_sets[prefetcher] = traces
    if not trace_sets:
        print(
            "[WARN] Skipping mechanism ratio plot: selected prefetchers have no matching traces.",
            file=sys.stderr,
        )
        return False

    all_traces = set().union(*trace_sets.values())
    common_traces = set.intersection(*trace_sets.values())
    if common_traces != all_traces:
        dropped = len(all_traces - common_traces)
        print(
            f"[INFO] Mechanism plot: dropping {dropped} traces not present for every selected prefetcher.",
            file=sys.stderr,
        )
    if not common_traces:
        print(
            "[WARN] Skipping mechanism ratio plot: no trace appears in every selected prefetcher.",
            file=sys.stderr,
        )
        return False

    subset = subset[subset["trace_base"].isin(common_traces)].copy()

    value_columns: List[str] = []
    mechanism_order = ("STREAM", "FOE", "SOE", "TOE")
    for mechanism in mechanism_order:
        value_columns.append(resolved[mechanism]["useful"])

    benchmark_by_trace = (
        subset[["trace_base", "benchmark"]]
        .drop_duplicates(subset=["trace_base"])
        .set_index("trace_base")["benchmark"]
        .to_dict()
    )

    available_traces = common_traces
    if programs:
        excluded_programs = [name for name in programs if name in all_traces and name not in available_traces]
        if excluded_programs:
            print(
                f"[INFO] Mechanism plot: {len(excluded_programs)} requested traces were excluded because they are not available for all selected prefetchers.",
                file=sys.stderr,
            )
        candidate_traces = [name for name in programs if name in available_traces]
    else:
        candidate_traces = sorted(available_traces)
    if random_sample_size > 0 and not programs and len(candidate_traces) > random_sample_size:
        rng = np.random.default_rng(random_seed)
        cloudsuite_candidates = [
            trace for trace in candidate_traces if benchmark_by_trace.get(trace) == "CloudSuite"
        ]
        other_candidates = [
            trace for trace in candidate_traces if benchmark_by_trace.get(trace) != "CloudSuite"
        ]
        target_cloudsuite = int(round(random_sample_size * max(0.0, min(1.0, cloudsuite_ratio_target))))
        take_cloudsuite = min(target_cloudsuite, len(cloudsuite_candidates))
        take_other = min(random_sample_size - take_cloudsuite, len(other_candidates))
        remaining = random_sample_size - take_cloudsuite - take_other
        if remaining > 0:
            extra_cloudsuite = min(remaining, len(cloudsuite_candidates) - take_cloudsuite)
            take_cloudsuite += extra_cloudsuite
            remaining -= extra_cloudsuite
        if remaining > 0:
            extra_other = min(remaining, len(other_candidates) - take_other)
            take_other += extra_other
            remaining -= extra_other

        selected: List[str] = []
        if take_cloudsuite > 0:
            selected.extend(rng.choice(cloudsuite_candidates, size=take_cloudsuite, replace=False).tolist())
        if take_other > 0:
            selected.extend(rng.choice(other_candidates, size=take_other, replace=False).tolist())
        trace_order = sorted(selected)
    else:
        trace_order = candidate_traces
    if not trace_order:
        return False

    if random_sample_size > 0 and not programs:
        cloudsuite_count = sum(1 for trace in trace_order if benchmark_by_trace.get(trace) == "CloudSuite")
        print(
            f"[INFO] Mechanism plot sample mix: CloudSuite={cloudsuite_count}/{len(trace_order)} "
            f"({(cloudsuite_count / len(trace_order)) if trace_order else 0.0:.1%}).",
            file=sys.stderr,
        )
    suite_labels = list(suite_averages) if suite_averages else ["SPEC06", "SPEC17", "CloudSuite"]
    average_labels: List[str] = []
    average_source_traces: List[str] = []
    if append_average:
        if programs:
            average_source_traces = [name for name in candidate_traces if name in available_traces]
        else:
            average_source_traces = sorted(available_traces)
        for suite in suite_labels:
            suite_traces = [trace for trace in average_source_traces if benchmark_by_trace.get(trace) == suite]
            if suite_traces:
                average_labels.append(f"{suite} Avg")

    grouped_by_prefetcher: dict[str, pd.DataFrame] = {}
    active_prefetchers: List[str] = []
    for prefetcher in prefetcher_order:
        pf_subset = subset[subset["prefetcher"] == prefetcher]
        if pf_subset.empty:
            continue
        grouped_all = pf_subset.groupby("trace_base", as_index=False)[value_columns].sum()
        grouped = grouped_all.set_index("trace_base").reindex(trace_order, fill_value=0.0).reset_index()
        if append_average:
            all_indexed = grouped_all.set_index("trace_base")
            suite_rows = []
            for suite in suite_labels:
                suite_trace_list = [
                    trace for trace in average_source_traces
                    if benchmark_by_trace.get(trace) == suite
                ]
                if not suite_trace_list:
                    continue
                suite_slice = all_indexed.reindex(suite_trace_list, fill_value=0.0)
                avg_row = {"trace_base": f"{suite} Avg"}
                for column in value_columns:
                    avg_row[column] = float(suite_slice[column].mean())
                suite_rows.append(avg_row)
            if suite_rows:
                grouped = pd.concat([grouped, pd.DataFrame(suite_rows)], ignore_index=True)
        grouped_by_prefetcher[prefetcher] = grouped
        active_prefetchers.append(prefetcher)

    if not active_prefetchers:
        print(
            "[WARN] Skipping mechanism ratio plot: no selected prefetcher has matching rows.",
            file=sys.stderr,
        )
        return False

    trace_labels = trace_order + average_labels
    display_labels = [
        trace if trace in average_labels else get_trace_display_name(trace)
        for trace in trace_labels
    ]

    ratio_values: dict[str, dict[str, np.ndarray]] = {}
    for prefetcher in active_prefetchers:
        grouped = grouped_by_prefetcher[prefetcher]
        zero_mechanisms = [
            mechanism
            for mechanism in mechanism_order
            if np.allclose(grouped[resolved[mechanism]["useful"]].to_numpy(dtype=float), 0.0)
        ]
        if zero_mechanisms:
            print(
                f"[INFO] Mechanism plot: {prefetcher} has all-zero useful counts for {', '.join(zero_mechanisms)} in the plotted traces.",
                file=sys.stderr,
            )
        ratio_values[prefetcher] = {}
        useful_total = np.zeros(len(grouped), dtype=float)
        for mechanism in mechanism_order:
            useful_total += grouped[resolved[mechanism]["useful"]].to_numpy(dtype=float)

        for mechanism in mechanism_order:
            useful_vals = grouped[resolved[mechanism]["useful"]].to_numpy(dtype=float)
            ratio_values[prefetcher][mechanism] = np.divide(
                useful_vals,
                useful_total,
                out=np.zeros_like(useful_vals),
                where=useful_total > 0,
            )

    mechanism_colors = {
        "STREAM": "#7f7f7f",
        "FOE": "#1f77b4",
        "SOE": "#2ca02c",
        "TOE": "#ff7f0e",
    }
    mechanism_display_labels = {
        "STREAM": "STREAM",
        "FOE": "FOE",
        "SOE": "SOE",
        "TOE": "TOE",
    }

    x = np.arange(len(trace_labels), dtype=float)
    width = 0.54
    fig_width = max(16.0, len(trace_labels) * 0.52)
    if len(active_prefetchers) == 1:
        nrows, ncols = 1, 1
    elif len(active_prefetchers) <= 4:
        nrows, ncols = 2, 2
    else:
        ncols = 2
        nrows = int(np.ceil(len(active_prefetchers) / ncols))
    fig_height = max(6 if nrows == 1 else 6.2, nrows * 2.2)
    fig, axes = plt.subplots(nrows, ncols, figsize=(fig_width, fig_height), sharex=True, sharey=True)
    axes_flat = list(np.atleast_1d(axes).reshape(-1))

    mechanism_handles = [
        Patch(
            facecolor=mechanism_colors[name],
            edgecolor="black",
            label=mechanism_display_labels.get(name, name),
        )
        for name in mechanism_order
    ]
    legend_handles = [Patch(facecolor="none", edgecolor="none", label="Trigger")] + mechanism_handles

    for ax, prefetcher in zip(axes_flat, active_prefetchers):
        ax.tick_params(axis="y", labelsize=20)
        bottom = np.zeros(len(trace_labels), dtype=float)
        for mechanism in mechanism_order:
            values = ratio_values[prefetcher][mechanism]
            ax.bar(
                x,
                values,
                width=width,
                bottom=bottom,
                color=mechanism_colors[mechanism],
                edgecolor="black",
                linewidth=0.5,
            )
            bottom += values

        if average_labels:
            split_x = len(trace_order) - 0.5
            ax.axvline(split_x, color="#555555", linestyle=":", linewidth=1.2, alpha=0.7)

        ax.set_ylabel("Useful prefetch fraction", fontsize=20)
        ax.set_ylim(0.0, 1.05)
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_title(
            MECHANISM_PREFETCHER_LABELS.get(
                prefetcher,
                PREFETCHER_DISPLAY_NAMES.get(prefetcher, prefetcher),
            ),
            loc="left",
        )

    for ax in axes_flat[len(active_prefetchers):]:
        ax.set_visible(False)

    # Show x tick labels only on the bottom row.
    for idx, ax in enumerate(axes_flat[:len(active_prefetchers)]):
        row = idx // ncols
        if row < nrows - 1:
            ax.tick_params(axis="x", labelbottom=False)
        else:
            ax.set_xticks(x)
            ax.set_xticklabels(display_labels, rotation=45, ha="right",fontsize=22)

    fig.legend(
        handles=legend_handles,
        ncol=len(legend_handles),
        loc="upper center",
        bbox_to_anchor=(0.5, 1.05),
        framealpha=0.9,
        fontsize=20,
    )

    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.95))
    ensure_dir(output.parent)
    fig.savefig(output, dpi=300, bbox_inches="tight")
    try:
        fig.savefig(output.with_suffix(".pdf"), bbox_inches="tight")
    except Exception:
        pass
    plt.close(fig)
    return True


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Plot single-core performance metrics.")
    parser.add_argument(
        "--metrics",
        type=Path,
        default=REPO_ROOT / "scripts" / "results_analysis" / "results" / "ablation_results.csv",
        help="CSV file generated by collect_metrics.py.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "figures",
        help="Directory to write the generated figures.",
    )
    parser.add_argument(
        "--prefetchers",
        nargs="*",
        default=[
            "no",
            "step_full_ft256_at128_pt8",
            "step_disable_first_ft256_at128_pt8",
            "step_disable_second_ft256_at128_pt8",
            "step_disable_third_ft256_at128_pt8",
        ],
        help="Subset of prefetchers to include (defaults to all present in the CSV).",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=["no"],
        help="Prefetchers to exclude when selecting top programs (baseline).",
    )
    parser.add_argument(
        "--programs",
        nargs="*",
        help="Explicit list of program short-names to plot (overrides --top-programs).",
    )
    parser.add_argument(
        "--program-categories",
        nargs="*",
        help="Benchmark categories (e.g., SPEC17) whose programs should be emphasised in per-program plots.",
    )
    parser.add_argument(
        "--top-programs",
        type=int,
        default=50,
        help="Number of programs to show when --programs is not provided.",
    )
    parser.add_argument(
        "--cache-prefix",
        default="cpu0_L2C",
        help="Cache prefix used for prefetch statistics (default: cpu0_L2C).",
    )
    parser.add_argument(
        "--mechanism-prefetchers",
        nargs="*",
        help=(
            "Prefetchers used for STREAM/FOE/SOE/TOE ratio breakdown plot. "
            f"Default: {' '.join(DEFAULT_MECHANISM_PREFETCHERS)}"
        ),
    )
    parser.add_argument(
        "--mechanism-prefetcher",
        default=None,
        help="Legacy single-prefetcher option (used when --mechanism-prefetchers is omitted).",
    )
    parser.add_argument(
        "--no-mechanism-average",
        dest="mechanism_average",
        action="store_false",
        help="Disable benchmark-suite average bars in FOE/SOE/TOE useful breakdown plot.",
    )
    parser.add_argument(
        "--mechanism-random-sample-size",
        type=int,
        default=40,
        help=(
            "Number of randomly sampled programs to show in FOE/SOE/TOE useful breakdown "
            "when --programs is not explicitly provided (0 disables sampling)."
        ),
    )
    parser.add_argument(
        "--mechanism-random-seed",
        type=int,
        default=7,
        help="Random seed used for program sampling in FOE/SOE/TOE useful breakdown.",
    )
    parser.add_argument(
        "--mechanism-cloudsuite-ratio-target",
        type=float,
        default=0.25,
        help=(
            "Target CloudSuite share when randomly sampling mechanism traces "
            "(e.g., 0.25 means around one quarter of sampled traces)."
        ),
    )
    parser.add_argument(
        "--mechanism-step-full-random-sample-size",
        type=int,
        default=60,
        help=(
            "Number of randomly sampled programs to show in the additional STEP-full-only "
            "FOE/SOE/TOE useful breakdown when --programs is not explicitly provided."
        ),
    )
    parser.add_argument(
        "--mechanism-suite-averages",
        nargs="*",
        default=["SPEC06", "SPEC17", "CloudSuite"],
        help="Benchmark suites for average bars in FOE/SOE/TOE useful breakdown.",
    )
    parser.add_argument(
        "--no-print-speedup-values",
        dest="print_speedup_values",
        action="store_false",
        help="Disable printing exact speedup tables to stdout.",
    )
    parser.set_defaults(mechanism_average=True)
    parser.set_defaults(print_speedup_values=True)
    args = parser.parse_args(argv)

    apply_standard_style()
    df_full = load_metrics(args.metrics)
    df = filter_prefetchers(df_full, args.prefetchers)

    # Drop the baseline prefetcher unless it is the only one requested.
    if "no" in df["prefetcher"].unique() and df["prefetcher"].nunique() > 1:
        df = df[df["prefetcher"] != "no"]

    baseline_rows = df_full[df_full["prefetcher"] == "no"].copy()
    if not baseline_rows.empty:
        trace_filter = df["trace_base"].unique()
        if trace_filter.size > 0:
            baseline_rows = baseline_rows[baseline_rows["trace_base"].isin(trace_filter)]
    composition_df = pd.concat([df, baseline_rows], ignore_index=True) if not baseline_rows.empty else df.copy()

    if df.empty:
        raise ValueError("No rows remain after applying the selected prefetchers.")

    output_dir = args.output_dir
    ensure_dir(output_dir)

    cache_prefix = args.cache_prefix
    accuracy_total_col = f"{cache_prefix}_accuracy_useful_total"
    accuracy_issued_col = f"{cache_prefix}_accuracy_useful_issued"
    coverage_col = f"coverage_{cache_prefix}"

    required_columns = [accuracy_total_col, accuracy_issued_col, coverage_col]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise KeyError(
            f"Metrics file is missing required columns for cache prefix '{cache_prefix}': {missing_columns}.\n"
            "Either re-run collect_metrics.py with the desired cache present or adjust --cache-prefix."
        )

    metric_configs = [
        {
            "column": "speedup",
            "label": "Speedup over no prefetching",
            "program_label": "Speedup over no prefetching",
            "cap": 1.7,
            "program_title": "",
            "category_title": None,
            "annotate_overflow_only": True,
            "annotate_average": True,
            "legend_inside": True,
        },
        {
            "column": accuracy_total_col,
            "label": "Prefetch accuracy",
            "program_label": "Prefetch accuracy",
            "cap": 1.0,
            "program_title": "",
            "category_title": "",
            "annotate_overflow_only": False,
        },
        {
            "column": accuracy_issued_col,
            "label": "Prefetch accuracy",
            "program_label": "Prefetch accuracy",
            "cap": 1.0,
            "program_title": "",
            "category_title": "",
            "annotate_overflow_only": False,
        },
        {
            "column": coverage_col,
            "label": "Prefetch coverage",
            "program_label": "Prefetch coverage",
            "cap": 1.0,
            "program_title": "",
            "category_title": "",
            "annotate_overflow_only": False,
        },
    ]
    # If a list of prefetchers is provided, use its display-label order for plotting
    preferred_order = None
    if args.prefetchers:
        preferred_order = [PREFETCHER_DISPLAY_NAMES.get(p, p) for p in args.prefetchers]

    category_skip_columns = {accuracy_total_col, accuracy_issued_col, coverage_col}
    for config in metric_configs:
        if config["column"] in category_skip_columns:
            continue
        plot_metric_by_category(
            df,
            config["column"],
            config["label"],
            output_dir / f"{config['column']}_by_benchmark.png",
            title=config.get("category_title"),
            prefetcher_order=preferred_order,
        )
    plot_accuracy_coverage_by_category(
        df,
        accuracy_total_col,
        coverage_col,
        output_dir / "prefetch_accuracy_coverage_by_benchmark.png",
        prefetcher_order=preferred_order,
    )

    if args.programs:
        program_list = list(dict.fromkeys(args.programs))
    elif args.program_categories:
        program_list = select_programs_by_category(
            df,
            args.program_categories,
            metric="speedup",
            top_n=args.top_programs if args.top_programs > 0 else None,
        )
    else:
        program_list = select_top_programs(df, args.exclude, args.top_programs)

        # if args.regression_prefetcher:
        #     regression_list = select_regression_programs(
        #         df,
        #         args.regression_prefetcher,
        #         threshold=args.regression_threshold,
        #         reference_prefetcher=args.regression_reference,
        #     )
        # if regression_list:
        #     program_list = regression_list
        # else:
        #     print(
        #         f"[warn] No programs fell below {args.regression_threshold} speedup for "
        #         f"prefetcher '{args.regression_prefetcher}'.",
        #         file=sys.stderr,
        #     )
    average_source_df: Optional[pd.DataFrame] = None
    if program_list:
        if args.program_categories:
            average_source_df = df[df["benchmark"].isin(args.program_categories)].copy()
        else:
            average_source_df = df.copy()
        program_df = df[df["trace_base"].isin(program_list)].copy()
        for config in metric_configs:
            metric = config["column"]
            label = config["label"]
            program_label = config.get("program_label", label)
            program_title = config.get("program_title")
            cap = config.get("cap")
            cap_value = cap
            series = program_df[metric].dropna()
            if not series.empty:
                max_val = float(series.max())
                if max_val > 0:
                    candidate = max(max_val * 1.1, max_val + 0.05)
                    if cap is not None and cap > 0:
                        candidate = max(candidate, cap * 0.5)
                        cap_value = min(cap, candidate)
                    else:
                        cap_value = candidate
            if metric == "speedup" and cap is not None:
                cap_value = cap

            annotate_overflow_only = config.get("annotate_overflow_only", False)
            annotate_average = config.get("annotate_average", False)
            legend_inside = config.get("legend_inside", False)

            plot_metric_by_program(
                df,
                program_list,
                metric,
                program_label,
                output_dir / f"{metric}_by_program.png",
                title=program_title,
                y_cap=cap_value,
                append_average=True,
                average_label=GEOMEAN_LABEL,
                annotate_average=annotate_average,
                annotate_overflow_only=annotate_overflow_only,
                legend_inside=legend_inside,
                prefetcher_order=preferred_order,
                average_source_df=average_source_df,
            )

    if args.print_speedup_values:
        print_speedup_tables(
            df,
            prefetcher_order=preferred_order,
            program_list=program_list,
            average_source_df=average_source_df,
        )

    plot_prefetch_composition(
        composition_df,
        output_dir / "prefetch_composition.png",
        cache_prefix=args.cache_prefix,
        title=f"Prefetch request composition ({args.cache_prefix})",
    )

    # Prefetch composition by benchmark family
    plot_prefetch_composition(
        composition_df,
        output_dir / "prefetch_composition_by_benchmark.png",
        cache_prefix=args.cache_prefix,
        title=f"Prefetch request composition ({args.cache_prefix}) by benchmark group",
        group_fields=("prefetcher", "benchmark"),
        facet_field="benchmark",
        prefetcher_order=["SMS","DSPatch","SPP", "PMP", "Gaze", "STEP"]
    )

    # Prefetch composition by program for the selected subset
    if program_list:
        plot_prefetch_composition(
            composition_df,
            output_dir / "prefetch_composition_by_program.png",
            cache_prefix=args.cache_prefix,
            title=f"Prefetch request composition ({args.cache_prefix}) by program",
            group_fields=("prefetcher", "trace_base"),
            facet_field="trace_base",
            facet_order=list(dict.fromkeys(list(program_list) + [GEOMEAN_LABEL])),
            programs=program_list,
            append_average=True,
            average_label=GEOMEAN_LABEL,
            prefetcher_order=preferred_order,
        )

    if args.mechanism_prefetchers:
        mechanism_prefetchers = list(dict.fromkeys(args.mechanism_prefetchers))
    elif args.mechanism_prefetcher:
        mechanism_prefetchers = [args.mechanism_prefetcher]
    else:
        mechanism_prefetchers = DEFAULT_MECHANISM_PREFETCHERS

    mechanism_programs = list(dict.fromkeys(args.programs)) if args.programs else None
    plot_mechanism_useful_useless_by_program(
        df_full,
        output_dir / "fo_to_so_useful_useless_by_program.png",
        cache_prefix=args.cache_prefix,
        prefetchers=mechanism_prefetchers,
        programs=mechanism_programs,
        random_sample_size=args.mechanism_random_sample_size,
        random_seed=args.mechanism_random_seed,
        cloudsuite_ratio_target=args.mechanism_cloudsuite_ratio_target,
        suite_averages=args.mechanism_suite_averages,
        append_average=args.mechanism_average,
    )

    # Additional single-panel breakdown for STEP-full only.
    step_full_prefetcher = "step_full_ft256_at128_pt8"
    if step_full_prefetcher in set(df_full["prefetcher"].unique().tolist()):
        plot_mechanism_useful_useless_by_program(
            df_full,
            output_dir / "fo_to_so_useful_useless_by_program_step_full.png",
            cache_prefix=args.cache_prefix,
            prefetchers=[step_full_prefetcher],
            programs=mechanism_programs,
            random_sample_size=args.mechanism_step_full_random_sample_size,
            random_seed=args.mechanism_random_seed,
            cloudsuite_ratio_target=args.mechanism_cloudsuite_ratio_target,
            suite_averages=args.mechanism_suite_averages,
            append_average=args.mechanism_average,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
