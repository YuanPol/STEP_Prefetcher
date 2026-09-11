import os
from make_functions import *


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir + '/../../ChampSim')

    print('Making prefetchers for the paper multi-core experiments')

    for core in [2, 4, 8]:
        for prefetcher in [
            'no',
            'dspatch',
            'gaze',
            'step',
            'bingo_streaming_disable_overlap_pht_16x64',
        ]:
            make_multicore_l2(core, prefetcher)

    print('Done.')


if __name__ == '__main__':
    main()
