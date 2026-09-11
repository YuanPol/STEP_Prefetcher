import random
import math

workloads_spec06 = [
    ['410.bwaves-1963B.champsimtrace.xz', '410_1963'], ['410.bwaves-2097B.champsimtrace.xz', '410_2097'], 
    ['429.mcf-22B.champsimtrace.xz', '429_22'], ['429.mcf-51B.champsimtrace.xz', '429_51'], ['429.mcf-184B.champsimtrace.xz', '429_184'], ['429.mcf-192B.champsimtrace.xz', '429_192'], 
    ['436.cactusADM-1804B.champsimtrace.xz', '436_1804'], 
    ['437.leslie3d-271B.champsimtrace.xz', '437_271'], ['437.leslie3d-134B.champsimtrace.xz', '437_134'], ['437.leslie3d-149B.champsimtrace.xz', '437_149'], ['437.leslie3d-232B.champsimtrace.xz', '437_232'], ['437.leslie3d-265B.champsimtrace.xz', '437_265'], ['437.leslie3d-273B.champsimtrace.xz', '437_273'],
    ['462.libquantum-714B.champsimtrace.xz', '462_714'], ['462.libquantum-1343B.champsimtrace.xz', '462_1343'], 
    ['471.omnetpp-188B.champsimtrace.xz', '471_188'], 
    ['473.astar-359B.champsimtrace.xz', '473_359'], 
    ['482.sphinx3-234B.champsimtrace.xz', '482_234'], ['482.sphinx3-417B.champsimtrace.xz', '482_417'], ['482.sphinx3-1100B.champsimtrace.xz', '482_1100'], ['482.sphinx3-1297B.champsimtrace.xz', '482_1297'], ['482.sphinx3-1395B.champsimtrace.xz', '482_1395'], ['482.sphinx3-1522B.champsimtrace.xz', '482_1522'],
    ['483.xalancbmk-127B.champsimtrace.xz', '483_127'],
    ['433.milc-127B.champsimtrace.xz', '433_127'], ['433.milc-337B.champsimtrace.xz', '433_337'], 
    ['450.soplex-92B.champsimtrace.xz', '450_92'], ['450.soplex-247B.champsimtrace.xz', '450_247'],
    ['459.GemsFDTD-1211B.champsimtrace.xz', '459_1211'], ['459.GemsFDTD-765B.champsimtrace.xz', '459_765'], ['459.GemsFDTD-1169B.champsimtrace.xz', '459_1169'], ['459.GemsFDTD-1418B.champsimtrace.xz', '459_1418'], ['459.GemsFDTD-1491B.champsimtrace.xz', '459_1491'],
    ['470.lbm-1274B.champsimtrace.xz', '470_1274'],
    ['481.wrf-196B.champsimtrace.xz', '481_196'], ['481.wrf-455B.champsimtrace.xz', '481_455'], ['481.wrf-816B.champsimtrace.xz', '481_816'], ['481.wrf-1254B.champsimtrace.xz', '481_1254'], ['481.wrf-1281B.champsimtrace.xz', '481_1281']
]

workloads_comp = [
    ['433.milc-127B.champsimtrace.xz', '433_127'], ['433.milc-337B.champsimtrace.xz', '433_337'], 
    ['450.soplex-92B.champsimtrace.xz', '450_92'], ['450.soplex-247B.champsimtrace.xz', '450_247'],
    ['459.GemsFDTD-1211B.champsimtrace.xz', '459_1211'], ['459.GemsFDTD-765B.champsimtrace.xz', '459_765'], ['459.GemsFDTD-1169B.champsimtrace.xz', '459_1169'], ['459.GemsFDTD-1418B.champsimtrace.xz', '459_1418'], ['459.GemsFDTD-1491B.champsimtrace.xz', '459_1491'],
    ['470.lbm-1274B.champsimtrace.xz', '470_1274'],
    ['481.wrf-196B.champsimtrace.xz', '481_196'], ['481.wrf-455B.champsimtrace.xz', '481_455'], ['481.wrf-816B.champsimtrace.xz', '481_816'], ['481.wrf-1254B.champsimtrace.xz', '481_1254'], ['481.wrf-1281B.champsimtrace.xz', '481_1281'], 
    ['627.cam4_s-490B.champsimtrace.xz', '627_490'],
]

workloads_spec17 = [
    # 602.gcc_s
    ['602.gcc_s-734B.champsimtrace.xz', '602_734'],
    ['602.gcc_s-1850B.champsimtrace.xz', '602_1850'],
    ['602.gcc_s-2226B.champsimtrace.xz', '602_2226'],

    # 603.bwaves_s
    ['603.bwaves_s-1740B.champsimtrace.xz', '603_1740'],
    ['603.bwaves_s-2609B.champsimtrace.xz', '603_2609'],
    ['603.bwaves_s-2931B.champsimtrace.xz', '603_2931'],

    # 605.mcf_s
    ['605.mcf_s-472B.champsimtrace.xz', '605_472'],
    ['605.mcf_s-484B.champsimtrace.xz', '605_484'],
    ['605.mcf_s-665B.champsimtrace.xz', '605_665'],
    ['605.mcf_s-782B.champsimtrace.xz', '605_782'],
    ['605.mcf_s-994B.champsimtrace.xz', '605_994'],
    ['605.mcf_s-1152B.champsimtrace.xz', '605_1152'],
    ['605.mcf_s-1536B.champsimtrace.xz', '605_1536'],
    ['605.mcf_s-1554B.champsimtrace.xz', '605_1554'],

    # 607.cactuBSSN_s
    ['607.cactuBSSN_s-2421B.champsimtrace.xz', '607_2421'],
    ['607.cactuBSSN_s-3477B.champsimtrace.xz', '607_3477'],
    ['607.cactuBSSN_s-4004B.champsimtrace.xz', '607_4004'],
    ['607.cactuBSSN_s-4248B.champsimtrace.xz', '607_4248'],

    # 620.omnetpp_s
    ['620.omnetpp_s-141B.champsimtrace.xz', '620_141'],
    ['620.omnetpp_s-874B.champsimtrace.xz', '620_874'],

    # 621.wrf_s
    ['621.wrf_s-6673B.champsimtrace.xz', '621_6673'],
    ['621.wrf_s-8065B.champsimtrace.xz', '621_8065'],
    ['621.wrf_s-8100B.champsimtrace.xz', '621_8100'],

    # 623.xalancbmk_s
    ['623.xalancbmk_s-10B.champsimtrace.xz', '623_10'],
    ['623.xalancbmk_s-165B.champsimtrace.xz', '623_165'],
    ['623.xalancbmk_s-202B.champsimtrace.xz', '623_202'],

    # # 625.x264_s
    ['625.x264_s-20B.champsimtrace.xz', '625_20'],

    # 628.pop2_s
    ['628.pop2_s-17B.champsimtrace.xz', '628_17'],

    # 649.fotonik3d_s
    ['649.fotonik3d_s-1176B.champsimtrace.xz', '649_1176'],
    ['649.fotonik3d_s-7084B.champsimtrace.xz', '649_7084'],
    ['649.fotonik3d_s-8225B.champsimtrace.xz', '649_8225'],
    ['649.fotonik3d_s-10881B.champsimtrace.xz', '649_10881'],

    # 654.roms_s
    ['654.roms_s-293B.champsimtrace.xz', '654_293'],
    ['654.roms_s-294B.champsimtrace.xz', '654_294'],
    ['654.roms_s-523B.champsimtrace.xz', '654_523'],
    ['654.roms_s-1007B.champsimtrace.xz', '654_1007'],
    ['654.roms_s-1070B.champsimtrace.xz', '654_1070'],
    ['654.roms_s-1390B.champsimtrace.xz', '654_1390'],

    ['627.cam4_s-490B.champsimtrace.xz', '627_490'],
]

workloads_cloudsuite = [
    ['cassandra_phase0_core0.trace.xz', 'cass_p0_c0'], ['cassandra_phase0_core1.trace.xz', 'cass_p0_c1'], ['cassandra_phase0_core2.trace.xz', 'cass_p0_c2'], ['cassandra_phase0_core3.trace.xz', 'cass_p0_c3'],
    ['cassandra_phase1_core0.trace.xz', 'cass_p1_c0'], ['cassandra_phase1_core1.trace.xz', 'cass_p1_c1'], ['cassandra_phase1_core2.trace.xz', 'cass_p1_c2'], ['cassandra_phase1_core3.trace.xz', 'cass_p1_c3'],
    ['cassandra_phase2_core1.trace.xz', 'cass_p2_c1'], ['cassandra_phase2_core2.trace.xz', 'cass_p2_c2'], ['cassandra_phase2_core3.trace.xz', 'cass_p2_c3'],
    ['cassandra_phase3_core1.trace.xz', 'cass_p3_c1'], ['cassandra_phase3_core3.trace.xz', 'cass_p3_c3'],
    ['cassandra_phase4_core0.trace.xz', 'cass_p4_c0'], ['cassandra_phase4_core2.trace.xz', 'cass_p4_c2'], ['cassandra_phase4_core3.trace.xz', 'cass_p4_c3'],
    ['cassandra_phase5_core0.trace.xz', 'cass_p5_c0'], ['cassandra_phase5_core1.trace.xz', 'cass_p5_c1'], ['cassandra_phase5_core2.trace.xz', 'cass_p5_c2'], ['cassandra_phase5_core3.trace.xz', 'cass_p5_c3'],
    ['nutch_phase0_core0.trace.xz', 'nutch_p0_c0'], ['nutch_phase0_core1.trace.xz', 'nutch_p0_c1'], ['nutch_phase0_core2.trace.xz', 'nutch_p0_c2'], ['nutch_phase0_core3.trace.xz', 'nutch_p0_c3'],
    ['nutch_phase1_core0.trace.xz', 'nutch_p1_c0'], ['nutch_phase1_core2.trace.xz', 'nutch_p1_c2'], ['nutch_phase1_core3.trace.xz', 'nutch_p1_c3'],
    ['nutch_phase3_core0.trace.xz', 'nutch_p3_c0'], ['nutch_phase3_core1.trace.xz', 'nutch_p3_c1'], ['nutch_phase3_core2.trace.xz', 'nutch_p3_c2'], ['nutch_phase3_core3.trace.xz', 'nutch_p3_c3'],
    ['nutch_phase4_core0.trace.xz', 'nutch_p4_c0'], ['nutch_phase4_core1.trace.xz', 'nutch_p4_c1'], ['nutch_phase4_core2.trace.xz', 'nutch_p4_c2'], ['nutch_phase4_core3.trace.xz', 'nutch_p4_c3'],
    ['streaming_phase0_core1.trace.xz', 'stream_p0_c1'], 
    ['streaming_phase1_core0.trace.xz', 'stream_p1_c0'], ['streaming_phase1_core1.trace.xz', 'stream_p1_c1'], ['streaming_phase1_core3.trace.xz', 'stream_p1_c3'], 
    ['streaming_phase2_core0.trace.xz', 'stream_p2_c0'], ['streaming_phase2_core1.trace.xz', 'stream_p2_c1'], ['streaming_phase2_core2.trace.xz', 'stream_p2_c2'], ['streaming_phase2_core3.trace.xz', 'stream_p2_c3'], 
    ['streaming_phase3_core0.trace.xz', 'stream_p3_c0'], ['streaming_phase3_core1.trace.xz', 'stream_p3_c1'], ['streaming_phase3_core3.trace.xz', 'stream_p3_c3'], 
    ['streaming_phase4_core0.trace.xz', 'stream_p4_c0'], ['streaming_phase4_core1.trace.xz', 'stream_p4_c1'], ['streaming_phase4_core3.trace.xz', 'stream_p4_c3'], 
    ['streaming_phase5_core0.trace.xz', 'stream_p5_c0'], ['streaming_phase5_core1.trace.xz', 'stream_p5_c1'],
    ['cloud9_phase5_core2.trace.xz', 'cloud_p5_c2']
]


_spec_trace_map = {entry[1]: entry[0] for entry in (workloads_spec06 + workloads_spec17)}

for workload in workloads_spec06:
    workload.append(False)
for workload in workloads_spec17:
    workload.append(False)
for workload in workloads_cloudsuite:
    workload.append(True)

workloads_spec = workloads_spec06 + workloads_spec17
workloads_all = workloads_spec + workloads_cloudsuite


HETEROGENEOUS_RANDOM_SEED = 20260220
HETEROGENEOUS_MIXES_PER_CORE = 50


def _generate_random_heterogeneous_mixes(workload_pool, num_cores, num_groups, seed):
    """
    Build deterministic random heterogeneous mixes.

    Each mix has `num_cores` distinct workloads and keeps a uniform trace-mode
    flag (all entries have the same compressed/context-switch marker). This is
    required because the simulator takes one global `-c` option per run.

    Using a fixed seed guarantees reproducibility across runs.
    """
    if num_cores <= 0:
        raise ValueError("num_cores must be positive.")
    if num_groups <= 0:
        raise ValueError("num_groups must be positive.")
    if num_cores > len(workload_pool):
        raise ValueError("num_cores cannot exceed workload pool size.")

    by_mode = {
        False: [entry for entry in workload_pool if not entry[2]],
        True: [entry for entry in workload_pool if entry[2]],
    }
    for mode, pool in by_mode.items():
        if len(pool) < num_cores:
            raise ValueError(f"Not enough workloads for mode={mode} and num_cores={num_cores}.")

    def sample_unique(pool, required, rng_local):
        mixes = []
        seen = set()
        max_attempts = max(required * 500, 5000)
        attempts = 0

        while len(mixes) < required:
            selection = rng_local.sample(pool, num_cores)
            key = tuple(entry[1] for entry in selection)
            if key in seen:
                attempts += 1
                if attempts > max_attempts:
                    raise RuntimeError(
                        f"Unable to build {required} unique mixes for {num_cores} cores from a single mode."
                    )
                continue

            mixes.append([[entry[0], entry[1], entry[2]] for entry in selection])
            seen.add(key)
        return mixes

    rng = random.Random(seed)
    true_count = num_groups // 2
    false_count = num_groups - true_count

    mixes = []
    mixes.extend(sample_unique(by_mode[False], false_count, rng))
    mixes.extend(sample_unique(by_mode[True], true_count, rng))
    rng.shuffle(mixes)
    return mixes


# Use a fixed number of mixes per core count to keep statistical strength
# balanced across 2/4/8-core heterogeneous evaluations.
workloads_all_2core_heterogeneous = _generate_random_heterogeneous_mixes(
    workloads_all,
    num_cores=2,
    num_groups=HETEROGENEOUS_MIXES_PER_CORE,
    seed=HETEROGENEOUS_RANDOM_SEED,
)
workloads_all_4core_heterogeneous = _generate_random_heterogeneous_mixes(
    workloads_all,
    num_cores=4,
    num_groups=HETEROGENEOUS_MIXES_PER_CORE,
    seed=HETEROGENEOUS_RANDOM_SEED,
)
workloads_all_8core_heterogeneous = _generate_random_heterogeneous_mixes(
    workloads_all,
    num_cores=8,
    num_groups=HETEROGENEOUS_MIXES_PER_CORE,
    seed=HETEROGENEOUS_RANDOM_SEED,
)


workloads_name_map = {
    '410_1963': 'bwaves-1963',  '410_2097': 'bwaves-2097',  '429_22': 'mcf-22',  '429_51': 'mcf-51',  '429_184': 'mcf-184',  
    '429_192': 'mcf-192',  '433_127': 'milc-127',  '433_337': 'milc-337',  '437_134': 'leslie3d-134',  '437_149': 'leslie3d-149',  
    '437_232': 'leslie3d-232',  '437_265': 'leslie3d-265',  '437_273': 'leslie3d-273',  '450_247': 'soplex-247',  '459_765': 'GemsFDTD-765',  
    '459_1169': 'GemsFDTD-1169',  '459_1418': 'GemsFDTD-1418',  '459_1491': 'GemsFDTD-1491',  '462_714': 'libquantum-714',  
    '462_1343': 'libquantum-1343',  '470_1274': 'lbm-1274',  '471_188': 'omnetpp-188',  '481_196': 'wrf-196',  
    '481_455': 'wrf-455',  '481_816': 'wrf-816',  '481_1281': 'wrf-1281',  '482_234': 'sphinx3-234',  
    '482_417': 'sphinx3-417',  '482_1100': 'sphinx3-1100',  '482_1297': 'sphinx3-1297',  '482_1395': 'sphinx3-1395', 
    '482_1522': 'sphinx3-1522',  '483_127': 'xalancbmk-127',  '436_1804': 'cactusADM-1804',  '437_271': 'leslie3d-271',  
    '450_92': 'soplex-92',  '459_1211': 'GemsFDTD-1211',  '473_359': 'astar-359',  '481_1254': 'wrf-1254',  
    '602_734': 'gcc_s-734',  '602_1850': 'gcc_s-1850',  '602_2226': 'gcc_s-2226',  '603_1740': 'bwaves_s-1740',  
    '603_2609': 'bwaves_s-2609',  '603_2931': 'bwaves_s-2931',  '605_484': 'mcf_s-484',  '605_665': 'mcf_s-665',  
    '605_782': 'mcf_s-782',  '605_472': 'mcf_s-472',  '605_994': 'mcf_s-994',  '605_1536': 'mcf_s-1536',  
    '605_1554': 'mcf_s-1554',  '605_1644': 'mcf_s-1644',  '607_2421': 'cactuBSSN_s-2421',  '607_3477': 'cactuBSSN_s-3477',  
    '607_4004': 'cactuBSSN_s-4004',  '619_2676': 'lbm_s-2676',  '619_2677': 'lbm_s-2677',  '619_3766': 'lbm_s-3766',  
    '619_4268': 'lbm_s-4268',  '620_141': 'omnetpp_s-141',  '620_874': 'omnetpp_s-874',  '621_6673': 'wrf_s-6673',  
    '621_8065': 'wrf_s-8065',  '623_10': 'xalancbmk_s-10',  '623_202': 'xalancbmk_s-202',  '627_490': 'cam4_s-490',  
    '628_17': 'pop2_s-17',  '649_1176': 'fotonik3d_s-1176',  '649_7084': 'fotonik3d_s-7084',  
    '649_8225': 'fotonik3d_s-8225',  '649_10881': 'fotonik3d_s-10881',  '654_293': 'roms_s-293',  '654_294': 'roms_s-294',  
    '654_523': 'roms_s-523',  '654_1007': 'roms_s-1007',  '654_1070': 'roms_s-1070',  '654_1390': 'roms_s-1390',  
    'cass_p0_c0': 'cassandra-p0c0',  
    'cass_p0_c1': 'cassandra-p0c1',  'cass_p0_c2': 'cassandra-p0c2',  'cass_p0_c3': 'cassandra-p0c3',  
    'cass_p1_c0': 'cassandra-p1c0',  'cass_p1_c1': 'cassandra-p1c1',  'cass_p1_c2': 'cassandra-p1c2',  
    'cass_p1_c3': 'cassandra-p1c3',  'cass_p2_c1': 'cassandra-p2c1',  'cass_p2_c2': 'cassandra-p2c2',  
    'cass_p2_c3': 'cassandra-p2c3',  'cass_p3_c1': 'cassandra-p3c1',  'cass_p3_c3': 'cassandra-p3c3',  
    'cass_p4_c0': 'cassandra-p4c0',  'cass_p4_c2': 'cassandra-p4c2',  'cass_p4_c3': 'cassandra-p4c3',  
    'cass_p5_c0': 'cassandra-p5c0',  'cass_p5_c1': 'cassandra-p5c1',  'cass_p5_c2': 'cassandra-p5c2',  
    'cass_p5_c3': 'cassandra-p5c3',  'nutch_p0_c0': 'nutch-p0c0',  'nutch_p0_c1': 'nutch-p0c1',  
    'nutch_p0_c2': 'nutch-p0c2',  'nutch_p0_c3': 'nutch-p0c3',  'nutch_p1_c0': 'nutch-p1c0',  'nutch_p1_c2': 'nutch-p1c2',  
    'nutch_p1_c3': 'nutch-p1c3',  'nutch_p3_c0': 'nutch-p3c0',  'nutch_p3_c1': 'nutch-p3c1',  'nutch_p3_c2': 'nutch-p3c2',  
    'nutch_p3_c3': 'nutch-p3c3',  'nutch_p4_c0': 'nutch-p4c0',  'nutch_p4_c1': 'nutch-p4c1',  'nutch_p4_c2': 'nutch-p4c2',  
    'nutch_p4_c3': 'nutch-p4c3',  'stream_p0_c1': 'stream-p0c1',  'stream_p1_c0': 'stream-p1c0',  
    'stream_p1_c1': 'stream-p1c1',  'stream_p1_c3': 'stream-p1c3',  'stream_p2_c0': 'stream-p2c0',  
    'stream_p2_c1': 'stream-p2c1',  'stream_p2_c2': 'stream-p2c2',  'stream_p2_c3': 'stream-p2c3',  
    'stream_p3_c0': 'stream-p3c0',  'stream_p3_c1': 'stream-p3c1',  'stream_p3_c3': 'stream-p3c3',  
    'stream_p4_c0': 'stream-p4c0',  'stream_p4_c1': 'stream-p4c1',  'stream_p4_c3': 'stream-p4c3',  
    'stream_p5_c0': 'stream-p5c0',  'stream_p5_c1': 'stream-p5c1',  'cloud_p5_c2': 'cloud9-p5c2',
    'spec17': 'spec17',  'all':'all',
}
