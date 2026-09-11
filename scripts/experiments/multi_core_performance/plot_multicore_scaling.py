#!/usr/bin/env python3
"""
Plot multi-core scaling curves (speedup vs. core count) for a set of prefetchers.

The script expects one CSV per core-count (typically produced by
``scripts/results_analysis/collect_metrics.py``).  Each CSV is associated with a
core count using ``CORE:PATH`` arguments, e.g.:

    python3 plot_multicore_scaling.py \
        --inputs 1:scripts/results_analysis/results/single_core_l2_results.csv \
                 2:scripts/results_analysis/results/two_core_l2_results.csv \
                 4:scripts/results_analysis/results/four_core_l2_results.csv \
                 8:scripts/results_analysis/results/eight_core_l2_results.csv \
        --prefetchers gaze step
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from itertools import cycle

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = SCRIPT_DIR.parents[0]

DEFAULT_HOMO_INPUT_SPECS = [
    f"1:{REPO_ROOT / 'scripts' / 'results_analysis' / 'results' / 'single_core_l2_results.csv'}",
    f"2:{REPO_ROOT / 'scripts' / 'results_analysis' / 'results' / 'two_core_l2_results.csv'}",
    f"4:{REPO_ROOT / 'scripts' / 'results_analysis' / 'results' / 'four_core_l2_results.csv'}",
    f"8:{REPO_ROOT / 'scripts' / 'results_analysis' / 'results' / 'eight_core_l2_results.csv'}",
]
DEFAULT_HETERO_INPUT_SPECS = [
    f"1:{REPO_ROOT / 'scripts' / 'results_analysis' / 'results' / 'single_core_l2_results.csv'}",
    f"2:{REPO_ROOT / 'scripts' / 'results_analysis' / 'results' / 'two_core_l2_heter_results.csv'}",
    f"4:{REPO_ROOT / 'scripts' / 'results_analysis' / 'results' / 'four_core_l2_heter_results.csv'}",
    f"8:{REPO_ROOT / 'scripts' / 'results_analysis' / 'results' / 'eight_core_l2_heter_results.csv'}",
]
DEFAULT_BENCHMARK_PANELS = ["SPEC06", "SPEC17", "CloudSuite"]
HETEROGENEOUS_BENCHMARK = "Heterogeneous"

# Reuse shared plotting helpers for styling and palette consistency.
import sys

if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from scripts.results_analysis.plot_utils import (  # type: ignore
    apply_standard_style,
    filter_prefetchers,
    load_metrics,
    _aggregate_metric,
    _prefetcher_order,
    _prefetcher_palette,
)


# Styling helpers for line charts ------------------------------------------------
DEFAULT_MARKERS = ["o", "s", "D", "^", "v", "P", "X"]
DEFAULT_LINESTYLES = ["-", "--", "-.", ":"]

PREFETCHER_MARKERS: Dict[str, str] = {
    "STEP": "o",
    "Gaze": "s",
    "Bingo": "D",
    "DSPatch": "^",
    "SMS": "v",
    "PMP": "P",
    "SPP": "X",
}

PREFETCHER_LINESTYLES: Dict[str, str] = {
    "STEP": "-",
    "Gaze": "--",
    "Bingo": "-.",
    "DSPatch": ":",
}


def _resolve_marker(label: str, fallback_iter) -> str:
    marker = PREFETCHER_MARKERS.get(label)
    if marker:
        return marker
    return next(fallback_iter)


def _resolve_linestyle(label: str, fallback_iter) -> str:
    style = PREFETCHER_LINESTYLES.get(label)
    if style:
        return style
    return next(fallback_iter)


def parse_input_specs(specs: Sequence[str]) -> List[Tuple[int, Path]]:
    """Return a sorted list of (core_count, csv_path) pairs."""
    parsed: List[Tuple[int, Path]] = []
    for spec in specs:
        if ":" not in spec:
            raise argparse.ArgumentTypeError(f"Input '{spec}' is missing ':' (expected CORE:PATH).")
        core_str, path_str = spec.split(":", 1)
        try:
            cores = int(core_str)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"Invalid core count '{core_str}' in '{spec}'.") from exc
        path = Path(path_str).expanduser()
        parsed.append((cores, path))
    parsed.sort(key=lambda item: item[0])
    return parsed


def parse_region_specs(specs: Optional[Sequence[str]]) -> List[Tuple[int, int, str]]:
    """Parse CLI --regions entries of the form START-END:Label."""
    regions: List[Tuple[int, int, str]] = []
    if not specs:
        return regions
    for spec in specs:
        if ":" not in spec:
            raise argparse.ArgumentTypeError(
                f"Region '{spec}' is missing ':' (expected START-END:Label)."
            )
        span, label = spec.split(":", 1)
        if "-" not in span:
            raise argparse.ArgumentTypeError(
                f"Region '{spec}' is missing '-' (expected START-END:Label)."
            )
        start_str, end_str = span.split("-", 1)
        try:
            start = int(start_str)
            end = int(end_str)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"Invalid region bounds in '{spec}'.") from exc
        if end < start:
            start, end = end, start
        regions.append((start, end, label.strip()))
    return regions


def geometric_mean(series: pd.Series) -> float:
    """Return the geometric mean of positive values in the series."""
    cleaned = series.dropna()
    cleaned = cleaned[cleaned > 0]
    if cleaned.empty:
        return float("nan")
    return float(np.exp(np.log(cleaned).mean()))


def _filter_to_common_workloads(per_trace_df: pd.DataFrame) -> pd.DataFrame:
    """
    Keep only workloads present for every active prefetcher.

    Multi-core result CSVs can be incomplete for some prefetchers. Restricting
    the aggregate to the shared workload set keeps benchmark-level and overall
    geomeans directly comparable.
    """
    if per_trace_df.empty:
        return per_trace_df

    trace_sets: Dict[str, set[str]] = {}
    for prefetcher, group in per_trace_df.groupby("prefetcher"):
        workloads = set(group["_workload_id"].astype(str).tolist())
        if workloads:
            trace_sets[str(prefetcher)] = workloads
    if len(trace_sets) < 2:
        return per_trace_df

    all_workloads = set().union(*trace_sets.values())
    common_workloads = set.intersection(*trace_sets.values())
    if not common_workloads:
        return per_trace_df.iloc[0:0].copy()

    if common_workloads != all_workloads:
        dropped = len(all_workloads - common_workloads)
        print(
            f"[INFO] Multi-core scaling: dropping {dropped} workloads not present for every active prefetcher.",
            file=sys.stderr,
        )

    return per_trace_df[per_trace_df["_workload_id"].isin(common_workloads)].copy()


def _normalise_mix_prefix(prefix: str) -> str:
    """Ensure heterogeneous trace prefixes use ``...-`` form."""
    cleaned = prefix.strip()
    if not cleaned:
        raise ValueError("--mix-prefix cannot be empty.")
    return cleaned if cleaned.endswith("-") else f"{cleaned}-"


def _select_workload_rows(
    df: pd.DataFrame,
    heterogeneous: bool,
    mix_prefix: str,
) -> pd.DataFrame:
    """
    Select rows for the requested workload mode.

    Heterogeneous runs have trace identifiers like ``hete-...``. When
    ``heterogeneous`` is enabled, keep only those rows and map them to a
    synthetic benchmark bucket so existing aggregation/panel logic remains
    unchanged.
    """
    if not heterogeneous:
        return df

    trace_prefix = _normalise_mix_prefix(mix_prefix)
    trace_values = df["trace"].fillna("").astype(str)

    # Keep only true heterogeneous mixes for the requested prefix.
    # Example:
    #   homogeneous:   mc-410_1963
    #   heterogeneous: mc-429_192-481_1281
    # When a shared prefix is reused (e.g., "mc"), this prevents accidental
    # mixing of homogeneous rows into heterogeneous aggregation.
    def _is_heterogeneous_trace(trace: str) -> bool:
        if not trace.startswith(trace_prefix):
            return False
        tail = trace[len(trace_prefix) :]
        return "-" in tail

    prefix_mask = trace_values.apply(_is_heterogeneous_trace)
    subset = df[prefix_mask].copy()
    if subset.empty:
        return subset
    subset["benchmark"] = HETEROGENEOUS_BENCHMARK
    return subset


def _extract_heterogeneous_mix_components(df: pd.DataFrame, mix_prefix: str) -> List[List[str]]:
    """Return unique heterogeneous mixes as lists of trace identifiers."""
    trace_prefix = _normalise_mix_prefix(mix_prefix)
    traces = df["trace"].fillna("").astype(str)
    matched = traces[traces.str.startswith(trace_prefix)].drop_duplicates()
    mixes: List[List[str]] = []
    seen: set[Tuple[str, ...]] = set()
    for trace in matched:
        mix_body = trace[len(trace_prefix) :]
        parts = [part for part in mix_body.split("-") if part]
        if not parts:
            continue
        key = tuple(parts)
        if key in seen:
            continue
        seen.add(key)
        mixes.append(parts)
    return mixes


def _build_synthetic_single_core_rows(
    single_core_df: pd.DataFrame,
    mix_components: Sequence[Sequence[str]],
    prefetchers: Optional[Sequence[str]],
) -> pd.DataFrame:
    """
    Build synthetic 1-core heterogeneous rows from constituent single-core runs.

    For each heterogeneous mix and prefetcher:
      speedup_1c(mix) = geometric_mean(single_core_speedup(trace_i))
    """
    df = filter_prefetchers(single_core_df, prefetchers)
    if df.empty or not mix_components:
        return pd.DataFrame(columns=["benchmark", "prefetcher", "prefetcher_label", "speedup"])

    per_trace = (
        df.groupby(["prefetcher", "prefetcher_label", "trace_base"])["speedup"]
        .apply(lambda series: _aggregate_metric(series, "speedup"))
        .reset_index(name="speedup")
    )
    if per_trace.empty:
        return pd.DataFrame(columns=["benchmark", "prefetcher", "prefetcher_label", "speedup"])

    label_by_prefetcher = (
        per_trace.drop_duplicates(subset=["prefetcher", "prefetcher_label"])
        .set_index("prefetcher")["prefetcher_label"]
        .to_dict()
    )
    speedup_lookup: Dict[str, Dict[str, float]] = {}
    for prefetcher, group in per_trace.groupby("prefetcher"):
        speedup_lookup[prefetcher] = group.set_index("trace_base")["speedup"].to_dict()

    rows: List[Dict[str, object]] = []
    for mix in mix_components:
        mix_name = "-".join(mix)
        for prefetcher, trace_map in speedup_lookup.items():
            component_speedups: List[float] = []
            missing = False
            for trace in mix:
                value = trace_map.get(trace)
                if value is None or pd.isna(value) or value <= 0:
                    missing = True
                    break
                component_speedups.append(float(value))
            if missing or not component_speedups:
                continue
            rows.append(
                {
                    "benchmark": HETEROGENEOUS_BENCHMARK,
                    "prefetcher": prefetcher,
                    "prefetcher_label": label_by_prefetcher.get(prefetcher, prefetcher),
                    "speedup": geometric_mean(pd.Series(component_speedups)),
                    "trace": mix_name,
                    "trace_base": mix_name,
                }
            )
    return pd.DataFrame(rows)


def aggregate_speedup(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Aggregate speedups using the same weighting strategy as the single-core
    plots.

    Returns
    -------
    avg_df:
        Per-prefetcher geometric mean across all valid traces.
    category_df:
        Per-prefetcher, per-category geomean values.
    """
    work_df = df.copy()
    if "trace_base" not in work_df.columns:
        if "trace" in work_df.columns:
            work_df["trace_base"] = work_df["trace"].fillna("").astype(str)
        else:
            work_df["trace_base"] = ""

    per_trace = (
        work_df.groupby(["benchmark", "prefetcher", "prefetcher_label", "trace_base"])["speedup"]
        .apply(lambda series: _aggregate_metric(series, "speedup"))
        .reset_index(name="speedup")
    )
    per_trace = per_trace[per_trace["benchmark"] != "Unknown"].copy()
    per_trace = per_trace.dropna(subset=["speedup"])
    per_trace = per_trace[per_trace["speedup"] > 0]
    if per_trace.empty:
        return (
            pd.DataFrame(columns=["prefetcher", "prefetcher_label", "speedup"]),
            pd.DataFrame(columns=["prefetcher", "prefetcher_label", "benchmark", "speedup"]),
        )

    valid_benchmarks = per_trace.groupby("benchmark")["speedup"].sum()
    valid_benchmarks = valid_benchmarks[valid_benchmarks != 0].index
    per_trace = per_trace[per_trace["benchmark"].isin(valid_benchmarks)].copy()
    if per_trace.empty:
        return (
            pd.DataFrame(columns=["prefetcher", "prefetcher_label", "speedup"]),
            pd.DataFrame(columns=["prefetcher", "prefetcher_label", "benchmark", "speedup"]),
        )

    per_trace["_workload_id"] = (
        per_trace["benchmark"].astype(str) + "::" + per_trace["trace_base"].astype(str)
    )
    per_trace = _filter_to_common_workloads(per_trace)
    if per_trace.empty:
        return (
            pd.DataFrame(columns=["prefetcher", "prefetcher_label", "speedup"]),
            pd.DataFrame(columns=["prefetcher", "prefetcher_label", "benchmark", "speedup"]),
        )

    category_df = (
        per_trace.groupby(["benchmark", "prefetcher", "prefetcher_label"])["speedup"]
        .apply(geometric_mean)
        .reset_index(name="speedup")
    )
    averaged = (
        per_trace.groupby(["prefetcher", "prefetcher_label"])["speedup"]
        .apply(geometric_mean)
        .reset_index(name="speedup")
    )
    return averaged, category_df


def build_scaling_dataframe(
    inputs: Sequence[Tuple[int, Path]],
    prefetchers: Optional[Sequence[str]],
    panels: Optional[Sequence[str]] = None,
    benchmarks: Optional[Sequence[str]] = None,
    heterogeneous: bool = False,
    mix_prefix: str = "hete-",
) -> pd.DataFrame:
    """Load each metrics CSV and attach the aggregated speedup for every prefetcher."""
    rows: List[Dict[str, object]] = []
    single_core_source: Optional[pd.DataFrame] = None
    # Normalize benchmark filters for case-insensitive compare
    benchmark_filters = None
    if benchmarks:
        benchmark_filters = {b.strip().lower() for b in benchmarks}
    panel_filters = None
    if panels:
        panel_filters = {panel.strip().lower() for panel in panels if panel.lower() != "avg"}
    for cores, csv_path in inputs:
        df = load_metrics(csv_path)
        if heterogeneous and cores == 1:
            single_core_source = df.copy()
            continue
        df = _select_workload_rows(
            df,
            heterogeneous=heterogeneous,
            mix_prefix=mix_prefix,
        )
        if benchmark_filters is not None:
            df = df[df["benchmark"].str.lower().isin(benchmark_filters)]
        df = filter_prefetchers(df, prefetchers)
        if df.empty:
            continue
        avg_df, category_df = aggregate_speedup(df)
        avg_df = avg_df.copy()
        avg_df["scope"] = "Avg"
        selected_frames = [avg_df]
        cat_subset = category_df.copy()
        if panel_filters:
            cat_subset = cat_subset[cat_subset["benchmark"].str.lower().isin(panel_filters)]
        cat_subset = cat_subset.rename(columns={"benchmark": "scope"})
        selected_frames.append(cat_subset)
        combined = pd.concat(selected_frames, ignore_index=True, sort=False)
        if combined.empty:
            continue
        combined["cores"] = cores
        rows.append(combined)

    if heterogeneous and single_core_source is not None:
        # For heterogeneous scaling, reuse homogeneous 1-core aggregate directly.
        one_core_df = filter_prefetchers(single_core_source, prefetchers)
        if benchmark_filters is not None:
            one_core_df = one_core_df[one_core_df["benchmark"].str.lower().isin(benchmark_filters)]
        if not one_core_df.empty:
            one_core_avg, _ = aggregate_speedup(one_core_df)
            if not one_core_avg.empty:
                avg_rows = one_core_avg.copy()
                avg_rows["scope"] = "Avg"
                avg_rows["cores"] = 1
                rows.append(avg_rows)

                # Also provide a 1-core point for the heterogeneous panel itself.
                heter_rows = one_core_avg.copy()
                heter_rows["scope"] = HETEROGENEOUS_BENCHMARK
                heter_rows["cores"] = 1
                if panel_filters:
                    heter_rows = heter_rows[
                        heter_rows["scope"].str.lower().isin(panel_filters)
                    ]
                if not heter_rows.empty:
                    rows.append(heter_rows)

    if not rows:
        if heterogeneous:
            trace_prefix = _normalise_mix_prefix(mix_prefix)
            raise ValueError(
                "No data available after filtering heterogeneous mixes. "
                f"Check --mix-prefix (currently '{trace_prefix}') and input CSVs."
            )
        raise ValueError("No data available after loading the requested inputs/prefetchers.")
    combined = pd.concat(rows, ignore_index=True)
    return combined


def plot_scaling_panels(
    data: pd.DataFrame,
    scopes: Sequence[str],
    output: Path,
    ylabel: str = "Speedup over no prefetching",
    title: Optional[str] = None,
    regions: Optional[Sequence[Tuple[int, int, str]]] = None,
) -> None:
    """Render the scaling lines for multiple benchmark scopes in a single figure."""
    apply_standard_style()
    plt.rcParams.update(
        {
            "axes.labelsize": 12,
            "axes.titlesize": 12,
            "xtick.labelsize": 12,
            "ytick.labelsize": 12,
            "legend.fontsize": 12,
            "figure.titlesize": 12,
        }
    )
    order = _prefetcher_order(data)
    palette = _prefetcher_palette(order)
    core_values = sorted(data["cores"].unique())
    core_positions = {core: idx for idx, core in enumerate(core_values)}
    x_ticks = list(range(len(core_values)))

    fig, axes = plt.subplots(1, len(scopes), figsize=(5.0 * len(scopes), 3), sharey=True)
    axes = np.atleast_1d(axes)
    global_min: Optional[float] = None
    global_max: Optional[float] = None

    for idx, (ax, scope) in enumerate(zip(axes, scopes)):
        mask = data["scope"].str.lower() == scope.lower()
        subset = data[mask].copy()
        if subset.empty:
            ax.set_axis_off()
            ax.set_title(f"{scope} (no data)")
            continue

        marker_cycle = cycle(DEFAULT_MARKERS)
        linestyle_cycle = cycle(DEFAULT_LINESTYLES)
        shaded_regions: List[Tuple[float, float, str]] = []
        if regions:
            for start, end, label in regions:
                if start not in core_positions or end not in core_positions:
                    continue
                left_idx = min(core_positions[start], core_positions[end]) - 0.5
                right_idx = max(core_positions[start], core_positions[end]) + 0.5
                ax.axvspan(
                    left_idx,
                    right_idx,
                    facecolor="#f1f3fa",
                    edgecolor="#9a9a9a",
                    linewidth=1.0,
                    linestyle=(0, (4, 3)),
                    alpha=0.35,
                    zorder=0,
                )
                shaded_regions.append((left_idx, right_idx, label))

        for label in order:
            pref_subset = subset[subset["prefetcher_label"] == label].sort_values("cores")
            if pref_subset.empty:
                continue
            x_coords = pref_subset["cores"].map(core_positions).to_numpy()
            marker = _resolve_marker(label, marker_cycle)
            linestyle = _resolve_linestyle(label, linestyle_cycle)
            line_color = palette.get(label, "#4c72b0")
            marker_face = "#fffffb" if marker in {"o", "s", "D"} else line_color
            ax.plot(
                x_coords,
                pref_subset["speedup"],
                marker=marker,
                markersize=7,
                linewidth=2.3,
                linestyle=linestyle,
                label=label,
                color=line_color,
                markerfacecolor=marker_face,
                markeredgecolor=line_color,
                zorder=3,
            )

        ax.set_title(scope)
        ax.set_xlabel("Number of cores")
        if idx == 0:
            ax.set_ylabel(ylabel)
        ax.set_xticks(x_ticks)
        ax.set_xticklabels([str(c) for c in core_values])
        ax.set_xlim(-0.2, len(core_values) - 0.8)
        ax.grid(axis="y", linestyle="--", linewidth=0.6, alpha=0.6)
        ax.spines["right"].set_visible(False)
        ax.spines["top"].set_visible(False)

        local_min = float(subset["speedup"].min())
        local_max = float(subset["speedup"].max())
        global_min = local_min if global_min is None else min(global_min, local_min)
        global_max = local_max if global_max is None else max(global_max, local_max)

    if global_min is not None and global_max is not None:
        lower = 0.0 if global_min <= 0 else max(0.5, global_min * 0.9)
        upper = global_max * 1.05 if global_max > 0 else 1.0
        for ax in axes:
            if ax.has_data():
                ax.set_ylim(lower, upper)

    handles = []
    labels = []
    for ax in axes:
        if ax.has_data():
            handles, labels = ax.get_legend_handles_labels()
            if handles:
                break
    if handles:
        fig.legend(
            handles,
            labels,
            loc="upper center",
            bbox_to_anchor=(0.5, 1.1),
            ncol=min(len(order), 5),
            framealpha=0.9,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=300, bbox_inches="tight", pad_inches=0.02)
    try:
        fig.savefig(output.with_suffix(".pdf"), bbox_inches="tight")
    except Exception:
        pass
    plt.close(fig)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot prefetcher scaling across core counts.")
    parser.add_argument(
        "--inputs",
        nargs="+",
        default=None,
        help="List of CORE:CSV pairs (e.g., 1:path/to/single.csv 2:path/to/two.csv ...).",
    )
    parser.add_argument(
        "--hetero-inputs",
        nargs="+",
        default=DEFAULT_HETERO_INPUT_SPECS,
        help="List of CORE:CSV pairs used for the heterogeneous panels/averages.",
    )
    parser.add_argument(
        "--prefetchers",
        nargs="*",
        default=[
            "dspatch",
            "gaze",
            "bingo_streaming_disable_overlap_pht_16x64",
            "step",
        ],
        help="Subset of prefetchers to include across all inputs.",
    )
    parser.add_argument(
        "--benchmarks",
        nargs="*",
        help="Optional list of benchmark groups (e.g., SPEC17) to keep.",
    )
    parser.add_argument(
        "--benchmark-panels",
        nargs="*",
        default=None,
        help=(
            "Benchmark categories to highlight as individual subplots. "
            "Defaults to SPEC06/SPEC17/CloudSuite, or Heterogeneous with --heterogeneous."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "figures" / "multicore_scaling.png",
        help="Destination PNG file (default: figures/multicore_scaling.png).",
    )
    parser.add_argument(
        "--avg-output",
        type=Path,
        default=None,
        help=(
            "Optional output path for the homogeneous-vs-heterogeneous average figure. "
            "Default: same as --output with '_homo_heter_avg' suffix."
        ),
    )
    parser.add_argument(
        "--title",
        help="Optional plot title.",
    )
    parser.add_argument(
        "--ylabel",
        default="Speedup over no prefetching",
        help="Y-axis label (default: 'Speedup over no prefetching').",
    )
    parser.add_argument(
        "--regions",
        nargs="*",
        help="Optional shaded regions, e.g. '1-2:1 channel 3-4:2 channels'.",
    )
    parser.add_argument(
        "--heterogeneous",
        action="store_true",
        help=(
            "Plot heterogeneous mixes only. Rows are selected via --mix-prefix "
            "and aggregated under a single 'Heterogeneous' benchmark bucket."
        ),
    )
    parser.add_argument(
        "--mix-prefix",
        default="het-",
        help="Trace prefix used to identify heterogeneous mixes (default: 'het-').",
    )
    return parser.parse_args(argv)


def _resolve_panel_list(raw_panels: Optional[Sequence[str]], defaults: Sequence[str]) -> List[str]:
    if raw_panels is None:
        return list(defaults)
    deduped: List[str] = []
    seen: set[str] = set()
    for panel in raw_panels:
        stripped = panel.strip()
        if not stripped or stripped.lower() == "avg":
            continue
        key = stripped.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(stripped)
    return deduped if deduped else list(defaults)


def _default_avg_output(output: Path) -> Path:
    return output.with_name(f"{output.stem}_homo_heter_avg{output.suffix}")


def _print_exact_values(data: pd.DataFrame, scopes: Sequence[str], heading: str) -> None:
    """Print exact plotted speedup values to stdout."""
    print(f"\n=== {heading} ===")
    if data.empty:
        print("[no data]")
        return

    for scope in scopes:
        scope_df = data[data["scope"].str.lower() == scope.lower()].copy()
        if scope_df.empty:
            continue
        scope_df = scope_df[["prefetcher_label", "cores", "speedup"]].dropna(subset=["speedup"])
        if scope_df.empty:
            continue
        scope_df = scope_df.sort_values(["prefetcher_label", "cores"])
        print(f"\n[{scope}]")
        for row in scope_df.itertuples(index=False):
            try:
                core_label = str(int(row.cores))
            except Exception:
                core_label = str(row.cores)
            print(
                f"{row.prefetcher_label:>16}  cores={core_label:>2}  speedup={float(row.speedup):.12f}"
            )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    homo_input_specs = parse_input_specs(args.inputs or DEFAULT_HOMO_INPUT_SPECS)
    heter_input_specs = parse_input_specs(args.hetero_inputs or DEFAULT_HETERO_INPUT_SPECS)
    regions = parse_region_specs(args.regions)

    if args.heterogeneous:
        panel_list = _resolve_panel_list(args.benchmark_panels, [HETEROGENEOUS_BENCHMARK])
        data = build_scaling_dataframe(
            heter_input_specs,
            args.prefetchers,
            panels=panel_list,
            benchmarks=args.benchmarks,
            heterogeneous=True,
            mix_prefix=args.mix_prefix,
        )
        plot_scaling_panels(
            data,
            panel_list,
            args.output,
            ylabel=args.ylabel,
            title=args.title,
            regions=regions,
        )
        _print_exact_values(data, panel_list, "Heterogeneous Scaling Values")
        return 0

    # Figure 1: homogeneous benchmark-suite panels (SPEC06/SPEC17/CloudSuite by default).
    suite_panels = _resolve_panel_list(args.benchmark_panels, DEFAULT_BENCHMARK_PANELS)
    homo_data = build_scaling_dataframe(
        homo_input_specs,
        args.prefetchers,
        panels=suite_panels,
        benchmarks=args.benchmarks,
        heterogeneous=False,
        mix_prefix=args.mix_prefix,
    )
    plot_scaling_panels(
        homo_data,
        suite_panels,
        args.output,
        ylabel=args.ylabel,
        title=args.title,
        regions=regions,
    )
    _print_exact_values(homo_data, suite_panels, "Homogeneous Benchmark-Suite Scaling Values")

    # Figure 2: homogeneous global geomean vs heterogeneous global geomean.
    homo_avg = homo_data[homo_data["scope"].str.lower() == "avg"].copy()
    homo_avg["scope"] = "Homogeneous Avg"
    avg_output = args.avg_output if args.avg_output is not None else _default_avg_output(args.output)

    try:
        heter_data = build_scaling_dataframe(
            heter_input_specs,
            args.prefetchers,
            panels=[HETEROGENEOUS_BENCHMARK],
            benchmarks=args.benchmarks,
            heterogeneous=True,
            mix_prefix=args.mix_prefix,
        )
    except ValueError as exc:
        print(f"[WARN] Skipping homogeneous-vs-heterogeneous average figure: {exc}")
        return 0

    heter_avg = heter_data[heter_data["scope"].str.lower() == "avg"].copy()
    heter_avg["scope"] = "Heterogeneous Avg"
    avg_compare = pd.concat([homo_avg, heter_avg], ignore_index=True, sort=False)
    avg_compare = avg_compare.dropna(subset=["speedup"])
    compare_scopes = ["Homogeneous Avg", "Heterogeneous Avg"]
    avg_compare = avg_compare[avg_compare["scope"].isin(compare_scopes)]
    if avg_compare.empty:
        print("[WARN] Skipping homogeneous-vs-heterogeneous average figure: no average rows available.")
        return 0

    avg_title = (
        f"{args.title} (Homogeneous Avg + Heterogeneous Avg)"
        if args.title
        else "Homogeneous Avg + Heterogeneous Avg"
    )
    plot_scaling_panels(
        avg_compare,
        compare_scopes,
        avg_output,
        ylabel=args.ylabel,
        title=avg_title,
        regions=regions,
    )
    _print_exact_values(avg_compare, compare_scopes, "Homogeneous vs Heterogeneous Average Values")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
