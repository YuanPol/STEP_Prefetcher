#!/usr/bin/env python3
"""
Generate summary figures for storage sensitivity experiments.

The script consumes the CSV produced by ``collect_metrics.py`` and renders:

* Speedup / accuracy / coverage bar charts aggregated by benchmark family
* Per-program breakdowns for the selected workloads
* Prefetch request composition (useful, useless, cache hits, late arrivals)

Example usage:

    python plot_storage_sensitivity_metrics.py \
        --metrics ../../results_analysis/results/all_results.csv \
        --prefetchers step_disable_second_ft256_at128_pt8 step_probation_disable_second_ft256_at128_pt8
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = SCRIPT_DIR.parents[0]

if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from scripts.results_analysis.plot_utils import (  # type: ignore
    PREFETCHER_DISPLAY_NAMES,
    apply_standard_style,
    ensure_dir,
    filter_prefetchers,
    load_metrics,
    plot_metric_by_category,
    plot_metric_by_program,
    plot_prefetch_composition,
    select_programs_by_category,
    select_top_programs,
)

GEOMEAN_LABEL = "Geomean"
STEP_STORAGE_VARIANTS = [
    "step_small",
    "step_disable_second_ft256_at128_pt2",
    "step_disable_second_ft256_at128_pt4",
    "step_disable_second_ft256_at128_pt8",
    "step_disable_second_ft256_at128_pt16",
    "step_disable_second_ft256_at128_pt32",
    "step_disable_second_ft256_at128_pt64",
    "step_disable_second_ft256_at128_pt128",
    "step_disable_second_ft256_at128_pt256",
]
GAZE_STORAGE_VARIANTS = [
    "gaze_ptway_2",
    "gaze_ptway_4",
    "gaze_ptway_8",
    "gaze_ptway_16",
    "gaze_ptway_32",
    "gaze_ptway_64",
    "gaze_ptway_128",
    "gaze_ptway_256",
]
VBERTI_STORAGE_VARIANTS = [
    "berti_bts_16_hts_8",
    "berti_bts_32_hts_16",
    "berti_bts_64_hts_32",
    "berti_bts_128_hts_64",
    "berti_bts_256_hts_128",
    "berti_bts_512_hts_256",
]
BINGO_STORAGE_VARIANTS = [
    "bingo_pht_16x16",
    "bingo_pht_16x32",
    "bingo_pht_16x64",
    "bingo_pht_16x128",
    "bingo_pht_16x256",
    "bingo_pht_16x512",
    "bingo_pht_16x1024",
]
EBINGO_STORAGE_VARIANTS = [
    "bingo_streaming_disable_overlap_pht_16x16",
    "bingo_streaming_disable_overlap_pht_16x32",
    "bingo_streaming_disable_overlap_pht_16x64",
    "bingo_streaming_disable_overlap_pht_16x128",
    "bingo_streaming_disable_overlap_pht_16x256",
    "bingo_streaming_disable_overlap_pht_16x512",
    "bingo_streaming_disable_overlap_pht_16x1024",
]
IPCP_STORAGE_VARIANTS = [
    "ipcp_l1_it128_ipcp_l2",
    "ipcp_l1_it256_ipcp_l2",
    "ipcp_l1_it512_ipcp_l2",
    "ipcp_l1_it1024_ipcp_l2",
    "ipcp_l1_it2048_ipcp_l2",
    "ipcp_l1_it4096_ipcp_l2",
    "ipcp_l1_it8192_ipcp_l2",
]

STORAGE_PRESETS = {
    "paper": [
        "berti_bts_128_hts_64",
        "bingo_pht_16x64",
        "bingo_streaming_disable_overlap_pht_16x64",
        "ipcp_l1_it1024_ipcp_l2",
        "gaze_ptway_8",
        "step_disable_second_ft256_at128_pt8",
    ],
    "step": STEP_STORAGE_VARIANTS,
    "gaze": GAZE_STORAGE_VARIANTS,
    "vberti": VBERTI_STORAGE_VARIANTS,
    "bingo": BINGO_STORAGE_VARIANTS,
    "ebingo": EBINGO_STORAGE_VARIANTS,
    "ipcp": IPCP_STORAGE_VARIANTS,
}

STORAGE_LABEL_OVERRIDES = {
    "step_small": "STEP_SMALL",
    "step_disable_second_ft256_at128_pt2": "STEP_PT_2",
    "step_disable_second_ft256_at128_pt4": "STEP_PT_4",
    "step_disable_second_ft256_at128_pt8": "STEP_PT_8",
    "step_disable_second_ft256_at128_pt16": "STEP_PT_16",
    "step_disable_second_ft256_at128_pt32": "STEP_PT_32",
    "step_disable_second_ft256_at128_pt64": "STEP_PT_64",
    "step_disable_second_ft256_at128_pt128": "STEP_PT_128",
    "step_disable_second_ft256_at128_pt256": "STEP_PT_256",
    "gaze_ptway_2": "Gaze_PT_2",
    "gaze_ptway_4": "Gaze_PT_4",
    "gaze_ptway_8": "Gaze_PT_8",
    "gaze_ptway_16": "Gaze_PT_16",
    "gaze_ptway_32": "Gaze_PT_32",
    "gaze_ptway_64": "Gaze_PT_64",
    "gaze_ptway_128": "Gaze_PT_128",
    "gaze_ptway_256": "Gaze_PT_256",
    "berti_bts_16_hts_8": "vBerti_16/8",
    "berti_bts_32_hts_16": "vBerti_32/16",
    "berti_bts_64_hts_32": "vBerti_64/32",
    "berti_bts_128_hts_64": "vBerti_128/64",
    "berti_bts_256_hts_128": "vBerti_256/128",
    "berti_bts_512_hts_256": "vBerti_512/256",
    "bingo_pht_16x16": "Bingo_16",
    "bingo_pht_16x32": "Bingo_32",
    "bingo_pht_16x64": "Bingo_64",
    "bingo_pht_16x128": "Bingo_128",
    "bingo_pht_16x256": "Bingo_256",
    "bingo_pht_16x512": "Bingo_512",
    "bingo_pht_16x1024": "Bingo_1024",
    "bingo_streaming_disable_overlap_pht_16x16": "eBingo_16",
    "bingo_streaming_disable_overlap_pht_16x32": "eBingo_32",
    "bingo_streaming_disable_overlap_pht_16x64": "eBingo_64",
    "bingo_streaming_disable_overlap_pht_16x128": "eBingo_128",
    "bingo_streaming_disable_overlap_pht_16x256": "eBingo_256",
    "bingo_streaming_disable_overlap_pht_16x512": "eBingo_512",
    "bingo_streaming_disable_overlap_pht_16x1024": "eBingo_1024",
    "ipcp_l1_it128_ipcp_l2": "IPCP_128",
    "ipcp_l1_it256_ipcp_l2": "IPCP_256",
    "ipcp_l1_it512_ipcp_l2": "IPCP_512",
    "ipcp_l1_it1024_ipcp_l2": "IPCP_1024",
    "ipcp_l1_it2048_ipcp_l2": "IPCP_2048",
    "ipcp_l1_it4096_ipcp_l2": "IPCP_4096",
    "ipcp_l1_it8192_ipcp_l2": "IPCP_8192",
}


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


def _apply_storage_label_overrides(df: pd.DataFrame) -> pd.DataFrame:
    if "prefetcher" not in df.columns:
        return df
    updated = df.copy()
    override_mask = updated["prefetcher"].isin(STORAGE_LABEL_OVERRIDES)
    updated.loc[override_mask, "prefetcher_label"] = (
        updated.loc[override_mask, "prefetcher"].map(STORAGE_LABEL_OVERRIDES)
    )
    return updated


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Plot storage sensitivity metrics.")
    parser.add_argument(
        "--metrics",
        type=Path,
        default=REPO_ROOT / "scripts" / "results_analysis" / "results" / "storage_sensitivity_results.csv",
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
        default=None,
        help="Subset of prefetchers to include (defaults to all present in the CSV).",
    )
    parser.add_argument(
        "--preset",
        choices=sorted(STORAGE_PRESETS),
        default="paper",
        help="Built-in storage sensitivity subset to plot when --prefetchers is omitted.",
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
        default=114,
        help="Number of programs to show when --programs is not provided.",
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
    if args.prefetchers is None:
        args.prefetchers = list(STORAGE_PRESETS[args.preset])

    apply_standard_style()
    df_full = load_metrics(args.metrics)
    df_full = _select_run_prefix(df_full, args.run_prefix)
    df_full = _apply_storage_label_overrides(df_full)
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
        preferred_order = [
            STORAGE_LABEL_OVERRIDES.get(p, PREFETCHER_DISPLAY_NAMES.get(p, p))
            for p in args.prefetchers
        ]

    for config in metric_configs:
        plot_metric_by_category(
            df,
            config["column"],
            config["label"],
            output_dir / f"{config['column']}_by_benchmark.png",
            title=config.get("category_title"),
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

        #Prefetch composition by benchmark family
        plot_prefetch_composition(
            composition_df,
            output_dir / "prefetch_composition_by_benchmark.png",
            cache_prefix=args.cache_prefix,
            title=f"Prefetch request composition ({args.cache_prefix}) by benchmark group",
            group_fields=("prefetcher", "benchmark"),
            facet_field="benchmark",
            prefetcher_order=preferred_order,
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
