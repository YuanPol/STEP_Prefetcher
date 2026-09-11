/*
 *    Copyright 2023 The ChampSim Contributors
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "champsim.h"

#include <algorithm>
#include <chrono>
#include <numeric>
#include <vector>

#include "environment.h"
#include "ooo_cpu.h"
#include "operable.h"
#include "phase_info.h"
#include "tracereader.h"
#include "stats_printer.h"

auto start_time = std::chrono::steady_clock::now();

std::tuple<uint64_t, uint64_t, uint64_t> elapsed_time() {
    auto diff = std::chrono::steady_clock::now() - start_time;
    auto elapsed_hour = std::chrono::duration_cast<std::chrono::hours>(diff);
    auto elapsed_minute = std::chrono::duration_cast<std::chrono::minutes>(diff) - elapsed_hour;
    auto elapsed_second = std::chrono::duration_cast<std::chrono::seconds>(diff) - elapsed_hour - elapsed_minute;
    return {elapsed_hour.count(), elapsed_minute.count(), elapsed_second.count()};
}

namespace champsim {
phase_stats do_phase(phase_info phase, environment& env, std::vector<tracereader>& traces) {
    auto [phase_name, is_warmup, length, trace_index, trace_names] = phase;
    auto operables = env.operable_view();

    // Initialize phase
    for (champsim::operable& op : operables) {
        op.warmup = is_warmup;
        op.begin_phase();
    }

    static const uint64_t PRINT_INTERVAL = 1000000; // 1millon instructions
    uint64_t next_print_instrs = PRINT_INTERVAL;
    uint64_t last_heartbeat_cycle = 0;
    uint64_t last_heartbeat_instr = 0;

    // Perform phase
    std::vector<bool> phase_complete(std::size(env.cpu_view()), false);
    while (!std::accumulate(std::begin(phase_complete), std::end(phase_complete), true, std::logical_and{})) {
        // Operate
        uint64_t current_cycle = std::numeric_limits<uint64_t>::max();
        for (champsim::operable& op : operables) {
            try {
                op._operate();
            } catch (champsim::deadlock& dl) {
                for (champsim::operable& c : operables) {
                    c.print_deadlock();
                    std::cout << std::endl;
                }

                abort();
            }

            // DSPatch
            auto cpus = env.cpu_view();
            auto& dram_controller = env.dram_view();
            if (current_cycle != cpus[0].get().current_cycle) { // only broadcast once per cycle
                current_cycle = cpus[0].get().current_cycle;
                int DRAM_DBUS_RETURN_TIME = (BLOCK_SIZE / DRAM_CHANNEL_WIDTH) * (1.0 * (dram_controller.CLOCK_SCALE + 1)); // freq_scale
                int DRAM_DBUS_MAX_CAS = DRAM_CHANNELS * (measure_dram_bw_epoch / DRAM_DBUS_RETURN_TIME);
                if (current_cycle >= dram_controller.next_bw_measure_cycle) {
                    uint64_t this_epoch_enqueue_count = dram_controller.rq_enqueue_count - dram_controller.last_enqueue_count;
                    dram_controller.epoch_enqueue_count = (dram_controller.epoch_enqueue_count / 2) + this_epoch_enqueue_count;
                    uint32_t quartile = ((float)100 * dram_controller.epoch_enqueue_count) / DRAM_DBUS_MAX_CAS;
                    if (quartile <= 20)
                        dram_controller.bw = 0;
                    else if (quartile <= 40)
                        dram_controller.bw = 1;
                    else if (quartile <= 60)
                        dram_controller.bw = 2;
                    else if (quartile <= 80)
                        dram_controller.bw = 3;
                    else
                        dram_controller.bw = 4;

                    dram_controller.last_enqueue_count = dram_controller.rq_enqueue_count;
                    dram_controller.next_bw_measure_cycle = current_cycle + measure_dram_bw_epoch;
                    dram_controller.total_bw_epochs++;
                    dram_controller.bw_level_hist[dram_controller.bw]++;
                    /*  'lower_level' is now queues, not cache.
                    For simplicity, we directly update each cache instead of broadcasting.
                    Its the same. 
                    Original broadcast: llc -> l2c -> l1d && l1i 
                    Ours: for cache in caches, update cache.bw */
                    auto caches = env.cache_view();
                    for (auto cache : caches)
                        cache.get().bw = dram_controller.bw;

                    /* below seems to be part of Hermes, not DSPatch */
                }
            }
            
            //NAPA
            uint64_t retired_instrs = cpus[0].get().sim_instr();
            if (retired_instrs >= next_print_instrs) {
                std::cout << "\n=== [" << phase_name << "] Intermediate Cache Stats at "
                          << retired_instrs << " instructions ===\n";
                auto caches = env.cache_view();
                champsim::plain_printer printer(std::cout);
                for (auto cache_ref : caches) {
                    const auto& cache_name = cache_ref.get().NAME;
                    bool is_l2 = cache_name.find("L2C") != std::string::npos;
                    bool is_l1d = cache_name.find("L1D") != std::string::npos;
                    if (is_l2 || is_l1d)
                        printer.print(cache_ref.get().sim_stats);
                }

                for (O3_CPU& cpu : cpus) {
                    // cache_ref.get() 是 CACHE 对象
                    // std::cout << cache_ref.get().NAME << std::endl;
                    auto heartbeat_instr{std::ceil(cpu.num_retired - last_heartbeat_instr)};
                    auto heartbeat_cycle{std::ceil(cpu.current_cycle - last_heartbeat_cycle)};
                    std::cout << "Heartbeat CPU " << cpu.cpu << " instructions: " << cpu.num_retired << " cycles: " << cpu.current_cycle;
                    std::cout << " heartbeat IPC: " << heartbeat_instr / heartbeat_cycle;
                    last_heartbeat_cycle = cpu.current_cycle;
                    last_heartbeat_instr = cpu.num_retired;
                }

                std::cout << "================================================\n\n";
                next_print_instrs += PRINT_INTERVAL;
            }

        }
        std::sort(std::begin(operables), std::end(operables), champsim::by_next_operate());

        // Read from trace
        for (O3_CPU& cpu : env.cpu_view())
            std::generate_n(std::back_inserter(cpu.input_queue), cpu.IN_QUEUE_SIZE - std::size(cpu.input_queue), std::ref(traces.at(trace_index.at(cpu.cpu))));

        // Check for phase finish
        auto [elapsed_hour, elapsed_minute, elapsed_second] = elapsed_time();
        for (O3_CPU& cpu : env.cpu_view()) {
            // Phase complete
            if (!phase_complete[cpu.cpu] && (cpu.sim_instr() >= length)) {
                phase_complete[cpu.cpu] = true;
                for (champsim::operable& op : operables)
                    op.end_phase(cpu.cpu);

                std::cout << phase_name << " finished CPU " << cpu.cpu;
                std::cout << " instructions: " << cpu.sim_instr() << " cycles: " << cpu.sim_cycle()
                          << " cumulative IPC: " << std::ceil(cpu.sim_instr()) / std::ceil(cpu.sim_cycle());
                std::cout << " (Simulation time: " << elapsed_hour << " hr " << elapsed_minute << " min " << elapsed_second << " sec) " << std::endl;
            }
        }
    }

    auto [elapsed_hour, elapsed_minute, elapsed_second] = elapsed_time();
    for (O3_CPU& cpu : env.cpu_view()) {
        std::cout << std::endl;
        std::cout << phase_name << " complete CPU " << cpu.cpu << " instructions: " << cpu.sim_instr() << " cycles: " << cpu.sim_cycle();
        std::cout << " (Simulation time: " << elapsed_hour << " hr " << elapsed_minute << " min " << elapsed_second << " sec) " << std::endl;
        std::cout << std::endl;
    }

    phase_stats stats;
    stats.name = phase.name;

    for (std::size_t i = 0; i < std::size(trace_index); ++i)
        stats.trace_names.push_back(trace_names.at(trace_index.at(i)));

    auto cpus = env.cpu_view();
    std::transform(std::begin(cpus), std::end(cpus), std::back_inserter(stats.sim_cpu_stats), [](const O3_CPU& cpu) { return cpu.sim_stats; });
    std::transform(std::begin(cpus), std::end(cpus), std::back_inserter(stats.roi_cpu_stats), [](const O3_CPU& cpu) { return cpu.roi_stats; });

    auto caches = env.cache_view();
    std::transform(std::begin(caches), std::end(caches), std::back_inserter(stats.sim_cache_stats), [](const CACHE& cache) { return cache.sim_stats; });
    std::transform(std::begin(caches), std::end(caches), std::back_inserter(stats.roi_cache_stats), [](const CACHE& cache) { return cache.roi_stats; });

    std::transform(std::begin(caches), std::end(caches), std::back_inserter(stats.sim_cache_queue_stats), [](const CACHE& cache) { return cache.queues.sim_stats; });
    std::transform(std::begin(caches), std::end(caches), std::back_inserter(stats.roi_cache_queue_stats), [](const CACHE& cache) { return cache.queues.roi_stats; });

    auto dram = env.dram_view();
    std::transform(std::begin(dram.channels), std::end(dram.channels), std::back_inserter(stats.sim_dram_stats),
                   [](const DRAM_CHANNEL& chan) { return chan.sim_stats; });
    std::transform(std::begin(dram.channels), std::end(dram.channels), std::back_inserter(stats.roi_dram_stats),
                   [](const DRAM_CHANNEL& chan) { return chan.roi_stats; });

    return stats;
}

// simulation entry point
std::vector<phase_stats> main(environment& env, std::vector<phase_info>& phases, std::vector<tracereader>& traces) {
    for (champsim::operable& op : env.operable_view())
        op.initialize();

    std::vector<phase_stats> results;
    for (auto phase : phases) {
        auto stats = do_phase(phase, env, traces);
        if (!phase.is_warmup)
            results.push_back(stats);
    }

    return results;
}
} // namespace champsim
