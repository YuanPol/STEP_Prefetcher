# STEP Prefetcher

This repository contains the artifact used to evaluate **STEP**, the spatial footprint prefetcher proposed in:

> **STEP: Spatial Footprint Prefetcher with Multi-Point Temporal Triggers**
> Yuanji Ye, Oliver Lenke, Thomas Wild, Andreas Herkersdorf
>
> [10.1109/ISCA66397.2026.00095](https://doi.org/10.1109/ISCA66397.2026.00095)

The codebase is built on top of [ChampSim](https://github.com/ChampSim/ChampSim). This submission tree is a cleaned version of the development repository:

- traces are not included
- generated logs, JSON outputs, figures, and CSV results are not included
- run/build entry points are restricted to the experiment sets used in the paper

## Repository Layout

- `ChampSim/`
  ChampSim source tree and prefetcher implementations.
- `scripts/make/`
  Build scripts for the paper experiments.
- `scripts/experiments/`
  Run scripts and plotting scripts for the paper experiments.
- `scripts/results_analysis/`
  Metric collection and shared plotting utilities.
- `scripts/workloads.py`
  Single-core workloads and heterogeneous multi-core mixes.
- `traces/`
  Place downloaded trace files here.
- `log/`, `json/`, `figures/`
  Created/used for generated outputs.

## Tested Environment

The artifact was last validated on the following machine:

- OS: Ubuntu 24.04.4 LTS
- Kernel: Linux `6.17.0-1012-oem`
- Compiler: `g++ 13.3.0`
- Python: `3.12.3`
- Git: `2.43.0`
- Python packages:
  - `matplotlib 3.6.3`
  - `numpy 1.26.4`
  - `pandas 2.1.4`
  - `seaborn 0.13.2`

## Hardware Dependencies

The full campaign is compute- and storage-intensive. The evaluation machine used for the paper had:

- CPU: `2 x Intel Xeon Platinum 8462Y+`
- Logical CPUs: `128`
- Memory: `503 GiB RAM`

Smaller machines can still run the scripts, but you should reduce `--max-jobs` substantially and expect much longer runtimes.

## Software Dependencies

Install the standard build and scripting dependencies first.

```bash
sudo apt-get update
sudo apt-get install -y build-essential cmake git python3 python3-pip xz-utils
python3 -m pip install --user matplotlib numpy pandas seaborn
```

ChampSim uses `vcpkg` for its packaged dependencies:

```bash
cd ChampSim
git clone https://github.com/microsoft/vcpkg.git
./vcpkg/bootstrap-vcpkg.sh
./vcpkg/vcpkg install
```

## Data Dependencies

The paper experiments use the workload lists defined in [scripts/workloads.py](scripts/workloads.py).

- Single-core workload set:
  - `39` SPEC CPU2006 traces
  - `39` SPEC CPU2017 traces
  - `52` CloudSuite traces
  - Total: `130` traces
- Heterogeneous multi-core workload sets:
  - `50` random 2-core mixes
  - `50` random 4-core mixes
  - `50` random 8-core mixes

Trace sources:

- SPEC CPU2006 / SPEC CPU2017 ChampSim traces: [DPC-3 trace archive](https://dpc3.compas.cs.stonybrook.edu/champsim-traces/speccpu/)
- CloudSuite traces: [CRC-2 trace archive](https://bit.ly/2t2nkUj) (currently redirects to a Dropbox folder)

These are the same public ChampSim trace sources referenced by the
[Pythia artifact](https://github.com/CMU-SAFARI/Pythia#preparing-traces) and the
[upstream ChampSim documentation](https://github.com/ChampSim/ChampSim#download-dpc-3-trace).
The archives are maintained outside this repository and their availability is
controlled by their respective hosts. Keeping a local mirror is recommended.

Create the trace directory and download the files listed in
[scripts/workloads.py](scripts/workloads.py):

```bash
mkdir -p traces
# Download the required .champsimtrace.xz files from the archives above.
# Keep the original archive filenames and place the files directly in traces/.
```

The experiment scripts resolve traces as `traces/<filename>`. Before launching
the full campaign, check that all 130 expected single-core traces are present:

```bash
python3 - <<'PY'
from pathlib import Path
from scripts.workloads import workloads_all

trace_dir = Path("traces")
missing = [name for name, *_ in workloads_all if not (trace_dir / name).is_file()]
print(f"Expected: {len(workloads_all)}; found: {len(workloads_all) - len(missing)}; missing: {len(missing)}")
if missing:
    print("\n".join(missing))
    raise SystemExit(1)
PY
```

Trace files can be large and may have separate distribution terms. They are
ignored by Git and are not covered by this repository's MIT license.

## Setup

From the repository root:

```bash
cd /path/to/STEP
```

Build the binaries required by the paper:

```bash
python3 scripts/make/make_all.py
```

This compiles the binary sets used by:

- single-core L2 performance
- single-core L1-level experiments
- multi-core homogeneous and heterogeneous experiments
- multi-level prefetching
- ablation study
- parameter sweep
- system sensitivity
- storage sensitivity
- limited-way L2 prefetching

## Experiment Coverage

- Single-core L2:
  baseline `no`, `SMS`, `DSPatch`, `SPP-PPF`, `PMP`, `vBerti`, `Gaze`, `eBingo`, `STEP`
- Multi-core:
  baseline `no`, `DSPatch`, `Gaze`, `eBingo`, `STEP`
- L1-level:
  baseline `no`, `Gaze`, `eBingo`, `STEP`
- Multi-level:
  all L1/L2 combinations of `Gaze`, `STEP`, `eBingo`, `vBerti` except `vBerti+vBerti`, plus `IPCP`
- Ablation:
  `step_full_ft256_at128_pt8`, `step_disable_first_ft256_at128_pt8`, `step_disable_second_ft256_at128_pt8`, `step_disable_third_ft256_at128_pt8`
- Parameter sweep:
  STEP variants with
  - FT in `{32, 64, 128, 256, 512, 1024}` at `AT=128`, `PHT=8`
  - AT in `{32, 64, 128, 256, 512}` at `FT=256`, `PHT=8`
  - PHT in `{4, 8, 16, 32, 64, 128}` at `FT=256`, `AT=128`
- System sensitivity:
  baseline `no`, `Gaze`, `vBerti`, `SPP-PPF`, `eBingo`, `STEP`
- Storage sensitivity:
  storage variants of `STEP`, `Gaze`, `vBerti`, `Bingo`, `eBingo`, and `IPCP`
- Limited-way L2:
  baseline `no`, `Gaze`, `eBingo`, and `STEP`, with prefetches restricted to one L2 way

## Running Experiments

All paper experiments can be launched together with the shared global queue:

```bash
python3 scripts/experiments/run_all_experiments.py --max-jobs 32
```

By default, completed runs are skipped. Use `--no-skip-completed` if you need to rerun everything.

You can also run each experiment independently.

### Single-Core L2 Performance

```bash
python3 scripts/experiments/single_core_performance/run_single_core.py --max-jobs 32
```

### L1-Level Experiment

```bash
python3 scripts/experiments/l1_level/run_l1.py --max-jobs 32
```

### Multi-Core Performance

Homogeneous:

```bash
python3 scripts/experiments/multi_core_performance/run_multi_core.py --max-jobs 32
```

Heterogeneous:

```bash
python3 scripts/experiments/multi_core_performance/run_multi_core.py --heterogeneous --max-jobs 32
```

### Multi-Level Prefetching

```bash
python3 scripts/experiments/multi_level_prefetching/run_multi_level_prefetching.py --max-jobs 32
```

### Ablation Study

```bash
python3 scripts/experiments/ablation_experiment/run_ablation.py --max-jobs 32
```

### Parameter Sweep

```bash
python3 scripts/experiments/parameter_experiment/run_parameter_sweep.py --max-jobs 32
```

### System Sensitivity

```bash
python3 scripts/experiments/system_parameter_experiment/run_system_sensitivity.py --max-jobs 32
```

### Storage Sensitivity

```bash
python3 scripts/experiments/storage_sensitivity/run_storage_sensitivity.py --max-jobs 32
```

### Limited-Way L2 Prefetching

```bash
python3 scripts/experiments/limited_way_experiment/run_limited_way_experiment.py --max-jobs 32
```

## Collecting Metrics

After the simulations finish, regenerate the standard CSV files with:

```bash
python3 scripts/results_analysis/collect_all_metrics.py
```

This produces the expected CSV outputs under `scripts/results_analysis/results/`.

If you only need one experiment, use [scripts/results_analysis/collect_metrics.py](scripts/results_analysis/collect_metrics.py) directly with the appropriate `--log-root` and `--output` arguments.

## Plotting

Each experiment directory contains its corresponding plot script. Typical commands:

### Single-Core L2

```bash
python3 scripts/experiments/single_core_performance/plot_single_core_metrics.py
```

### L1-Level

```bash
python3 scripts/experiments/l1_level/plot_l1_level_metrics.py
```

### Multi-Core Scaling

```bash
python3 scripts/experiments/multi_core_performance/plot_multicore_scaling.py
```

### Multi-Level Prefetching

```bash
python3 scripts/experiments/multi_level_prefetching/plot_multi_level_prefetching.py
```

### Ablation

```bash
python3 scripts/experiments/ablation_experiment/plot_ablation.py
```

### Parameter Sweep

```bash
python3 scripts/experiments/parameter_experiment/plot_parameter_sweep.py
```

### System Sensitivity

```bash
python3 scripts/experiments/system_parameter_experiment/plot_l2_system_sensitivity.py
```

### Storage Sensitivity

```bash
python3 scripts/experiments/storage_sensitivity/plot_storage_sensitivity_metrics.py
```

### Limited-Way L2 Prefetching

```bash
python3 scripts/experiments/limited_way_experiment/plot_limited_way_experiment.py --reserved-ways 1
```

Generated figures are written under each experiment's `figures/` directory unless an explicit output path is provided.

## Notes

- Use the same warmup/simulation counts for build, run, collection, and plotting workflows. The default paper configuration is `50M` warmup and `100M` simulation instructions.
- The queue-based runners accept `--max-jobs`, `--poll-seconds`, and retry controls so you can adapt them to your machine.
- The Git tree intentionally excludes traces and generated outputs; those artifacts are regenerated locally.

## License

STEP-specific source code and experiment scripts are released under the
[MIT License](LICENSE). The bundled ChampSim source tree and third-party
prefetcher implementations retain their respective upstream copyright and
license notices; see [ChampSim/LICENSE](ChampSim/LICENSE).
