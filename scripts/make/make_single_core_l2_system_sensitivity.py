import os
from make_functions import *


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir + '/../../ChampSim')

    print('Making prefetchers for the paper system sensitivity experiments')

    for prefetcher in [
        'no',
        'gaze',
        'step',
        'berti',
        'spp_ppf',
        'bingo_streaming_disable_overlap_pht_16x64',
    ]:
        make_1core_l2_system_sensitivity(prefetcher)

    print('Done.')


if __name__ == '__main__':
    main()
