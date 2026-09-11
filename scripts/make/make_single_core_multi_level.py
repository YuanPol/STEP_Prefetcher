import os

from make_functions import *
    
def main():
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir + '/../../ChampSim')
    
    print('Making prefetchers used to generate the results of fig. 13')
    
    for prefetcher_l1 in [
        'gaze_l1_l2_fill',
        'step_l1_l2_fill_disable_second',
        'bingo_streaming_disable_overlap_l1_l2_fill',
        'berti',
    ]:
        for prefetcher_l2 in [
            'gaze',
            'step',
            'bingo_streaming_disable_overlap_pht_16x64',
            'berti',
        ]:
            if prefetcher_l1 == 'berti' and prefetcher_l2 == 'berti':
                continue
            make_1core_multi_level([prefetcher_l1, prefetcher_l2])
    make_1core_multi_level(['ipcp_l1', 'ipcp_l2'])
            
    # for prefetcher_l1 in ['ip_stride']:
    #     for prefetcher_l2 in ['berti', 'bingo', 'pmp', 'sms', 'dspatch', 'gaze']:
    #         make_1core_multi_level([prefetcher_l1, prefetcher_l2])
    
    print('Done.')


if __name__ == '__main__':
    main()
