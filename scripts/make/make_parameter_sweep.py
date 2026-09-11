import os
from make_functions import *


def build_step_parameter_sweep(prefix):
    return [
        f'{prefix}_ft32_at128_pt8',
        f'{prefix}_ft64_at128_pt8',
        f'{prefix}_ft128_at128_pt8',
        f'{prefix}_ft256_at128_pt8',
        f'{prefix}_ft512_at128_pt8',
        f'{prefix}_ft1024_at128_pt8',
        f'{prefix}_ft256_at32_pt8',
        f'{prefix}_ft256_at64_pt8',
        f'{prefix}_ft256_at256_pt8',
        f'{prefix}_ft256_at512_pt8',
        f'{prefix}_ft256_at128_pt4',
        f'{prefix}_ft256_at128_pt16',
        f'{prefix}_ft256_at128_pt32',
        f'{prefix}_ft256_at128_pt64',
        f'{prefix}_ft256_at128_pt128',
    ]


def main():

    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir + '/../../ChampSim')

    print('Making prefetchers for the paper parameter sweep')

    for prefetcher in build_step_parameter_sweep('step_disable_second'):
        make_1core_l2(prefetcher)
    
    print('Done.')


if __name__ == '__main__':
    main()
