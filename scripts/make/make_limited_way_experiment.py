import argparse
import os

from make_functions import *


DEFAULT_PREFETCHERS = [
    "no",
    "gaze",
    "step",
    "bingo_streaming_disable_overlap_pht_16x64",
]
DEFAULT_RESERVED_WAYS = [1]


def parse_args():
    parser = argparse.ArgumentParser(description="Build binaries for the limited-way single-core experiment.")
    parser.add_argument(
        "--prefetchers",
        nargs="*",
        default=DEFAULT_PREFETCHERS,
        help="Prefetchers to build.",
    )
    parser.add_argument(
        "--reserved-ways",
        type=int,
        nargs="*",
        default=DEFAULT_RESERVED_WAYS,
        help="Number of L2 ways reserved for prefetch fills. Defaults to 1.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    reserved_way_values = list(dict.fromkeys(args.reserved_ways))
    if not reserved_way_values:
        raise ValueError("--reserved-ways must provide at least one value")
    if any(reserved_ways <= 0 for reserved_ways in reserved_way_values):
        raise ValueError("--reserved-ways must all be > 0")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir + '/../../ChampSim')

    print(f"Making limited-way prefetchers (reserved_ways={reserved_way_values})")

    prefetchers = list(dict.fromkeys(args.prefetchers))
    if "no" in prefetchers:
        make_1core_l2("no")

    for reserved_ways in reserved_way_values:
        for prefetcher in prefetchers:
            if prefetcher == "no":
                continue
            make_1core_l2_limited_way(prefetcher, reserved_ways)

    print('Done.')


if __name__ == '__main__':
    main()
