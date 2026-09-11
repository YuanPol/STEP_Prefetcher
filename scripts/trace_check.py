import os
from workloads import *

trace_dir = '../traces'

all_exist, main_exist = True, True

for workloads, benchmark_name in [(workloads_spec06, 'SPEC06'), (workloads_spec17, 'SPEC17'), (workloads_cloudsuite, 'CloudSuite')]:
    for workload in workloads:
        trace = f'{trace_dir}/{workload[0]}'
        if not os.path.exists(trace):
            all_exist = False
            print(f'{benchmark_name} {trace} does not exist!')
    
if all_exist:
    print('All traces are prepared')