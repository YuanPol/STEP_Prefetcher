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
#include <utility>

#include "stats_printer.h"

void champsim::json_printer::print(O3_CPU::stats_type stats) {
    constexpr std::array<std::pair<std::string_view, std::size_t>, 6> types{
        {std::pair{"BRANCH_DIRECT_JUMP", BRANCH_DIRECT_JUMP}, std::pair{"BRANCH_INDIRECT", BRANCH_INDIRECT}, std::pair{"BRANCH_CONDITIONAL", BRANCH_CONDITIONAL},
         std::pair{"BRANCH_DIRECT_CALL", BRANCH_DIRECT_CALL}, std::pair{"BRANCH_INDIRECT_CALL", BRANCH_INDIRECT_CALL},
         std::pair{"BRANCH_RETURN", BRANCH_RETURN}}};

    auto total_mispredictions = std::ceil(
        std::accumulate(std::begin(types), std::end(types), 0ll, [btm = stats.branch_type_misses](auto acc, auto next) { return acc + btm[next.second]; }));

    stream << indent() << "{" << std::endl;
    ++indent_level;
    stream << indent() << "\"instructions\": " << stats.instrs() << "," << std::endl;
    stream << indent() << "\"cycles\": " << stats.cycles() << "," << std::endl;
    stream << indent() << "\"Avg ROB occupancy at mispredict\": " << std::ceil(stats.total_rob_occupancy_at_branch_mispredict) / std::ceil(total_mispredictions)
           << ", " << std::endl;

    stream << indent() << "\"mispredict\": {" << std::endl;
    ++indent_level;
    for (std::size_t i = 0; i < std::size(types); ++i) {
        if (i != 0)
            stream << "," << std::endl;
        stream << indent() << "\"" << types[i].first << "\": " << stats.branch_type_misses[types[i].second];
    }
    stream << std::endl;
    --indent_level;
    stream << indent() << "}" << std::endl;
    --indent_level;
    stream << indent() << "}";
}

void champsim::json_printer::print(CACHE::stats_type cache_stats) {
}

void champsim::json_printer::print(CACHE::stats_type cache_stats, CACHE::NonTranslatingQueues::stats_type cache_queue_stats) {
    constexpr std::array<std::pair<std::string_view, std::size_t>, 5> types{
        {std::pair{"LOAD", LOAD}, std::pair{"RFO", RFO}, std::pair{"PREFETCH", PREFETCH}, std::pair{"WRITE", WRITE}, std::pair{"TRANSLATION", TRANSLATION}}};

    stream << indent() << "\"" << cache_stats.name << "\": {" << std::endl;
    ++indent_level;
    if (cache_stats.name == "LLC") {
        for (const auto& type : types) {
            stream << indent() << "\"" << type.first << "\": {" << std::endl;
            ++indent_level;

            stream << indent() << "\"hit\": [";
            for (std::size_t i = 0; i < std::size(cache_stats.hits[type.second]); ++i) {
                if (i != 0)
                    stream << ", ";
                stream << cache_stats.hits[type.second][i];
            }
            stream << "]," << std::endl;

            stream << indent() << "\"miss\": [";
            for (std::size_t i = 0; i < std::size(cache_stats.misses[type.second]); ++i) {
                if (i != 0)
                    stream << ", ";
                stream << cache_stats.misses[type.second][i];
            }
            stream << "]" << std::endl;

            --indent_level;
            stream << indent() << "}," << std::endl;
        }
    } else {
        for (const auto& type : types) {
            uint64_t HIT = 0, MISS = 0;
            stream << indent() << "\"" << type.first << "\": {" << std::endl;
            ++indent_level;

            stream << indent() << "\"hit\":";
            for (std::size_t i = 0; i < std::size(cache_stats.hits[type.second]); ++i) {
                HIT += cache_stats.hits[type.second][i];
            }
            stream << HIT << "," << std::endl;

            stream << indent() << "\"miss\":";
            for (std::size_t i = 0; i < std::size(cache_stats.misses[type.second]); ++i) {
                MISS += cache_stats.misses[type.second][i];
            }
            stream << MISS << std::endl;

            --indent_level;
            stream << indent() << "}," << std::endl;
        }
    }

    stream << indent() << "\"mshr full\": " << cache_stats.mshr_full << "," << std::endl;
    stream << indent() << "\"prefetch requested\": " << cache_stats.pf_requested << "," << std::endl;
    stream << indent() << "\"prefetch issued\": " << cache_stats.pf_issued << "," << std::endl;
    stream << indent() << "\"prefetch filled\": " << cache_stats.pf_fill << "," << std::endl;
    stream << indent() << "\"prefetch useful\": " << cache_stats.pf_useful << "," << std::endl;
    stream << indent() << "\"prefetch useless\": " << cache_stats.pf_useless << "," << std::endl;
    stream << indent() << "\"prefetch late\": " << cache_stats.pf_late << "," << std::endl;

    auto print_prefetch_mechanism = [this](const char* label, uint64_t requested, uint64_t issued, uint64_t filled,
                                           uint64_t useful, uint64_t useless, uint64_t late) {
        stream << indent() << "\"" << label << " prefetch requested\": " << requested << "," << std::endl;
        stream << indent() << "\"" << label << " prefetch issued\": " << issued << "," << std::endl;
        stream << indent() << "\"" << label << " prefetch filled\": " << filled << "," << std::endl;
        stream << indent() << "\"" << label << " prefetch useful\": " << useful << "," << std::endl;
        stream << indent() << "\"" << label << " prefetch useless\": " << useless << "," << std::endl;
        stream << indent() << "\"" << label << " prefetch late\": " << late << "," << std::endl;
    };
    print_prefetch_mechanism("stride", cache_stats.pf_stride_requested, cache_stats.pf_stride_issued, cache_stats.pf_stride_fill,
                             cache_stats.pf_stride_useful, cache_stats.pf_stride_useless, cache_stats.pf_stride_late);
    print_prefetch_mechanism("first offset", cache_stats.pf_first_offset_requested, cache_stats.pf_first_offset_issued,
                             cache_stats.pf_first_offset_fill, cache_stats.pf_first_offset_useful,
                             cache_stats.pf_first_offset_useless, cache_stats.pf_first_offset_late);
    print_prefetch_mechanism("second offset", cache_stats.pf_second_offset_requested, cache_stats.pf_second_offset_issued,
                             cache_stats.pf_second_offset_fill, cache_stats.pf_second_offset_useful,
                             cache_stats.pf_second_offset_useless, cache_stats.pf_second_offset_late);
    print_prefetch_mechanism("third offset", cache_stats.pf_third_offset_requested, cache_stats.pf_third_offset_issued,
                             cache_stats.pf_third_offset_fill, cache_stats.pf_third_offset_useful,
                             cache_stats.pf_third_offset_useless, cache_stats.pf_third_offset_late);
    print_prefetch_mechanism("stream", cache_stats.pf_stream_requested, cache_stats.pf_stream_issued, cache_stats.pf_stream_fill,
                             cache_stats.pf_stream_useful, cache_stats.pf_stream_useless, cache_stats.pf_stream_late);
    stream << indent() << "\"pf_useful_at_l2_from_l1\": " << std::setw(10) << cache_stats.pf_useful_at_l2_from_l1 << "," << std::endl;
    stream << indent() << "\"pf_late_at_l2_from_l1\": " << std::setw(10) << cache_stats.pf_late_at_l2_from_l1 << "," << std::endl;
    stream << indent() << "\"pf_useless_at_l2_from_l1\": " << std::setw(10) << cache_stats.pf_useless_at_l2_from_l1 << "," << std::endl;
    stream << indent() << "\"pf_at_l2_to_l1\": " << std::setw(10) << cache_stats.l2_pf_to_l1 << "," << std::endl;
    stream << indent() << "\"pf_fill_this_level\": " << std::setw(10) << cache_stats.pf_fill_this_level << "," << std::endl;

    double TOTAL_MISS = 0;
    for (const auto& type : types)
        TOTAL_MISS += std::accumulate(std::begin(cache_stats.misses.at(type.second)), std::end(cache_stats.misses.at(type.second)), TOTAL_MISS);
    if (TOTAL_MISS > 0)
        stream << indent() << "\"miss latency\": " << (std::ceil(cache_stats.total_miss_latency)) / TOTAL_MISS << "," << std::endl;
    else
        stream << indent() << "\"miss latency\": null," << std::endl;

    stream << indent() << "\"cache queues\": {" << std::endl;
    ++indent_level;
    stream << indent() << "\"PQ_ACCESS\": " << cache_queue_stats.PQ_ACCESS << "," << std::endl;
    stream << indent() << "\"PQ_FULL\": " << cache_queue_stats.PQ_FULL << "," << std::endl;
    stream << indent() << "\"PQ_TO_CACHE\": " << cache_queue_stats.PQ_TO_CACHE << "," << std::endl;
    stream << indent() << "\"PQ_MERGED\": " << cache_queue_stats.PQ_MERGED << "," << std::endl;
    stream << indent() << "\"RQ_ACCESS\": " << cache_queue_stats.RQ_ACCESS << "," << std::endl;
    stream << indent() << "\"RQ_MERGED\": " << cache_queue_stats.RQ_MERGED << "," << std::endl;
    stream << indent() << "\"RQ_FULL\": " << cache_queue_stats.RQ_FULL << "," << std::endl;
    stream << indent() << "\"WQ_ACCESS\": " << cache_queue_stats.WQ_ACCESS << "," << std::endl;
    stream << indent() << "\"WQ_MERGED\": " << cache_queue_stats.WQ_MERGED << "," << std::endl;
    stream << indent() << "\"WQ_FULL\": " << cache_queue_stats.WQ_FULL << std::endl;
    --indent_level;
    stream << indent() << "}" << std::endl;

    --indent_level;
    stream << indent() << "}";
}

void champsim::json_printer::print(CACHE::NonTranslatingQueues::stats_type stats) {
    stream << indent() << "{" << std::endl;
    ++indent_level;
    stream << indent() << "\"PQ_ACCESS\": " << stats.PQ_ACCESS << "," << std::endl;
    stream << indent() << "\"PQ_FULL\": " << stats.PQ_FULL << "," << std::endl;
    stream << indent() << "\"PQ_TO_CACHE\": " << stats.PQ_TO_CACHE << "," << std::endl;
    stream << indent() << "\"PQ_MERGED\": " << stats.PQ_MERGED << "," << std::endl;
    stream << indent() << "\"RQ_ACCESS\": " << stats.RQ_ACCESS << "," << std::endl;
    stream << indent() << "\"RQ_MERGED\": " << stats.RQ_MERGED << "," << std::endl;
    stream << indent() << "\"RQ_FULL\": " << stats.RQ_FULL << "," << std::endl;
    stream << indent() << "\"WQ_ACCESS\": " << stats.WQ_ACCESS << "," << std::endl;
    stream << indent() << "\"WQ_MERGED\": " << stats.WQ_MERGED << "," << std::endl;
    stream << indent() << "\"WQ_FULL\": " << stats.WQ_FULL << "," << std::endl;
    --indent_level;
    stream << indent() << "}";
}

void champsim::json_printer::print(DRAM_CHANNEL::stats_type stats) {
    stream << indent() << "{" << std::endl;
    ++indent_level;
    stream << indent() << "\"RQ ROW_BUFFER_HIT\": " << stats.RQ_ROW_BUFFER_HIT << "," << std::endl;
    stream << indent() << "\"RQ ROW_BUFFER_MISS\": " << stats.RQ_ROW_BUFFER_MISS << "," << std::endl;
    stream << indent() << "\"PQ FULL\": " << stats.RQ_FULL << "," << std::endl;
    stream << indent() << "\"WQ ROW_BUFFER_HIT\": " << stats.WQ_ROW_BUFFER_HIT << "," << std::endl;
    stream << indent() << "\"WQ ROW_BUFFER_MISS\": " << stats.WQ_ROW_BUFFER_MISS << "," << std::endl;
    stream << indent() << "\"WQ FULL\": " << stats.WQ_FULL << "," << std::endl;
    if (stats.dbus_count_congested > 0)
        stream << indent() << "\"AVG DBUS CONGESTED CYCLE\": " << std::ceil(stats.dbus_cycle_congested) / std::ceil(stats.dbus_count_congested) << std::endl;
    else
        stream << indent() << "\"AVG DBUS CONGESTED CYCLE\": null" << std::endl;
    --indent_level;
    stream << indent() << "}";
}

void champsim::json_printer::print(std::vector<O3_CPU::stats_type> stats_list) {
    stream << indent() << "\"cores\": [" << std::endl;
    ++indent_level;

    bool first = true;
    for (const auto& stats : stats_list) {
        if (!first)
            stream << "," << std::endl;
        print(stats);
        first = false;
    }
    stream << std::endl;

    --indent_level;
    stream << indent() << "]";
}

void champsim::json_printer::print(std::vector<CACHE::stats_type> stats_list) {
    bool first = true;
    for (const auto& stats : stats_list) {
        if (!first)
            stream << "," << std::endl;
        print(stats);
        first = false;
    }
}

void champsim::json_printer::print(std::vector<CACHE::NonTranslatingQueues::stats_type> stats_list) {
    bool first = true;
    for (const auto& stats : stats_list) {
        if (!first)
            stream << "," << std::endl;
        print(stats);
        first = false;
    }
}

void champsim::json_printer::print(std::vector<CACHE::stats_type> cache_stats_list, std::vector<CACHE::NonTranslatingQueues::stats_type> cache_queue_stats_list) {
    bool first = true;
    for (int i = 0; i < cache_stats_list.size(); i++) {
        if (!first)
            stream << "," << std::endl;
        print(cache_stats_list[i], cache_queue_stats_list[i]);
        first = false;
    }
}

void champsim::json_printer::print(std::vector<DRAM_CHANNEL::stats_type> stats_list) {
    stream << indent() << "\"DRAM\": [" << std::endl;
    ++indent_level;

    bool first = true;
    for (const auto& stats : stats_list) {
        if (!first)
            stream << "," << std::endl;
        print(stats);
        first = false;
    }
    stream << std::endl;

    --indent_level;
    stream << indent() << "]" << std::endl;
}

void champsim::json_printer::print(champsim::phase_stats& stats) {
    stream << indent() << "{" << std::endl;
    ++indent_level;

    stream << indent() << "\"name\": \"" << stats.name << "\"," << std::endl;
    stream << indent() << "\"traces\": [" << std::endl;
    ++indent_level;

    bool first = true;
    for (auto t : stats.trace_names) {
        if (!first)
            stream << "," << std::endl;
        stream << indent() << "\"" << t << "\"";
        first = false;
    }

    --indent_level;
    stream << std::endl
           << indent() << "]," << std::endl;

    stream << indent() << "\"roi\": {" << std::endl;
    ++indent_level;

    print(stats.roi_cpu_stats);
    stream << "," << std::endl;

    // print(stats.roi_cache_stats);
    // stream << "," << std::endl;

    print(stats.roi_cache_stats, stats.roi_cache_queue_stats);
    stream << "," << std::endl;

    print(stats.roi_dram_stats);
    stream << std::endl;

    --indent_level;
    stream << indent() << "}," << std::endl;

    stream << indent() << "\"sim\": {" << std::endl;
    ++indent_level;

    print(stats.sim_cpu_stats);
    stream << "," << std::endl;

    print(stats.sim_cache_stats, stats.sim_cache_queue_stats);
    stream << "," << std::endl;

    print(stats.sim_dram_stats);
    stream << std::endl;

    --indent_level;
    stream << indent() << "}" << std::endl;
    --indent_level;
    stream << indent() << "}" << std::endl;
}

void champsim::json_printer::print(std::vector<phase_stats>& stats) {
    stream << "[" << std::endl;
    ++indent_level;

    for (auto p : stats)
        print(p);

    stream << "]" << std::endl;
    --indent_level;
}
