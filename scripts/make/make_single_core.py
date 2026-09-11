import os
from make_functions import *
    
def main():
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir + '/../../ChampSim')
    
    print('Making prefetchers for the paper L1-level experiments')
    
    for prefetcher in [
        "no",
        "gaze_l1_l2_fill",
        "step_l1_l2_fill_disable_second",
        "bingo_streaming_disable_overlap_l1_l2_fill",
    ]:
        make_1core(prefetcher)
    
    print('Done.')


if __name__ == '__main__':
    main()
