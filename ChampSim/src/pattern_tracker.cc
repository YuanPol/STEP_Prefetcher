#include "pattern_tracker.h"
#include "champsim_constants.h"
#include <assert.h>
#include <utility>
#include <iostream>
#include <iomanip>
#include <numeric>

namespace pattern_tracker {

PatternTracker::PatternTracker() {}

void PatternTracker::access(uint64_t addr, uint64_t ip) {
    if (track) {
        timestamp++;
        int valid_active_num = std::count_if(active_patterns.begin(), active_patterns.end(), [](auto x) { return x.valid; });
        assert(valid_active_num <= max_track_num);
        total_active += valid_active_num;
        if (valid_active_num > max_active) max_active = valid_active_num;

        uint64_t base_addr = addr >> LOG2_PAGE_SIZE;
        uint64_t page_offset = addr ^ (base_addr << LOG2_PAGE_SIZE);
        assert(page_offset < (1 << LOG2_PAGE_SIZE));
        uint64_t block_num = page_offset >> LOG2_BLOCK_SIZE;
        assert(block_num < 64 && block_num >= 0);

        // addr + pc >> 6
        ip = 0;

        for (auto p = active_patterns.begin(); p != active_patterns.end(); p++) {
            if (p->valid) {
                ++(p->keep_track_time);
                if (p->keep_track_time > max_track_timestamp) {
                    p->valid = false;
                    auto first_valid = std::find_if(active_patterns.begin(), active_patterns.end(), [](auto x) { return x.valid; });
                    if (first_valid != active_patterns.end()) {
                        std::iter_swap(p, first_valid);
                    }
                }
            }
        }

        auto p = std::find_if(active_patterns.begin(), active_patterns.end(), [base_addr, ip](auto x) { return x.valid && x.base_addr == base_addr && x.ip == ip; });
        if (p == active_patterns.end()) { // not found
            pattern new_p;

            new_p.base_addr = base_addr;
            new_p.ip = ip;
            new_p.trigger_offset = block_num;
            new_p.bit_vector[block_num] = 1;
            new_p.access_order.push_back(block_num);
            new_p.first_accessed = new_p.last_updated = new_p.last_accessed = timestamp;
            new_p.keep_track_time = 0;

            active_patterns.push_back(new_p);
        } else { // found
            if (p->bit_vector[block_num] == 0) {
                p->bit_vector[block_num] = 1;
                p->last_updated = timestamp;
            }
            if (p->access_order.size() == 1)
                p->second_accessed = timestamp;
            p->access_order.push_back(block_num);
            p->last_accessed = timestamp;
            p->keep_track_time = 0;
        }

        if (!(timestamp & 15)) { // t % 16 == 0
            auto first_valid = std::find_if(active_patterns.begin(), active_patterns.end(), [](auto x) { return x.valid; });
            for (auto it = active_patterns.begin(); it != first_valid; it++) {
                saved_patterns.push_back(*it);
            }
            active_patterns.erase(active_patterns.begin(), first_valid);
            if (saved_patterns.size() > max_track_num)
                track = false;
        }
    }
}

void PatternTracker::final_stats() {
    std::cout << "Total patterns: " << saved_patterns.size() << " Average Active " << (timestamp == 0 ? 0 : total_active / timestamp) << " Max Active " << max_active << " ";
    int num_1 = 0, num_2 = 0, num_less_than_5 = 0, num_at_least_5 = 0;
    for (auto& p : saved_patterns) {
        if (std::accumulate(p.bit_vector, p.bit_vector + std::size(p.bit_vector), 0) == 1)
            num_1++;
        else if (std::accumulate(p.bit_vector, p.bit_vector + std::size(p.bit_vector), 0) == 2)
            num_2++;
        else if (std::accumulate(p.bit_vector, p.bit_vector + std::size(p.bit_vector), 0) < 5)
            num_less_than_5++;
        else
            num_at_least_5++;
    }
    std::cout << "1 bit pattern: " << num_1 << " 2 bit pattern: " << num_2 << " less than 5 bit pattern: " << num_less_than_5 << " at least 5 bit pattern: " << num_at_least_5 << std::endl;

    for (auto& p : saved_patterns)
        p.print();
}

void PatternTracker::initialize() {
}

void PatternTracker::pattern::print() {
    std::cout << std::bitset<36>(base_addr).to_string() << " " << std::bitset<32>(ip).to_string() << " " << std::bitset<6>(trigger_offset).to_string() << " "
              << "first " << first_accessed << " "
              << "second " << second_accessed << " "
              << "generated " << last_updated << " "
              << "last " << last_accessed << " "
              << "access num " << access_order.size() << " "
              << "bit num " << std::accumulate(bit_vector, bit_vector + std::size(bit_vector), 0) << std::endl;
    for (auto b : bit_vector)
        std::cout << b;
    std::cout << std::endl;
    uint64_t access_order_array[BLOCK_SIZE] = {0};
    int o = 0;
    for (auto a : access_order) {
        if (access_order_array[a] == 0) access_order_array[a] = ++o;
    }
    for (auto a : access_order_array)
        std::cout << a;
    std::cout << std::endl;
}

} // namespace pattern_tracker