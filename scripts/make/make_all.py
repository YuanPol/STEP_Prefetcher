#!/usr/bin/env python3

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent

MAKE_SCRIPTS = [
    "make_single_core_l2.py",
    "make_single_core.py",
    "make_multi_core_l2.py",
    "make_single_core_multi_level.py",
    "make_ablation.py",
    "make_parameter_sweep.py",
    "make_single_core_l2_system_sensitivity.py",
    "make_storage_sensitivity.py",
    "make_limited_way_experiment.py",
]


def main() -> int:
    for script_name in MAKE_SCRIPTS:
        subprocess.run([sys.executable, script_name], check=True, cwd=SCRIPT_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
