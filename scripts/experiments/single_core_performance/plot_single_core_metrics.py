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
import random
import sys
from pathlib import Path
from typing import List, Optional, Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
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
    load_metrics,
    plot_metric_by_category,
    plot_metric_by_program,
    plot_prefetch_composition,
    select_programs_by_category,
    select_regression_programs,
    select_top_programs,
)

GEOMEAN_LABEL = "Geomean"
PROGRAM_SPEEDUP_PREFETCHER_LABELS = ["PMP", "Gaze", "eBingo", "STEP"]


def _select_run_prefix(df: pd.DataFrame, run_prefix: Optional[str]) -> pd.DataFrame:
    """
    Resolve multiple run prefixes (e.g., v00/v01) before plotting.

    If ``run_prefix`` is provided, keep only that prefix.
    Otherwise, keep the latest prefix per (prefetcher, trace_base) to prevent
    mixed-prefix double counting in composition plots.
    """
    if "run_prefix" not in df.columns:
        return df

    if run_prefix:
        filtered = df[df["run_prefix"] == run_prefix].copy()
        if filtered.empty:
            available = ", ".join(sorted(str(v) for v in df["run_prefix"].dropna().unique()))
            raise ValueError(
                f"Requested run prefix '{run_prefix}' not present in metrics CSV. "
                f"Available prefixes: {available or 'none'}"
            )
        return filtered

    duplicate_mask = df.duplicated(subset=["prefetcher", "trace_base"], keep=False)
    if not duplicate_mask.any():
        return df

    ranked = df.copy()
    suffix_num = ranked["run_prefix"].astype(str).str.extract(r"(\d+)$", expand=False)
    ranked["_run_rank"] = pd.to_numeric(suffix_num, errors="coerce").fillna(-1)
    ranked = ranked.sort_values(["prefetcher", "trace_base", "_run_rank", "run_prefix"])
    deduped = ranked.drop_duplicates(subset=["prefetcher", "trace_base"], keep="last").drop(columns=["_run_rank"])
    return deduped


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

    fallback = plt.get_cmap("tab20")
    palette = {}
    fallback_idx = 0
    for label in hue_order:
        colour = PREFETCHER_COLOURS.get(label)
        if colour is None:
            colour = fallback(fallback_idx % fallback.N)
            fallback_idx += 1
        palette[label] = colour

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


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Plot single-core performance metrics.")
    parser.add_argument(
        "--metrics",
        type=Path,
        default=REPO_ROOT / "scripts" / "results_analysis" / "results" / "single_core_l2_results.csv",
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
            "sms",
            "dspatch",
            "spp_ppf",
            "pmp",
            "berti",
            "gaze",
            "bingo_streaming_disable_overlap_pht_16x64",
            "step",
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
        default=130,
        help="Number of programs to show when --programs is not provided.",
    )
    parser.add_argument(
        "--program-sample-seed",
        type=int,
        default=4244,
        help=(
            "Random seed for default program sampling "
            "(used only when neither --programs nor --program-categories is set)."
        ),
    )
    parser.add_argument(
        "--cache-prefix",
        default="cpu0_L2C",
        help="Cache prefix used for prefetch statistics (default: cpu0_L2C).",
    )
    parser.add_argument(
        "--run-prefix",
        default=None,
        help=(
            "Optional run prefix to plot (e.g., v01). If omitted and duplicate "
            "prefixes exist, the latest prefix per prefetcher+trace is used."
        ),
    )
    args = parser.parse_args(argv)

    apply_standard_style()
    df_full = load_metrics(args.metrics)
    df_full = _select_run_prefix(df_full, args.run_prefix)
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
        print(
            f"[WARN] Metrics file is missing columns for cache prefix '{cache_prefix}': {missing_columns}. "
            "Skipping accuracy/coverage plots. Re-run collect_metrics.py with cache stats to enable them.",
            file=sys.stderr,
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
    ]
    if not missing_columns:
        metric_configs.extend(
            [
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
        )
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
    if not missing_columns:
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
        registered_suites = {"SPEC06", "SPEC17", "CloudSuite"}
        candidate_df = df[df["benchmark"].isin(registered_suites)].copy()
        if candidate_df.empty:
            candidate_df = df[df["benchmark"] != "Unknown"].copy()
        if candidate_df.empty:
            print(
                "[WARN] No traces found in registered benchmark suites; falling back to all traces for sampling.",
                file=sys.stderr,
            )
            candidate_df = df

        candidates = list(dict.fromkeys(candidate_df["trace_base"].dropna().tolist()))
        if args.top_programs > 0:
            sample_n = min(args.top_programs, len(candidates))
            rng = random.Random(args.program_sample_seed)
            program_list = rng.sample(candidates, sample_n) if sample_n > 0 else []
        else:
            program_list = candidates

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
            is_speedup_program_plot = metric == "speedup"
            metric_program_df = program_df
            metric_prefetcher_order = preferred_order
            if is_speedup_program_plot:
                # Restrict Geomean to the registered single-core suites only.
                registered_suites = {"SPEC06", "SPEC17", "CloudSuite"}
                registered_source_df = df[df["benchmark"].isin(registered_suites)].copy()
                if not registered_source_df.empty:
                    metric_average_source_df = registered_source_df
                    geomean_scope_desc = "registered suites (SPEC06/SPEC17/CloudSuite)"
                else:
                    metric_average_source_df = df.copy()
                    geomean_scope_desc = "all filtered traces (registered suites unavailable)"

                metric_program_df = program_df[
                    program_df["prefetcher_label"].isin(PROGRAM_SPEEDUP_PREFETCHER_LABELS)
                ].copy()
                metric_average_source_df = metric_average_source_df[
                    metric_average_source_df["prefetcher_label"].isin(PROGRAM_SPEEDUP_PREFETCHER_LABELS)
                ].copy()
                metric_prefetcher_order = [
                    label
                    for label in PROGRAM_SPEEDUP_PREFETCHER_LABELS
                    if label in set(metric_program_df["prefetcher_label"])
                ]
            else:
                metric_average_source_df = average_source_df
            if is_speedup_program_plot:
                geomean_trace_count = int(metric_average_source_df["trace_base"].nunique())
                print(
                    f"[INFO] speedup_by_program Geomean uses {geomean_trace_count} traces "
                    f"({geomean_scope_desc})."
                )

            plot_metric_by_program(
                metric_program_df,
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
                prefetcher_order=metric_prefetcher_order,
                average_source_df=metric_average_source_df,
                figure_width_per_program=0.75 if is_speedup_program_plot else 0.8,
                figure_height=8 if is_speedup_program_plot else 5.5,
                bar_width=0.72 if is_speedup_program_plot else 0.6,
                axis_labelsize=20 if is_speedup_program_plot else None,
                x_tick_labelsize=20 if is_speedup_program_plot else None,
                y_tick_labelsize=19 if is_speedup_program_plot else None,
                title_fontsize=20 if is_speedup_program_plot else None,
                legend_fontsize=17 if is_speedup_program_plot else None,
                value_label_fontsize=13 if is_speedup_program_plot else 9.0,
                y_tick_bins=9 if is_speedup_program_plot else None,
                y_tick_step=0.2 if is_speedup_program_plot else None,
            )

    composition_required = [
        f"{cache_prefix}_prefetch_hit",
        f"{cache_prefix}_load_miss",
        f"{cache_prefix}_prefetch_issued",
        f"{cache_prefix}_load_access",
        f"{cache_prefix}_prefetch_useful",
        f"{cache_prefix}_prefetch_late",
        f"{cache_prefix}_prefetch_useless",
    ]
    missing_comp = [col for col in composition_required if col not in composition_df.columns]
    if missing_comp:
        print(
            f"[WARN] Metrics file is missing columns for composition plot (prefix '{cache_prefix}'): {missing_comp}. "
            "Skipping composition plots.",
            file=sys.stderr,
        )
    else:
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
            prefetcher_order=["SMS", "DSPatch", "SPP-PPF", "PMP", "vBerti", "Bingo", "Gaze", "STEP"],
            xtick_labelsize=18,
            group_label_y_factor=-0.3,
            figure_height=10,
            legend_rows=2,
            legend_fontsize=20,
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

    resolved_output_dir = output_dir.resolve()
    print(f"[INFO] Output directory: {resolved_output_dir}")
    print(f"[INFO] Generated: {resolved_output_dir / 'speedup_by_benchmark.png'}")
    if not missing_columns:
        print(f"[INFO] Generated: {resolved_output_dir / 'prefetch_accuracy_coverage_by_benchmark.png'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
