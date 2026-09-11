import os
from make_functions import *


def build_step_storage_variants(prefix):
    return [
        "step_small",
        f"{prefix}_ft256_at128_pt2",
        f"{prefix}_ft256_at128_pt4",
        f"{prefix}_ft256_at128_pt8",
        f"{prefix}_ft256_at128_pt16",
        f"{prefix}_ft256_at128_pt32",
        f"{prefix}_ft256_at128_pt64",
        f"{prefix}_ft256_at128_pt128",
        f"{prefix}_ft256_at128_pt256",
    ]


STEP_STORAGE_VARIANTS = build_step_storage_variants("step_disable_second")
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

DEFAULT_PREFETCHERS = [
    *STEP_STORAGE_VARIANTS,
    *GAZE_STORAGE_VARIANTS,
    *VBERTI_STORAGE_VARIANTS,
    *BINGO_STORAGE_VARIANTS,
    *EBINGO_STORAGE_VARIANTS,
    *IPCP_STORAGE_VARIANTS,
]


def make_storage_prefetcher(prefetcher):
    if prefetcher.endswith("_ipcp_l2") and prefetcher.startswith("ipcp_l1_"):
        make_1core_multi_level([prefetcher.removesuffix("_ipcp_l2"), "ipcp_l2"])
        return
    make_1core_l2(prefetcher)


def main():

    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir + '/../../ChampSim')

    print('Making prefetchers for the paper storage sensitivity experiments')

    for prefetcher in DEFAULT_PREFETCHERS:
        make_storage_prefetcher(prefetcher)

    print('Done.')


if __name__ == '__main__':
    main()
