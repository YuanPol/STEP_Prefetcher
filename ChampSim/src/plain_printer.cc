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

#include <iomanip>
#include <iostream>
#include <numeric>
#include <sstream>
#include <utility>
#include <vector>

#include "stats_printer.h"

void champsim::plain_printer::print(O3_CPU::stats_type stats) {
    constexpr std::array<std::pair<std::string_view, std::size_t>, 6> types{
        {std::pair{"BRANCH_DIRECT_JUMP", BRANCH_DIRECT_JUMP}, std::pair{"BRANCH_INDIRECT", BRANCH_INDIRECT}, std::pair{"BRANCH_CONDITIONAL", BRANCH_CONDITIONAL},
         std::pair{"BRANCH_DIRECT_CALL", BRANCH_DIRECT_CALL}, std::pair{"BRANCH_INDIRECT_CALL", BRANCH_INDIRECT_CALL},
         std::pair{"BRANCH_RETURN", BRANCH_RETURN}}};

    auto total_branch = std::ceil(
        std::accumulate(std::begin(types), std::end(types), 0ll, [tbt = stats.total_branch_types](auto acc, auto next) { return acc + tbt[next.second]; }));
    auto total_mispredictions = std::ceil(
        std::accumulate(std::begin(types), std::end(types), 0ll, [btm = stats.branch_type_misses](auto acc, auto next) { return acc + btm[next.second]; }));

    stream << std::endl;
    stream << stats.name << " cumulative IPC: " << std::ceil(stats.instrs()) / std::ceil(stats.cycles()) << " instructions: " << stats.instrs()
           << " cycles: " << stats.cycles() << std::endl;
    stream << stats.name << " Branch Prediction Accuracy: " << (100.0 * std::ceil(total_branch - total_mispredictions)) / total_branch
           << "% MPKI: " << (1000.0 * total_mispredictions) / std::ceil(stats.instrs());
    stream << " Average ROB Occupancy at Mispredict: " << std::ceil(stats.total_rob_occupancy_at_branch_mispredict) / total_mispredictions << std::endl;

    std::vector<double> mpkis;
    std::transform(std::begin(stats.branch_type_misses), std::end(stats.branch_type_misses), std::back_inserter(mpkis),
                   [instrs = stats.instrs()](auto x) { return 1000.0 * std::ceil(x) / std::ceil(instrs); });

    stream << "Branch type MPKI" << std::endl;
    for (auto [str, idx] : types)
        stream << str << ": " << mpkis[idx] << std::endl;
    stream << std::endl;
}

void champsim::plain_printer::print(CACHE::stats_type stats) {
    auto print_access_line = [&](std::size_t cpu, const std::string& label, uint64_t access, uint64_t hit, uint64_t miss) {
        stream << "cpu" << cpu << "->" << stats.name << " ";
        stream << std::left << std::setw(12) << label;
        stream << std::right;
        stream << " ACCESS: " << std::setw(10) << access;
        stream << " HIT: " << std::setw(10) << hit;
        stream << " MISS: " << std::setw(10) << miss << std::endl;
    };

    auto print_prefetch_line = [&](std::size_t cpu, const std::string& label, uint64_t requested, uint64_t issued, uint64_t useful, uint64_t useless,
                                   uint64_t fill, uint64_t late, bool include_fill) {
        stream << "cpu" << cpu << "->" << stats.name << " ";
        if (!label.empty())
            stream << label << " ";
        stream << "PREFETCH REQ: " << std::setw(10) << requested;
        stream << " ISSUED: " << std::setw(10) << issued;
        stream << " USEFUL: " << std::setw(10) << useful;
        stream << " USELESS: " << std::setw(10) << useless;
        if (include_fill) {
            stream << " FILL: " << std::setw(10) << fill;
            stream << " LATE: " << std::setw(10) << late;
        }
        stream << std::endl;
    };

    for (std::size_t cpu = 0; cpu < NUM_CPUS; ++cpu) {
        uint64_t total_hit = 0;
        uint64_t total_miss = 0;

        for (std::size_t type = 0; type < NUM_TYPES; ++type) {
            total_hit += stats.hits.at(type).at(cpu);
            total_miss += stats.misses.at(type).at(cpu);
        }

        print_access_line(cpu, "TOTAL", total_hit + total_miss, total_hit, total_miss);
        print_access_line(cpu, "LOAD", stats.hits.at(LOAD).at(cpu) + stats.misses.at(LOAD).at(cpu), stats.hits.at(LOAD).at(cpu),
                          stats.misses.at(LOAD).at(cpu));
        print_access_line(cpu, "RFO", stats.hits.at(RFO).at(cpu) + stats.misses.at(RFO).at(cpu), stats.hits.at(RFO).at(cpu),
                          stats.misses.at(RFO).at(cpu));
        print_access_line(cpu, "PREFETCH", stats.hits.at(PREFETCH).at(cpu) + stats.misses.at(PREFETCH).at(cpu),
                          stats.hits.at(PREFETCH).at(cpu), stats.misses.at(PREFETCH).at(cpu));
        print_access_line(cpu, "WRITE", stats.hits.at(WRITE).at(cpu) + stats.misses.at(WRITE).at(cpu), stats.hits.at(WRITE).at(cpu),
                          stats.misses.at(WRITE).at(cpu));
        print_access_line(cpu, "TRANSLATION", stats.hits.at(TRANSLATION).at(cpu) + stats.misses.at(TRANSLATION).at(cpu),
                          stats.hits.at(TRANSLATION).at(cpu), stats.misses.at(TRANSLATION).at(cpu));

        print_prefetch_line(cpu, "", stats.pf_requested, stats.pf_issued, stats.pf_useful, stats.pf_useless, stats.pf_fill, stats.pf_late, false);
        stream << "cpu" << cpu << "->" << stats.name << " PREFETCH FILL: " << std::setw(10) << stats.pf_fill << " LATE: " << std::setw(10)
               << stats.pf_late << std::endl;

        print_prefetch_line(cpu, "STRIDE", stats.pf_stride_requested, stats.pf_stride_issued, stats.pf_stride_useful, stats.pf_stride_useless,
                            stats.pf_stride_fill, stats.pf_stride_late, true);
        print_prefetch_line(cpu, "FIRST OFFSET", stats.pf_first_offset_requested, stats.pf_first_offset_issued, stats.pf_first_offset_useful,
                            stats.pf_first_offset_useless, stats.pf_first_offset_fill, stats.pf_first_offset_late, true);
        print_prefetch_line(cpu, "SECOND OFFSET", stats.pf_second_offset_requested, stats.pf_second_offset_issued, stats.pf_second_offset_useful,
                            stats.pf_second_offset_useless, stats.pf_second_offset_fill, stats.pf_second_offset_late, true);
        print_prefetch_line(cpu, "THIRD OFFSET", stats.pf_third_offset_requested, stats.pf_third_offset_issued, stats.pf_third_offset_useful,
                            stats.pf_third_offset_useless, stats.pf_third_offset_fill, stats.pf_third_offset_late, true);
        print_prefetch_line(cpu, "STREAM", stats.pf_stream_requested, stats.pf_stream_issued, stats.pf_stream_useful,
                            stats.pf_stream_useless, stats.pf_stream_fill, stats.pf_stream_late, true);
        stream << "cpu" << cpu << "->" << stats.name << " TRIGGERS TOTAL: " << std::setw(10) << stats.total_trigger << " PHT: " << std::setw(10)
               << stats.pht_trigger << " PC: " << std::setw(10) << stats.pc_trigger << " NN: " << std::setw(10) << 0 << " FT_DROP: "
               << std::setw(10) << stats.ft_drop << std::endl;

        double avg_latency = 0.0;
        if (total_miss > 0)
            avg_latency = static_cast<double>(stats.total_miss_latency) / static_cast<double>(total_miss);

        auto old_flags = stream.flags();
        auto old_precision = stream.precision();
        stream.setf(std::ios::fixed, std::ios::floatfield);
        stream << std::setprecision(1);
        stream << "cpu" << cpu << "->" << stats.name << " AVERAGE MISS LATENCY: " << avg_latency << " cycles" << std::endl;
        stream.flags(old_flags);
        stream.precision(old_precision);
    }
}
void champsim::plain_printer::print(CACHE::NonTranslatingQueues::stats_type stats) {
    stream << "Queue Stats ";
    stream << " PQ_ACCESS: " << std::setw(10) << stats.PQ_ACCESS;
    stream << " PQ_FULL: " << std::setw(10) << stats.PQ_FULL;
    stream << " PQ_TO_CACHE: " << std::setw(10) << stats.PQ_TO_CACHE;
    stream << " PQ_MERGED: " << std::setw(10) << stats.PQ_MERGED << std::endl;
}

void champsim::plain_printer::print(DRAM_CHANNEL::stats_type stats) {
    stream << stats.name << std::endl;
    stream << " RQ ROW_BUFFER_HIT: " << std::setw(10) << stats.RQ_ROW_BUFFER_HIT << std::endl;
    stream << "  ROW_BUFFER_MISS: " << std::setw(10) << stats.RQ_ROW_BUFFER_MISS << std::endl;
    stream << " AVG DBUS CONGESTED CYCLE: ";
    if (stats.dbus_count_congested > 0)
        stream << std::setw(10) << std::ceil(stats.dbus_cycle_congested) / std::ceil(stats.dbus_count_congested);
    else
        stream << "-";
    stream << std::endl;
    stream << " WQ ROW_BUFFER_HIT: " << std::setw(10) << stats.WQ_ROW_BUFFER_HIT << std::endl;
    stream << "  ROW_BUFFER_MISS: " << std::setw(10) << stats.WQ_ROW_BUFFER_MISS;
    stream << "  FULL: " << std::setw(10) << stats.WQ_FULL << std::endl;
    stream << std::endl;
}

void champsim::plain_printer::print(champsim::phase_stats& stats) {
    stream << "=== " << stats.name << " ===" << std::endl;

    int i = 0;
    for (auto tn : stats.trace_names)
        stream << "CPU " << i++ << " runs " << tn << std::endl;

    if (NUM_CPUS > 1) {
        stream << std::endl;
        stream << "Total Simulation Statistics (not including warmup)" << std::endl;

        std::cout << stats.sim_cpu_stats.size() << std::endl;
        for (const auto& stat : stats.sim_cpu_stats)
            print(stat);

        std::cout << stats.sim_cache_stats.size() << std::endl;
        for (const auto& stat : stats.sim_cache_stats)
            print(stat);

        std::cout << stats.sim_cache_queue_stats.size() << std::endl;
        for (const auto& stat : stats.sim_cache_queue_stats)
            print(stat);
    }

    stream << std::endl;
    stream << "Region of Interest Statistics" << std::endl;

    for (const auto& stat : stats.roi_cpu_stats)
        print(stat);

    auto it_cache_stat = stats.roi_cache_stats.cbegin();
    auto it_cache_queue_stat = stats.roi_cache_queue_stats.cbegin();
    for (; it_cache_stat != stats.roi_cache_stats.cend();) {
        print(*it_cache_stat);
        print(*it_cache_queue_stat);
        it_cache_stat++;
        it_cache_queue_stat++;
    }

    stream << std::endl;
    stream << "DRAM Statistics" << std::endl;
    for (const auto& stat : stats.roi_dram_stats)
        print(stat);
}

void champsim::plain_printer::print(std::vector<phase_stats>& stats) {
    for (auto p : stats)
        print(p);
}
