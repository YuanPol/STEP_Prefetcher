import os
import json
from make_functions import *
    
def main():
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir + '/../../ChampSim')
    
    print('Making prefetchers single core and l2 level')
    
    for prefetcher in [
        'step_full_ft256_at128_pt8',
        'step_disable_first_ft256_at128_pt8',
        'step_disable_second_ft256_at128_pt8',
        'step_disable_third_ft256_at128_pt8',
    ]:
        make_1core_l2(prefetcher)
    
    print('Done.')


if __name__ == '__main__':
    main()
