#ifndef PATTERN_TRACKER_H
#define PATTERN_TRACKER_H

#include "champsim_constants.h"
#include <vector>
#include <bitset>

namespace pattern_tracker {

constexpr int max_track_timestamp = 1024;
constexpr int max_track_num = 100000;

class PatternTracker {
public:
    typedef struct tag_pattern {
        bool valid = true;
        uint64_t base_addr;
        uint64_t ip;
        uint64_t trigger_offset;
        uint64_t bit_vector[BLOCK_SIZE] = {0};
        std::vector<uint64_t> access_order;
        uint64_t first_accessed = 0;
        uint64_t second_accessed = 0;
        uint64_t last_accessed = 0;
        uint64_t last_updated = 0;
        uint64_t keep_track_time = 0;
        void print();
    } pattern;

private:
    bool track = true;
    uint64_t timestamp = 0;
    uint64_t total_active = 0;
    uint64_t max_active = 0;
    std::vector<pattern> active_patterns;
    std::vector<pattern> saved_patterns;

public:
    void access(uint64_t addr, uint64_t ip);
    void final_stats();
    void initialize();

    void calculateSimularity(uint64_t* bv1, uint64_t* bv2);

    void searchByIP(uint64_t ip);
    void searchByOffset(uint64_t offset);
    void countByIP(uint64_t ip);
    void countByOffset(uint64_t offset);
    void approxSearchByIP(uint64_t ip, uint64_t approx_bit_num);
    void approxSearchByOffset(uint64_t offset, uint64_t approx_bit_num);
    void approxCountByIP(uint64_t ip, uint64_t approx_bit_num);
    void approxCountByOffset(uint64_t offset, uint64_t approx_bit_num);

    PatternTracker();
    // ~PatternTracker();
};
} // namespace pattern_tracker
#endif