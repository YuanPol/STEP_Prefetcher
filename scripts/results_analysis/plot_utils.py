#!/usr/bin/env python3
"""
Shared helper utilities for ChampSim plotting scripts.

"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import math
import numpy as np
import pandas as pd
import seaborn as sns
import warnings
from itertools import cycle
from matplotlib.patches import Patch
from matplotlib import colors as mcolors
from matplotlib.ticker import MaxNLocator, MultipleLocator, PercentFormatter

# Import workload definitions to construct the benchmark category mapping.
from scripts.workloads import (  # type: ignore
    workloads_cloudsuite,
    workloads_spec06,
    workloads_spec17,
)

# -----------------------------------------------------------------------------
# Styling utilities


def apply_standard_style() -> None:
    """Apply a consistent Seaborn theme used across all plots."""
    sns.set_theme(style="whitegrid", font_scale=1.1)
    plt.rcParams.update(
        {
            "figure.autolayout": True,
            "axes.labelweight": "semibold",
            "axes.titleweight": "semibold",
            "legend.frameon": True,
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "DejaVu Sans"],
            "axes.labelsize": 16,
            "axes.titlesize": 12,
            "xtick.labelsize": 14,
            "ytick.labelsize": 14,
            "legend.fontsize": 12,
            "figure.titlesize": 18,
            "text.color": "#111111",
        }
    )


def ensure_dir(path: Path) -> None:
    """Create the parent directory for a path if it does not exist."""
    path.mkdir(parents=True, exist_ok=True)


def _style_legend(
    legend: Optional[plt.Legend],
    font_size: Optional[float] = None,
    title_size: Optional[float] = None,
) -> None:
    """Apply consistent styling to legends (smaller font, translucent frame)."""
    if legend is None:
        return
    resolved_font_size = font_size if font_size is not None else 12
    resolved_title_size = title_size if title_size is not None else (font_size if font_size is not None else 10)
    legend.get_frame().set_alpha(0.85)
    if legend.get_title():
        legend.get_title().set_fontsize(resolved_title_size)
    for text in legend.get_texts():
        text.set_fontsize(resolved_font_size)


# -----------------------------------------------------------------------------
# Metrics loading and classification


def _build_category_map() -> Dict[str, str]:
    """Construct a mapping from trace short-name to benchmark category."""
    mapping: Dict[str, str] = {}

    def record(entries: Sequence[Sequence], category: str) -> None:
        for entry in entries:
            # Each workload entry is [trace_path, short_name, optional flags...]
            if len(entry) < 2:
                continue
            short = entry[1]
            mapping.setdefault(short, category)

    record(workloads_spec06, "SPEC06")
    record(workloads_spec17, "SPEC17")
    record(workloads_cloudsuite, "CloudSuite")

    return mapping


CATEGORY_MAP = _build_category_map()
CATEGORY_ORDER = ["SPEC06", "SPEC17", "CloudSuite", "Avg", "Overall GMean"]


def _extract_program_name(trace_path: str) -> Optional[str]:
    """
    Derive a human-readable program name from a workload trace filename.

    Expected formats include SPEC-style ``<id>.<program>-<variant>`` entries and
    SPEC17 ``<id>.<program>_s-<variant>`` names. Only SPEC-style entries are
    currently translated.
    """
    name = Path(trace_path).name
    stem = name
    for suffix in (".champsimtrace", ".xz", ".gz"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    if "." not in stem:
        return None
    prefix, rest = stem.split(".", 1)
    if not prefix.isdigit():
        return None
    program = rest.split("-", 1)[0]
    for suffix in ("_s", "_b", "_c", "_d"):
        if program.endswith(suffix):
            program = program[: -len(suffix)]
    return program


def _build_program_display_map() -> Dict[str, str]:
    """Map SPEC short-name prefixes (e.g., ``607``) to readable program names."""
    mapping: Dict[str, str] = {}

    def register(entries: Sequence[Sequence]) -> None:
        for entry in entries:
            if len(entry) < 2:
                continue
            trace_path, short = entry[0], entry[1]
            if not isinstance(short, str):
                continue
            prefix = short.split("_", 1)[0]
            if not prefix.isdigit():
                continue
            friendly = _extract_program_name(str(trace_path))
            if not friendly:
                continue
            mapping.setdefault(prefix, friendly)

    register(workloads_spec06)
    register(workloads_spec17)
    register(workloads_cloudsuite)
    return mapping


TRACE_PROGRAM_NAMES = _build_program_display_map()

# Prefetcher display configuration (label, colour, hatch) used by all plots.
PREFETCHER_DISPLAY_NAMES: Dict[str, str] = {
    "sms": "SMS",
    "bingo": "Bingo",
    "dspatch": "DSPatch",
    "spp_ppf": "SPP-PPF",
    "ipcp_l1_ipcp_l2": "IPCP",
    "berti": "vBerti",
    "pmp": "PMP",
    "gaze": "Gaze",
    "gaze_l1_l2_fill": "Gaze",
    "step": "STEP",
    "step_l1_l2_fill_disable_second": "STEP",
    "bingo_streaming_disable_overlap_pht_16x64": "eBingo",
    "bingo_streaming_disable_overlap_l1_l2_fill": "eBingo",
    "step_l1_l2_fill_disable_second_step": "STEP",
    "step_full_ft256_at128_pt8": "STEP_FULL",
    "step_disable_first_ft256_at128_pt8": "STEP_D1",
    "step_disable_second_ft256_at128_pt8": "STEP_D2",
    "step_disable_third_ft256_at128_pt8": "STEP_D3",
    "step_disable_second_ft32_at128_pt8": "FT_32",
    "step_disable_second_ft64_at128_pt8": "FT_64",
    "step_disable_second_ft128_at128_pt8": "FT_128",
    "step_disable_second_ft512_at128_pt8": "FT_512",
    "step_disable_second_ft1024_at128_pt8": "FT_1024",
    "step_disable_second_ft256_at32_pt8": "AT_32",
    "step_disable_second_ft256_at64_pt8": "AT_64",
    "step_disable_second_ft256_at256_pt8": "AT_256",
    "step_disable_second_ft256_at512_pt8": "AT_512",
    "step_disable_second_ft256_at128_pt4": "PT_4",
    "step_disable_second_ft256_at128_pt16": "PT_16",
    "step_disable_second_ft256_at128_pt32": "PT_32",
    "step_disable_second_ft256_at128_pt64": "PT_64",
    "step_disable_second_ft256_at128_pt128": "PT_128",
    "step_disable_second_ft512_at256_pt16": "STEP_L",
}

PREFETCHER_COLOURS: Dict[str, str] = {
    "SMS": "#a77d0b",
    "Bingo": "#8c564b",
    "DSPatch": "#1b80d6",
    "SPP-PPF": "#d62728",
    "PMP": "#9467bd",
    "Gaze": "#ff7f0e",
    "STEP": "#2ca02c",
    "eBingo": "#8c564b",
    "IPCP": "#1f77b4",
    "vBerti":"#7f7f7f",
    "STEP_FULL": "#2ca02c",
    "STEP_D1": "#98df8a",
    "STEP_D2": "#31a354",
    "STEP_D3": "#74c476",
    "FT_32": "#1f77b4",
    "FT_64": "#ff7f0e",
    "FT_128": "#2ca02c",
    "FT_256": "#9467bd",
    "FT_512": "#d62728",
    "AT_32": "#8c564b",
    "AT_128": "#e377c2",
    "AT_256": "#7f7f7f",
    "AT_512": "#bcbd22",
    "PT_4": "#17becf",
    "PT_16": "#1f77b4",
    "PT_32": "#ff7f0e",
    "PT_64": "#2ca02c",
    "PT_128": "#d62728",
}

PREFETCHER_HATCHES: Dict[str, str] = {
    "SMS": "",
    "Bingo": "--",
    "DSPatch": "++",
    "SPP-PPF": "..",
    "PMP": "xx",
    "Gaze": "\\\\",
    "STEP": "//",
    "eBingo": "--",
    "IPCP": "**",
    "vBerti":"o",
    "STEP_FULL": "",
    "STEP_D1": "--",
    "STEP_D2": "..",
    "STEP_D3": "++",
    "FT_32": "",
    "FT_64": "..",
    "FT_128": "xx",
    "FT_256": "//",
    "FT_512": "\\\\",
    "AT_32": "",
    "AT_128": "..",
    "AT_256": "xx",
    "AT_512": "//",
    "PT_4": "",
    "PT_16": "..",
    "PT_32": "xx",
    "PT_64": "//",
    "PT_128": "\\\\",
}

DEFAULT_HATCH_CYCLE = ["", "xx", "..", "++", "--", "**"]


def normalise_trace_id(raw: str) -> str:
    """
    Strip the run prefix (e.g., ``v00-``) from the trace identifier recorded in
    the metrics CSV.
    """
    return raw.split("-", 1)[-1] if "-" in raw else raw


def get_trace_display_name(trace_base: str) -> str:
    """
    Convert the internal trace identifier (e.g., ``607_3477``) into a more
    descriptive label such as ``cactuBSSN (3477)`` when possible.
    """
    prefix = trace_base.split("_", 1)[0]
    friendly = TRACE_PROGRAM_NAMES.get(prefix)
    if not friendly:
        return trace_base
    suffix = trace_base.split("_", 1)[1] if "_" in trace_base else ""
    if suffix:
        return f"{friendly} ({suffix})"
    return friendly


def _infer_benchmark_from_name(name: str) -> Optional[str]:
    lowered = name.lower()
    prefix_map = {
        ("cloud", "cass", "nutch", "stream", "graph", "media", "data", "specjbb", "memc"): "CloudSuite",
    }
    for prefixes, category in prefix_map.items():
        for prefix in prefixes:
            if lowered.startswith(prefix):
                return category
    return None


def load_metrics(csv_path: Path) -> pd.DataFrame:
    """Load the metrics CSV produced by ``collect_metrics.py``."""
    df = pd.read_csv(csv_path)
    df["run_prefix"] = df["trace"].apply(lambda raw: raw.split("-", 1)[0] if "-" in raw else "")
    df["trace_base"] = df["trace"].apply(normalise_trace_id)
    df["benchmark"] = df["trace_base"].map(CATEGORY_MAP)
    unknown_mask = df["benchmark"].isna()
    if unknown_mask.any():
        df.loc[unknown_mask, "benchmark"] = df.loc[unknown_mask, "trace_base"].apply(
            lambda name: _infer_benchmark_from_name(name) or "Unknown"
        )
    df["prefetcher_label"] = df["prefetcher"].apply(
        lambda name: PREFETCHER_DISPLAY_NAMES.get(name, name)
    )
    return df


def filter_prefetchers(df: pd.DataFrame, prefetchers: Optional[Sequence[str]]) -> pd.DataFrame:
    """Return a DataFrame filtered to the provided set of prefetchers."""
    if prefetchers:
        return df[df["prefetcher"].isin(prefetchers)].copy()
    return df.copy()


# -----------------------------------------------------------------------------
# Prefetch composition helpers


COVERAGE_COMPONENTS = (
    "Covered Misses",
    "Late Prefetches",
    "Uncovered Misses",
)

COVERAGE_PALETTE = {
    "Covered Misses": "#2ca02c",
    "Late Prefetches": "#9467bd",
    "Uncovered Misses": "#8c564b",
}

OVERPRED_COLOUR = "#d62728"
OVERPRED_HATCHES = {
    "Overprediction (Useless)": "///",
    "Overprediction (Cache Hit)": "...",
}

OVERPRED_COMPONENTS = (
    "Overprediction (Useless)",
    "Overprediction (Cache Hit)",
)

COMPOSITION_COMPONENTS = COVERAGE_COMPONENTS + OVERPRED_COMPONENTS
COMPOSITION_COLOURS = {
    **COVERAGE_PALETTE,
    "Overprediction (Useless)": OVERPRED_COLOUR,
    "Overprediction (Cache Hit)": OVERPRED_COLOUR,
}
COMPOSITION_HATCHES = {
    "Covered Misses": "",
    "Late Prefetches": "",
    "Uncovered Misses": "",
    "Overprediction (Useless)": OVERPRED_HATCHES["Overprediction (Useless)"],
    "Overprediction (Cache Hit)": OVERPRED_HATCHES["Overprediction (Cache Hit)"],
}


def compute_prefetch_composition(
    df: pd.DataFrame,
    cache_prefix: str = "cpu0_L2C",
    groupby_fields: Sequence[str] = ("prefetcher_label",),
    baseline_prefetcher: str = "no",
) -> pd.DataFrame:
    """
    Aggregate useful/useless/late/cache-hit prefetch counts for the specified cache.

    Parameters
    ----------
    df:
        The metrics DataFrame.
    cache_prefix:
        Name prefix used in the CSV columns (e.g., ``cpu0_L2C``).
    groupby_fields:
        Columns used to group the data prior to aggregation. Defaults to
        aggregating per-prefetcher across all traces.
    """
    issued_col = f"{cache_prefix}_prefetch_issued"
    useful_col = f"{cache_prefix}_prefetch_useful"
    useless_col = f"{cache_prefix}_prefetch_useless"
    hit_col = f"{cache_prefix}_prefetch_hit"
    late_col = f"{cache_prefix}_prefetch_late"
    load_access_col = f"{cache_prefix}_load_access"
    load_miss_col = f"{cache_prefix}_load_miss"

    required = {issued_col, useful_col, useless_col, hit_col, late_col, load_access_col, load_miss_col}
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise KeyError(f"Metrics file is missing columns required for composition plot: {missing}")

    grouped = df.groupby(list(groupby_fields), as_index=False)[list(required)].sum()

    baseline_fields = [field for field in groupby_fields if field not in ("prefetcher", "prefetcher_label")]
    baseline_df = df[df["prefetcher"] == baseline_prefetcher]
    if baseline_df.empty:
        raise ValueError(
            f"Baseline prefetcher '{baseline_prefetcher}' not present in the provided metrics."
        )
    if baseline_fields:
        baseline_grouped = (
            baseline_df.groupby(baseline_fields, as_index=False)[load_miss_col]
            .sum()
        )
        baseline_map = {
            tuple(row[baseline_fields]): row[load_miss_col]
            for _, row in baseline_grouped.iterrows()
        }
    else:
        total = float(baseline_df[load_miss_col].sum())
        baseline_map = {(): total}

    def baseline_key_from(row: pd.Series) -> Tuple:
        if not baseline_fields:
            return ()
        return tuple(row[field] for field in baseline_fields)

    def compute_row(row: pd.Series) -> pd.Series:
        useful = row[useful_col]
        late = row[late_col]
        nonlate = max(useful - late, 0)
        pref_miss = row[load_miss_col]
        base_key = baseline_key_from(row)
        baseline_miss = float(baseline_map.get(base_key, pref_miss))
        late_component = min(late, pref_miss)
        covered = max(baseline_miss - pref_miss, 0.0)
        uncovered = max(pref_miss - late_component, 0.0)
        overpred_useless = row[useless_col]
        overpred_hit = row[hit_col]
        overpred_total = overpred_useless + overpred_hit
        return pd.Series(
            {
                "Covered Misses": covered,
                "Late Prefetches": late,
                "Uncovered Misses": uncovered,
                "Overprediction": overpred_total,
                "Overprediction (Useless)": overpred_useless,
                "Overprediction (Cache Hit)": overpred_hit,
                "Prefetch Issued": row[issued_col],
                "Load Accesses": row[load_access_col],
                "Baseline Load Misses": baseline_miss,
            }
        )

    composition = grouped.apply(compute_row, axis=1)
    result = pd.concat([grouped[list(groupby_fields)], composition], axis=1)
    return result


def stack_composition_df(df: pd.DataFrame, value_cols: Sequence[str], id_vars: Sequence[str]) -> pd.DataFrame:
    """Convert the wide composition table into a long-form DataFrame suitable for stacked bars."""
    melted = df.melt(id_vars=list(id_vars), value_vars=list(value_cols), var_name="component", value_name="count")
    total = melted.groupby(list(id_vars))["count"].transform("sum").replace(0, pd.NA)
    melted["fraction"] = melted["count"] / total
    return melted


def _stacked_component_bars(
    ax: plt.Axes,
    data: pd.DataFrame,
    x_field: str,
    component_order: Sequence[str],
    palette: Dict[str, str],
) -> None:
    """Render a 100% stacked bar chart for the provided components."""
    bottoms = np.zeros(len(data))
    for component in component_order:
        if component not in data.columns:
            continue
        values = data[component].to_numpy()
        ax.bar(
            data[x_field],
            values,
            bottom=bottoms,
            label=component,
            color=palette.get(component),
            edgecolor="black",
        )
        bottoms += values


# -----------------------------------------------------------------------------
# Convenience helpers for system/parameter experiments


def parse_system_params(trace_base: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """
    Extract bandwidth/L2/LLC sizes from the trace identifier generated by
    ``run_system_sensitivity``.  Returns ``None`` for any field that cannot be
    parsed.
    """
    bw = l2 = llc = None
    parts = trace_base.split("_")
    for part in parts:
        if part.startswith("bw"):
            try:
                bw = int(part[2:])
            except ValueError:
                pass
        elif part.startswith("l2"):
            try:
                l2 = int(part[2:])
            except ValueError:
                pass
        elif part.startswith("llc"):
            try:
                llc = int(part[3:])
            except ValueError:
                pass
    return bw, l2, llc


def extract_variant_label(trace_base: str) -> str:
    """
    Extract the variant label from parameter/ablation experiment traces which
    use the ``<prefix>_<label>-<workload>`` naming convention.
    """
    return trace_base.split("_", 1)[0] if "_" in trace_base else trace_base


# -----------------------------------------------------------------------------
# Generic plotting utilities used by multiple experiments


def normalise_category_column(df: pd.DataFrame, column: str = "benchmark") -> pd.DataFrame:
    """Ensure the benchmark column is categorical with a stable ordering."""
    categories = [c for c in CATEGORY_ORDER if c in df[column].unique()]
    extras = [c for c in df[column].unique() if c not in categories]
    df[column] = pd.Categorical(df[column], categories=categories + extras, ordered=True)
    return df


def select_top_programs(
    df: pd.DataFrame,
    exclude_prefetchers: Sequence[str],
    top_n: int,
    metric: str = "speedup",
) -> List[str]:
    """Select programs with the highest maximum value for the specified metric."""
    candidate_df = df[~df["prefetcher"].isin(exclude_prefetchers)]
    if candidate_df.empty:
        return []
    max_metric = candidate_df.groupby("trace_base")[metric].max().sort_values(ascending=False)
    return list(max_metric.head(top_n).index)


def select_programs_by_category(
    df: pd.DataFrame,
    categories: Sequence[str],
    metric: str = "speedup",
    top_n: Optional[int] = None,
) -> List[str]:
    """Return programs that belong to the requested benchmark categories, ranked by the specified metric."""
    if not categories:
        return []
    requested = {cat.strip() for cat in categories}
    subset = df[df["benchmark"].isin(requested)]
    if subset.empty:
        return []
    ranked = subset.groupby("trace_base")[metric].max().sort_values(ascending=False)
    if top_n is not None and top_n > 0:
        ranked = ranked.head(top_n)
    return list(ranked.index)


def select_regression_programs(
    df: pd.DataFrame,
    prefetcher: str,
    threshold: float = 1.0,
    metric: str = "speedup",
    reference_prefetcher: Optional[str] = None,
) -> List[str]:
    """
    Return programs where the specified prefetcher underperforms.

    If ``reference_prefetcher`` is provided, the comparison is relative to that
    prefetcher (ratio < threshold). Otherwise, the absolute metric value is
    compared against ``threshold``.
    """
    target = df[df["prefetcher"] == prefetcher]
    if target.empty:
        return []

    if reference_prefetcher:
        reference = df[df["prefetcher"] == reference_prefetcher]
        if reference.empty:
            return []
        target_cols = target[["trace_base", metric]].rename(columns={metric: "target_value"})
        reference_cols = reference[["trace_base", metric]].rename(columns={metric: "reference_value"})
        merged = pd.merge(target_cols, reference_cols, on="trace_base", how="inner")
        merged = merged.dropna(subset=["target_value", "reference_value"])
        merged = merged[merged["reference_value"] > 0]
        if merged.empty:
            return []
        merged["ratio"] = merged["target_value"] / merged["reference_value"]
        regressions = merged[merged["ratio"] < threshold].sort_values("ratio")
        return list(regressions["trace_base"])

    regressions = target[target[metric] < threshold].copy()
    if regressions.empty:
        return []
    regressions = regressions.sort_values(metric)
    return list(regressions["trace_base"])


def _prefetcher_order(df: pd.DataFrame, override: Optional[Sequence[str]] = None) -> List[str]:
    """
    Return the plotting order of prefetchers.

    If ``override`` is provided, it is interpreted as a preferred sequence of
    display labels (e.g., ["STEP", "Gaze"]). Any labels not present in the
    current DataFrame are ignored. If no override is given, the order is the
    first-appearance order in the DataFrame.
    """
    observed = list(dict.fromkeys(df["prefetcher_label"]))
    if override:
        allowed = set(observed)
        ordered = [label for label in override if label in allowed]
        # Keep any remaining labels that were not specified at the end
        tail = [label for label in observed if label not in ordered]
        result = ordered + tail
    else:
        result = observed

    # Keep the primary STEP label at the far right in comparison plots.
    if "STEP" in result:
        result = [label for label in result if label != "STEP"] + ["STEP"]
    return result


def _prefetcher_palette(order: Sequence[str]) -> Dict[str, str]:
    """Resolve a colour palette for the requested label order."""
    fallback = iter(sns.color_palette("colorblind", len(order)))
    palette: Dict[str, str] = {}
    for label in order:
        palette[label] = PREFETCHER_COLOURS.get(label, next(fallback))
    return palette


def _prefetcher_hatch_cycle(order: Sequence[str]) -> List[str]:
    """Resolve hatch patterns for the requested label order."""
    hatch_list: List[str] = []
    fallback = cycle(DEFAULT_HATCH_CYCLE)
    for label in order:
        hatch = PREFETCHER_HATCHES.get(label)
        if hatch is None:
            hatch = next(fallback)
        hatch_list.append(hatch)
    return hatch_list


def _prefetcher_handles(order: Sequence[str], palette: Dict[str, str]) -> List[Patch]:
    """Return legend handles styled with both colour and hatch."""
    handles: List[Patch] = []
    for label in order:
        face = palette.get(label, "#cccccc")
        hatch = PREFETCHER_HATCHES.get(label, "")
        handles.append(Patch(facecolor=face, edgecolor="black", hatch=hatch, label=label))
    return handles


def _apply_bar_hatches(
    ax: plt.Axes,
    order: Sequence[str],
    palette: Optional[Dict[str, str]] = None,  # kept for API symmetry; not required here
) -> None:
    """
    Apply hatch patterns so each hue label (given by `order`) maps to a consistent hatch.

    Robust strategy (color-agnostic):
      • Do NOT rely on facecolor matching (seaborn/mpl may tweak colors/alpha).
      • Group bars by x-tick, sort bars left→right within each group, and map
        index 0..len(order)-1 to the hatch sequence from `_prefetcher_hatch_cycle(order)`.
      • This matches seaborn's usual "hue splits bars left→right" layout, and
        remains stable even if some hues are missing at certain x positions.
      • Finally, sync legend handles to use the same hatches.
    """
    hatches = _prefetcher_hatch_cycle(order)
    if not hatches or not ax.patches:
        return

    def is_visible_patch(p) -> bool:
        fc = p.get_facecolor()
        return not (len(fc) == 4 and fc[3] == 0) and p.get_width() > 0

    # Map each drawn bar (patch) to its nearest x tick (program index)
    tick_positions = np.asarray(ax.get_xticks())
    patches_by_prog: Dict[int, List] = {}
    for p in ax.patches:
        if not is_visible_patch(p):
            continue
        center = p.get_x() + p.get_width() / 2.0
        prog_idx = int(np.argmin(np.abs(tick_positions - center)))
        patches_by_prog.setdefault(prog_idx, []).append(p)

    # Within each x position, sort bars by x (left→right), then assign hatches
    applied = False
    group_size = len(order)
    for plist in patches_by_prog.values():
        plist.sort(key=lambda bar: bar.get_x())
        for hue_idx, patch in enumerate(plist):
            if hue_idx >= group_size:
                break
            hatch = hatches[hue_idx]
            if hatch:
                patch.set_hatch(hatch)
                applied = True

    if not applied:
        return

    # --- Sync legend handles to use the same hatches (so legend matches the bars) ---
    # Build label -> hatch map using the provided display order.
    hatch_for_label = {label: h for label, h in zip(order, hatches)}

    legend = ax.get_legend()
    if legend is None:
        return

    # Legend labels are the visible texts; map them to our hatches
    labels = [t.get_text() for t in legend.get_texts()]
    handles = legend.legend_handles if hasattr(legend, "legend_handles") else legend.legendHandles

    for handle, lab in zip(handles, labels):
        hatch = hatch_for_label.get(lab, "")
        try:
            # Most seaborn bar legends are Patch-like and accept set_hatch
            handle.set_hatch(hatch)
            handle.set_edgecolor("black")
            # Ensure the legend patch is visible even if facecolor is translucent
            if hasattr(handle, "set_linewidth"):
                handle.set_linewidth(1.0)
        except Exception:
            # Some backends may not support hatches on this handle type; skip safely.
            pass


def _aggregate_metric(series: pd.Series, metric: str) -> float:
    """Aggregate a metric series using the appropriate averaging strategy."""
    cleaned = series.dropna()
    if cleaned.empty:
        return float("nan")
    if "speedup" in metric.lower():
        cleaned = cleaned[cleaned > 0]
        if cleaned.empty:
            return float("nan")
        return float(np.exp(np.log(cleaned).mean()))
    return float(cleaned.mean())


def plot_metric_by_category(
    df: pd.DataFrame,
    metric: str,
    ylabel: str,
    output: Path,
    title: Optional[str] = None,
    prefetcher_order: Optional[Sequence[str]] = None,
) -> None:
    """Bar plot showing per-benchmark averages for the given metric."""
    overall_gmean_label = "Overall GMean"
    is_speedup_metric = "speedup" in metric.lower()
    pivot = (
        df.groupby(["benchmark", "prefetcher_label"])[metric]
        .apply(lambda series: _aggregate_metric(series, metric))
        .reset_index(name="value")
    )
    if pivot.empty:
        return
    pivot = pivot.rename(columns={"prefetcher_label": "prefetcher"})
    pivot = pivot[pivot["prefetcher"] != "no"].copy()
    pivot = pivot[pivot["benchmark"] != "Unknown"].copy()
    if pivot.empty:
        return
    valid_benchmarks = (
        pivot.groupby("benchmark")["value"]
        .sum()
    )
    valid_benchmarks = valid_benchmarks[valid_benchmarks != 0].index
    pivot = pivot[pivot["benchmark"].isin(valid_benchmarks)].copy()
    if pivot.empty:
        return
    avg = (
        pivot.groupby("prefetcher", as_index=False)["value"]
        .mean()
        .assign(benchmark="Avg")
    )
    extra_rows: List[pd.DataFrame] = []
    overall = pd.DataFrame(columns=["prefetcher", "value", "benchmark"])
    if is_speedup_metric:
        workload_level = df[df["benchmark"].isin(valid_benchmarks)].copy()
        workload_level = workload_level[workload_level["prefetcher"] != "no"]
        workload_level = workload_level[workload_level["prefetcher_label"].isin(pivot["prefetcher"].unique())]
        overall = (
            workload_level.groupby("prefetcher_label")[metric]
            .apply(lambda series: _aggregate_metric(series, metric))
            .reset_index(name="value")
            .rename(columns={"prefetcher_label": "prefetcher"})
            .assign(benchmark=overall_gmean_label)
        )
        if not overall.empty:
            extra_rows.append(overall)
    else:
        extra_rows.append(avg)
    pivot = pd.concat([pivot] + extra_rows, ignore_index=True, sort=False)
    if is_speedup_metric:
        print("\n=== Speedup ===")
        if not overall.empty:
            for _, row in overall.iterrows():
                print(f"{row['prefetcher']} Overall GMean: {row['value']:.4f}")
    pivot = normalise_category_column(pivot, column="benchmark")

    hue_order = _prefetcher_order(df, override=prefetcher_order)
    palette = _prefetcher_palette(hue_order)

    benchmark_order = [b for b in CATEGORY_ORDER if b in pivot["benchmark"].astype(str).unique()]
    if not benchmark_order:
        benchmark_order = list(dict.fromkeys(pivot["benchmark"].astype(str)))

    value_table = (
        pivot.assign(benchmark=pivot["benchmark"].astype(str))
        .pivot(index="benchmark", columns="prefetcher", values="value")
        .reindex(index=benchmark_order)
        .reindex(columns=hue_order)
    )

    num_prefetchers = max(len(hue_order), 1)
    bar_width = 0.2
    group_width = bar_width * num_prefetchers
    group_gap = max(0.10, bar_width * 1.2)
    group_stride = group_width + group_gap
    x_centers = np.arange(len(benchmark_order), dtype=float) * group_stride

    fig_width = max(10.0, len(benchmark_order) * group_stride * 1.15 + 2.0)
    plt.figure(figsize=(fig_width, 5))
    ax = plt.gca()

    for idx, prefetcher in enumerate(hue_order):
        if prefetcher not in value_table.columns:
            continue
        x_positions = x_centers - (group_width / 2.0) + (idx + 0.5) * bar_width
        series = value_table[prefetcher]
        valid = series.notna()
        if not valid.any():
            continue
        bars = ax.bar(
            x_positions[valid.to_numpy()],
            series[valid].to_numpy(),
            width=bar_width,
            color=palette.get(prefetcher, "#cccccc"),
            edgecolor="black",
            linewidth=1.0,
            label=prefetcher,
        )
        hatch = PREFETCHER_HATCHES.get(prefetcher, "")
        if hatch:
            for patch in bars:
                patch.set_hatch(hatch)

    ax.set_xticks(x_centers)
    ax.set_xticklabels(benchmark_order)
    plt.xlabel("Benchmark")
    plt.ylabel(ylabel)
    if title is None:
        pass
        # plt.title(f"{ylabel} by benchmark group")
    else:
        plt.title(title)
    if pivot["value"].max() <= 1.5 and "speedup" not in metric.lower():
        ax.yaxis.set_major_formatter(PercentFormatter(xmax=1.0))

    min_val = float(pivot["value"].min())
    max_val = float(pivot["value"].max())
    is_speedup_metric = "speedup" in metric.lower()
    if is_speedup_metric and min_val > 0:
        lower = min_val * 0.95 if max_val - min_val < 0.2 else max(min_val - 0.05, 0.5)
        upper = max_val * 1.05
        ax.set_ylim(lower, upper)

    for patch in ax.patches:
        height = patch.get_height()
        if math.isnan(height):
            continue
        if math.isclose(height, 0.0, abs_tol=1e-6):
            continue
        label = f"{height:.2f}"
        if pivot["value"].max() <= 1.5 and "speedup" not in metric.lower():
            label = f"{height:.0%}"
        ax.annotate(
            label,
            (patch.get_x() + patch.get_width() / 2, height),
            ha="center",
            va="bottom",
            fontsize=8,
            xytext=(0, 3),
            textcoords="offset points",
        )
    handles = _prefetcher_handles(hue_order, palette)
    legend_y = 1.10 if is_speedup_metric else 1.16
    legend = ax.legend(
        handles,
        [h.get_label() for h in handles],
        # title="Prefetcher",
        loc="upper center",
        bbox_to_anchor=(0.5, legend_y),
        ncol=min(len(hue_order), 8),
        framealpha=0.95,
    )
    _style_legend(legend)
    ensure_dir(output.parent)
    plt.savefig(output, dpi=300)
    try:
        plt.savefig(output.with_suffix('.pdf'), bbox_inches='tight')
    except Exception:
        pass
    plt.close()


def plot_metric_by_program(
    df: pd.DataFrame,
    programs: Sequence[str],
    metric: str,
    ylabel: str,
    output: Path,
    title: Optional[str] = None,
    y_cap: Optional[float] = None,
    append_average: bool = False,
    average_label: str = "Avg",
    annotate_average: bool = False,
    annotate_overflow_only: bool = False,
    legend_inside: bool = False,
    prefetcher_order: Optional[Sequence[str]] = None,
    average_source_df: Optional[pd.DataFrame] = None,
    figure_width_per_program: float = 0.8,
    min_figure_width: float = 12.0,
    figure_height: float = 7,
    bar_width: float = 0.6,
    axis_labelsize: Optional[float] = None,
    x_tick_labelsize: Optional[float] = None,
    y_tick_labelsize: Optional[float] = None,
    title_fontsize: Optional[float] = None,
    legend_fontsize: Optional[float] = None,
    value_label_fontsize: float = 9.0,
    y_tick_bins: Optional[int] = None,
    y_tick_step: Optional[float] = None,
) -> None:

    if not programs:
        return

    ordered_programs = list(dict.fromkeys(programs))
    subset = df[df["trace_base"].isin(ordered_programs)].copy()
    if subset.empty:
        return

    subset["trace_base"] = pd.Categorical(
        subset["trace_base"],
        categories=ordered_programs,
        ordered=True,
    )

    # ---- Append average ----
    if append_average:
        avg_source = average_source_df if average_source_df is not None else df
        avg_source = avg_source[
            avg_source["prefetcher"].isin(subset["prefetcher"].unique())
        ]

        avg = (
            avg_source.groupby(["prefetcher", "prefetcher_label"])[metric]
            .apply(lambda s: _aggregate_metric(s, metric))
            .reset_index(name=metric)
        )

        if not avg.empty:
            avg["trace_base"] = average_label
            subset = pd.concat([subset, avg], ignore_index=True)
            if average_label not in ordered_programs:
                ordered_programs.append(average_label)

    # ---- Final aggregation ----
    plot_data = (
        subset.groupby(
            ["trace_base", "prefetcher", "prefetcher_label"],
            as_index=False
        )[metric]
        .mean()
        .dropna(subset=[metric])
    )

    if plot_data.empty:
        return

    plot_data = plot_data.rename(columns={metric: "metric_value"})
    plot_data["plot_height"] = plot_data["metric_value"]

    # ---- Display name mapping ----
    display_order = [get_trace_display_name(name) for name in ordered_programs]
    display_map = dict(zip(ordered_programs, display_order))

    plot_data["display_label"] = plot_data["trace_base"].map(display_map)
    plot_data["display_label"] = pd.Categorical(
        plot_data["display_label"],
        categories=display_order,
        ordered=True,
    )

    if y_cap is not None:
        plot_data["plot_height"] = plot_data["plot_height"].clip(upper=y_cap)

    hue_order = _prefetcher_order(plot_data, override=prefetcher_order)
    palette = _prefetcher_palette(hue_order)

    plt.figure(figsize=(max(min_figure_width, len(ordered_programs) * figure_width_per_program), figure_height))

    ax = sns.barplot(
        data=plot_data,
        x="display_label",
        y="plot_height",
        hue="prefetcher_label",
        hue_order=hue_order,
        palette=palette,
        edgecolor="black",
        width=bar_width,
    )

    _apply_bar_hatches(ax, hue_order, palette)

    plt.xlabel("Program", fontsize=axis_labelsize)
    plt.ylabel(ylabel, fontsize=axis_labelsize)

    computed_title = f"{ylabel} by program" if title is None else title
    if computed_title:
        plt.title(computed_title, fontsize=title_fontsize)

    # ---- Y axis handling ----
    min_val = float(plot_data["metric_value"].min())
    max_val = float(plot_data["metric_value"].max())

    # Preserve unclipped metric values for overflow detection/labels.
    metric_lookup: Dict[Tuple[str, str], float] = {}
    for trace_base, prefetcher_label, metric_value in plot_data[
        ["trace_base", "prefetcher_label", "metric_value"]
    ].itertuples(index=False):
        if pd.notna(metric_value):
            metric_lookup[(str(trace_base), str(prefetcher_label))] = float(metric_value)

    # Track arrow-label stacking rank within each program (overflow + capped average).
    arrow_rank: Dict[Tuple[int, int], int] = {}
    max_arrow_count = 0
    if y_cap is not None:
        for prog_idx, program in enumerate(ordered_programs):
            rank = 0
            is_average_program = annotate_average and str(program) == str(average_label)
            for hue_idx, prefetcher in enumerate(hue_order):
                actual_value = metric_lookup.get((str(program), str(prefetcher)))
                if actual_value is None or not np.isfinite(actual_value):
                    continue
                is_overflow = actual_value > y_cap + 1e-9
                if is_overflow or is_average_program:
                    arrow_rank[(prog_idx, hue_idx)] = rank
                    rank += 1
            max_arrow_count = max(max_arrow_count, rank)

    lower = 0.7
    upper = max_val

    if y_cap is not None:
        upper = y_cap
        ax.axhline(y_cap, linestyle="--", linewidth=0.8, color="gray")

    plot_span = upper - lower
    if plot_span <= 0:
        plot_span = max(abs(upper), 1.0)

    # Keep label gaps tied to data scale so thin bars stay readable.
    non_overflow_offset = plot_span * 0.03
    overflow_base = plot_span * 0.12
    average_arrow_extra_gap = plot_span * 0.06
    overflow_step = plot_span * 0.08
    text_top_clearance = plot_span * 0.11

    if y_cap is not None and max_arrow_count > 0:
        extra_headroom = (
            overflow_base
            + average_arrow_extra_gap
            + (max_arrow_count - 1) * overflow_step
            + text_top_clearance
        )
    else:
        extra_headroom = plot_span * 0.20

    ax.set_ylim(lower, upper + extra_headroom)
    if y_tick_step is not None and y_tick_step > 0:
        ax.yaxis.set_major_locator(MultipleLocator(base=y_tick_step))
    elif y_tick_bins is not None and y_tick_bins > 1:
        ax.yaxis.set_major_locator(MaxNLocator(nbins=y_tick_bins))

    # ---- Stable annotation using containers ----
    ymin, ymax = ax.get_ylim()
    format_as_percent = max_val <= 1.5 and "speedup" not in metric.lower()

    for hue_idx, container in enumerate(ax.containers):

        prefetcher = hue_order[hue_idx]

        for prog_idx, bar in enumerate(container):

            if prog_idx >= len(ordered_programs):
                continue

            program = ordered_programs[prog_idx]
            bar_height = float(bar.get_height())
            actual_value = metric_lookup.get((str(program), str(prefetcher)), bar_height)

            overflow = (
                y_cap is not None
                and actual_value > y_cap + 1e-9
            )
            force_average_arrow = (
                annotate_average
                and program == average_label
                and y_cap is not None
            )

            should_label = not annotate_overflow_only

            if annotate_overflow_only:
                should_label = overflow

            if annotate_average and program == average_label:
                should_label = True

            if not should_label:
                continue

            label_value = actual_value
            label = f"{label_value:.2f}"

            if format_as_percent:
                label = f"{label_value:.0%}"

            x = bar.get_x() + bar.get_width() / 2

    
            if not overflow and not force_average_arrow:
                text_height = min(bar_height + non_overflow_offset, ymax - text_top_clearance)
                ax.annotate(
                    label,
                    (x, text_height),
                    ha="center",
                    va="bottom",
                    fontsize=value_label_fontsize,
                    clip_on=False,
                )

            else:

                rank = arrow_rank.get((prog_idx, hue_idx), 0)
                anchor_height = y_cap if overflow and y_cap is not None else bar_height
                arrow_base = overflow_base
                if force_average_arrow:
                    arrow_base += average_arrow_extra_gap
                text_height = anchor_height + arrow_base + rank * overflow_step
                text_height = min(text_height, ymax - text_top_clearance)

                ax.annotate(
                    label,
                    xy=(x, anchor_height),
                    xytext=(x, text_height),
                    textcoords="data",
                    ha="center",
                    va="bottom",
                    fontsize=value_label_fontsize,
                    arrowprops={
                        "arrowstyle": "-",
                        "linewidth": 0.8,
                        "color": "black",
                    },
                    clip_on=False,
                )

    plt.xticks(rotation=45, ha="right")
    if x_tick_labelsize is not None:
        ax.tick_params(axis="x", labelsize=x_tick_labelsize)
    if y_tick_labelsize is not None:
        ax.tick_params(axis="y", labelsize=y_tick_labelsize)

    if legend_inside:
        legend_loc = "upper left"
        legend_anchor = (0.01, 1.02)
        legend_ncol = min(len(hue_order), 2)
    else:
        legend_loc = "upper center"
        legend_anchor = (0.5, 1.02)
        legend_ncol = min(len(hue_order), 4)

    legend = ax.legend(
        title="Prefetcher",
        loc=legend_loc,
        bbox_to_anchor=legend_anchor,
        ncol=legend_ncol,
        framealpha=0.95,
        fancybox=True,
    )
    _style_legend(legend, font_size=legend_fontsize)

    ensure_dir(output.parent)
    plt.tight_layout()
    plt.savefig(output, dpi=300)
    try:
        plt.savefig(output.with_suffix(".pdf"), bbox_inches="tight")
    except Exception:
        pass

    plt.close()



def plot_prefetch_composition(
    df: pd.DataFrame,
    output: Path,
    cache_prefix: str = "cpu0_L2C",
    title: Optional[str] = None,
    group_fields: Sequence[str] = ("prefetcher",),
    facet_field: Optional[str] = None,
    facet_order: Optional[Sequence[str]] = None,
    programs: Optional[Sequence[str]] = None,
    append_average: bool = False,
    average_label: str = "Avg",
    prefetcher_order: Optional[Sequence[str]] = None,
    baseline_prefetcher: str = "no",
    show_title: bool = False,
    show_xlabel: bool = False,
    ylabel_fontsize: Optional[float] = None,
    tick_labelsize: Optional[float] = None,
    xtick_labelsize: Optional[float] = None,
    legend_fontsize: Optional[float] = None,
    legend_loc: str = "upper center",
    prefetcher_tick_rotation: float = 45.0,
    figure_height: float = 8,
    group_label_fontsize: float = 20.0,
    group_label_y_factor: float = -0.1,
    legend_rows: Optional[int] = None,
) -> None:
    """
    Plot coverage vs. overprediction breakdown as a single capped stacked-bar chart.

    Font sizes for the y-label, ticks and legend can be overridden when desired.
    """

    if programs is not None:
        df = df[df["trace_base"].isin(programs)].copy()
        if df.empty:
            return

    resolved_fields = tuple(
        "prefetcher_label" if field == "prefetcher" else field for field in group_fields
    )
    resolved_facet = "prefetcher_label" if facet_field == "prefetcher" else facet_field

    if (
        "benchmark" in df.columns
        and ("benchmark" in resolved_fields or resolved_facet == "benchmark")
    ):
        df = df[df["benchmark"] != "Unknown"].copy()
        if df.empty:
            return

    comp = compute_prefetch_composition(
        df,
        cache_prefix=cache_prefix,
        groupby_fields=resolved_fields,
        baseline_prefetcher=baseline_prefetcher,
    )
    if comp.empty:
        return
    if "prefetcher_label" in comp.columns:
        comp = comp.rename(columns={"prefetcher_label": "prefetcher"})
    group_columns = tuple("prefetcher" if field == "prefetcher_label" else field for field in resolved_fields)

    if "prefetcher" in comp.columns:
        comp = comp[comp["prefetcher"] != baseline_prefetcher]
        if comp.empty:
            return

    if append_average and "trace_base" in comp.columns:
        grouping_for_avg = tuple(col for col in group_columns if col != "trace_base")
        if grouping_for_avg:
            sum_columns = list(COMPOSITION_COMPONENTS) + [
                "Overprediction",
                "Prefetch Issued",
                "Load Accesses",
                "Baseline Load Misses",
            ]
            avg_rows = (
                comp.groupby(list(grouping_for_avg), as_index=False)[sum_columns].sum()
            )
            avg_rows["trace_base"] = average_label
            comp = pd.concat([comp, avg_rows], ignore_index=True)
            if resolved_facet == "trace_base":
                if facet_order is not None:
                    existing_order = list(facet_order)
                elif programs is not None:
                    existing_order = list(dict.fromkeys(list(programs)))
                else:
                    existing_order = list(dict.fromkeys(comp["trace_base"]))
                if average_label not in existing_order:
                    existing_order.append(average_label)
                facet_order = existing_order

    fraction_df = comp.copy()
    baseline_denom = fraction_df["Baseline Load Misses"].replace(0, pd.NA)
    fraction_cols = list(dict.fromkeys(COMPOSITION_COMPONENTS + ("Overprediction",)))
    for column in fraction_cols:
        if column in fraction_df.columns:
            fraction_df[column] = fraction_df[column] / baseline_denom
    fraction_df = fraction_df.fillna(0.0)

    axis_fields: List[str] = []
    if resolved_facet:
        axis_fields = [resolved_facet]
    else:
        axis_fields = [field for field in group_columns if field != "prefetcher"]
    axis_fields = [field for field in axis_fields if field in fraction_df.columns]

    def format_group_label(key: Tuple) -> str:
        if not key:
            return "All"
        parts = [str(val) for val in key if not pd.isna(val) and val != ""]
        if not parts:
            return "All"
        return parts[0] if len(parts) == 1 else " / ".join(parts)

    def build_group_key(row: pd.Series) -> Tuple:
        if not axis_fields:
            return tuple()
        return tuple(row.get(field) for field in axis_fields)

    fraction_df["_group_key"] = fraction_df.apply(build_group_key, axis=1)
    fraction_df["_group_label"] = fraction_df["_group_key"].apply(format_group_label)

    unique_keys = list(dict.fromkeys(fraction_df["_group_key"]))
    if axis_fields and facet_order is not None:
        ordered_group_keys: List[Tuple] = []
        for label in facet_order:
            for key in unique_keys:
                first = key[0] if key else None
                if first == label and key not in ordered_group_keys:
                    ordered_group_keys.append(key)
        for key in unique_keys:
            if key not in ordered_group_keys:
                ordered_group_keys.append(key)
    else:
        ordered_group_keys = unique_keys

    prefetcher_labels = [
        label for label in list(dict.fromkeys(fraction_df["prefetcher"])) if pd.notna(label)
    ]
    if not prefetcher_labels:
        return

    if "prefetcher_label" in df.columns:
        pref_sequence = _prefetcher_order(df, override=prefetcher_order)
    elif prefetcher_order is not None:
        pref_sequence = list(prefetcher_order)
    else:
        pref_sequence = []
    pref_sequence = list(dict.fromkeys(pref_sequence))

    resolved_prefetchers = [label for label in pref_sequence if label in prefetcher_labels]
    if not resolved_prefetchers:
        resolved_prefetchers = prefetcher_labels

    ordered_rows: List[pd.Series] = []
    for group_key in ordered_group_keys:
        subset = fraction_df[fraction_df["_group_key"] == group_key]
        if subset.empty:
            continue
        for label in resolved_prefetchers:
            row = subset[subset["prefetcher"] == label]
            if row.empty:
                continue
            ordered_rows.append(row.iloc[0])
    if not ordered_rows:
        return

    ordered_df = pd.DataFrame(ordered_rows).reset_index(drop=True)
    for column in COMPOSITION_COMPONENTS:
        if column not in ordered_df.columns:
            ordered_df[column] = 0.0

    ordered_df["_total_fraction"] = ordered_df[list(COMPOSITION_COMPONENTS)].sum(axis=1)
    ordered_df["prefetcher_display"] = ordered_df["prefetcher"].fillna("Unknown").astype(str)

    bar_width = 1.0
    group_gap = 0.6
    group_entries: List[Tuple[Tuple, pd.Index]] = []
    for group_key in ordered_group_keys:
        mask = ordered_df["_group_key"] == group_key
        if not mask.any():
            continue
        group_entries.append((group_key, ordered_df.index[mask]))
    if not group_entries:
        return
    x_positions = np.zeros(len(ordered_df), dtype=float)
    group_spans: List[Tuple[Tuple, float, float, str]] = []
    current_x = 0.0
    for idx, (group_key, idxs) in enumerate(group_entries):
        start_center = current_x
        for row_idx in idxs:
            x_positions[row_idx] = current_x
            current_x += 1.0
        end_center = current_x - 1.0
        label = ordered_df.loc[idxs[0], "_group_label"]
        group_spans.append(
            (group_key, start_center - bar_width / 2.0, end_center + bar_width / 2.0, label)
        )
        if idx < len(group_entries) - 1:
            current_x += group_gap
    ordered_df["x_position"] = x_positions

    cap_value = 2.0
    visible_by_component = {component: [] for component in COMPOSITION_COMPONENTS}
    for _, row in ordered_df.iterrows():
        bottom = 0.0
        for component in COMPOSITION_COMPONENTS:
            value = float(row.get(component, 0.0))
            if bottom >= cap_value:
                visible = 0.0
            else:
                visible = min(value, cap_value - bottom)
            visible_by_component[component].append(max(visible, 0.0))
            bottom += value

    fig_width = max(14.0, len(ordered_df) * 0.75)
    fig, ax = plt.subplots(figsize=(fig_width, figure_height))

    if axis_fields:
        for span_idx, (_, start_edge, end_edge, label) in enumerate(group_spans):
            color = "#f3f3f3" if span_idx % 2 == 0 else "#ffffff"
            ax.axvspan(start_edge, end_edge, color=color, alpha=0.4, zorder=-2)
            ax.text(
                (start_edge + end_edge) / 2.0,
                group_label_y_factor * cap_value,
                label,
                ha="center",
                va="top",
                fontsize=group_label_fontsize,
                clip_on=False,
            )

    ax.set_axisbelow(True)
    ax.grid(axis="y", linestyle="--", linewidth=0.6, alpha=0.5)

    x_positions = ordered_df["x_position"].to_numpy()
    bottoms = np.zeros(len(ordered_df), dtype=float)
    legend_components: List[str] = []
    for component in COMPOSITION_COMPONENTS:
        heights = np.asarray(visible_by_component[component], dtype=float)
        if not np.any(heights > 1e-9):
            continue
        ax.bar(
            x_positions,
            heights,
            bottom=bottoms,
            width=bar_width,
            color=COMPOSITION_COLOURS.get(component, "#bbbbbb"),
            edgecolor="black",
            linewidth=0.8,
            hatch=COMPOSITION_HATCHES.get(component, ""),
        )
        legend_components.append(component)
        bottoms += heights

    if len(x_positions):
        x_min = float(np.min(x_positions))
        x_max = float(np.max(x_positions))
    else:
        x_min = x_max = 0.0

    resolved_ylabel_size = ylabel_fontsize if ylabel_fontsize is not None else 22
    resolved_y_tick_size = tick_labelsize if tick_labelsize is not None else 22
    resolved_x_tick_size = (
        xtick_labelsize
        if xtick_labelsize is not None
        else (tick_labelsize if tick_labelsize is not None else 14)
    )
    resolved_legend_size = legend_fontsize if legend_fontsize is not None else 20

    ax.set_xlim(x_min - bar_width / 2.0, x_max + bar_width / 2.0)
    ax.set_ylim(0, cap_value)
    ax.set_ylabel("Fraction of baseline load misses", fontsize=resolved_ylabel_size)
    if show_xlabel:
        axis_desc = ", ".join(field.replace("_", " ").title() for field in axis_fields)
        if axis_desc:
            ax.set_xlabel(f"Prefetcher grouped by {axis_desc}")
        else:
            ax.set_xlabel("Prefetcher")
    else:
        ax.set_xlabel("")
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1.0))
    ax.set_xticks(x_positions)
    label_ha = "right" if abs(prefetcher_tick_rotation) > 1e-6 else "center"
    ax.set_xticklabels(
        ordered_df["prefetcher_display"],
        rotation=prefetcher_tick_rotation,
        ha=label_ha,
        fontsize=resolved_x_tick_size,
    )
    ax.tick_params(axis="y", labelsize=resolved_y_tick_size)

    totals = ordered_df["_total_fraction"].to_numpy()
    for idx, total in enumerate(totals):
        if total <= cap_value + 1e-9:
            continue
        ax.annotate(
            f"{total:.0%}",
            xy=(x_positions[idx], cap_value),
            xytext=(x_positions[idx], cap_value + 0.05 * cap_value),
            textcoords="data",
            ha="center",
            va="bottom",
            fontsize=14,
            arrowprops={"arrowstyle": "-", "linewidth": 0.8, "color": "black"},
            clip_on=False,
        )

    if legend_components:
        handles = [
            Patch(
                facecolor=COMPOSITION_COLOURS.get(comp, "#bbbbbb"),
                edgecolor="black",
                hatch=COMPOSITION_HATCHES.get(comp, ""),
                label=comp,
            )
            for comp in legend_components
        ]
        if legend_rows is not None and legend_rows > 0:
            legend_ncol = max(1, int(math.ceil(len(legend_components) / legend_rows)))
        else:
            legend_ncol = (
                max(1, min(len(legend_components), 5))
                if legend_loc == "upper center"
                else max(1, min(len(legend_components), 2))
            )
        legend_kwargs = {
            "loc": legend_loc,
            "framealpha": 0.95,
            "ncol": legend_ncol,
        }
        if legend_loc == "upper center":
            legend_kwargs["bbox_to_anchor"] = (0.5, 1.4)
            legend_kwargs["borderaxespad"] = 0.2
        legend = ax.legend(
            handles,
            [h.get_label() for h in handles],
            **legend_kwargs,
        )
        _style_legend(legend, font_size=resolved_legend_size)

    if show_title and title:
        ax.set_title(title)

    if abs(prefetcher_tick_rotation) > 1e-6:
        bottom_margin = 0.36 if axis_fields else 0.26
    else:
        bottom_margin = 0.28 if axis_fields else 0.18
    if axis_fields:
        bottom_margin += max(0.0, (-group_label_y_factor - 0.10))
    if resolved_x_tick_size > 14:
        bottom_margin += min(0.10, (resolved_x_tick_size - 14) * 0.01)
    top_margin = 0.88 if legend_loc == "upper center" else 0.92
    if legend_loc == "upper center" and legend_rows is not None and legend_rows > 1:
        top_margin -= min(0.10, 0.04 * (legend_rows - 1) + max(0.0, resolved_legend_size - 16) * 0.01)
    fig.subplots_adjust(left=0.08, right=0.98, top=top_margin, bottom=bottom_margin)

    ensure_dir(output.parent)
    save_dpi = 300
    max_render_pixels = 60000
    width_in, height_in = fig.get_size_inches()
    scale = min(
        1.0,
        max_render_pixels / max(width_in * save_dpi, 1.0),
        max_render_pixels / max(height_in * save_dpi, 1.0),
    )
    if scale < 1.0:
        fig.set_size_inches(width_in * scale, height_in * scale, forward=True)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        fig.savefig(output, dpi=save_dpi)
        try:
            fig.savefig(output.with_suffix('.pdf'), bbox_inches='tight')
        except Exception:
            pass
    plt.close(fig)

# -----------------------------------------------------------------------------
