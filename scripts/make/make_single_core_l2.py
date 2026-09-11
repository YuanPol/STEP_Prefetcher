import os
import json
from make_functions import *
    
def main():
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir + '/../../ChampSim')
    
    print('Making prefetchers single core and l2 level')
    
    for prefetcher in [
        "no",
        "sms",
        "dspatch",
        "spp_ppf",
        "pmp",
        "berti",
        "gaze",
        "step",
        "bingo_streaming_disable_overlap_pht_16x64",
    ]:
        make_1core_l2(prefetcher)
    
    print('Done.')


if __name__ == '__main__':
    main()
