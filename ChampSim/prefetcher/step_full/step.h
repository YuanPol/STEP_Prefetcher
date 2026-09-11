#ifndef STEP_PREFETCHER_8WAY_STRIDE_H
#define STEP_PREFETCHER_8WAY_STRIDE_H

/* Author: Yuanji Ye (yuanji.ye@tum.de)
    Description:
    The STEP (Spatial Footprint Prefetcher with Multi-Point Temporal Triggers) with stride support,
    adapted for the legacy ChampSim (footprint-prefetcher) interface.
*/

#include "custom_util.h"
#include "cache.h"

#include <stdint.h>
#include <deque>
#include <vector>
#include <algorithm>
#include <memory>

namespace step {

#define __region_offset(block_num) (block_num & REGION_OFFSET_MASK)

#define FT_TYPE custom_util::SRRIPSetAssociativeCache
#define AT_TYPE custom_util::LRUSetAssociativeCache
#define PT_TYPE custom_util::LRUFuzzSetAssociativeTable
#define PB_TYPE custom_util::LRUSetAssociativeCache

constexpr uint64_t REGION_SIZE = 4 * 1024;
constexpr uint64_t LOG2_REGION_SIZE = champsim::lg2(REGION_SIZE);
constexpr uint64_t REGION_OFFSET_MASK = (1ULL << (LOG2_REGION_SIZE - LOG2_BLOCK_SIZE)) - 1;

constexpr int NUM_BLOCKS = REGION_SIZE / BLOCK_SIZE;
constexpr uint64_t LOG2_NUM_BLOCKS = champsim::lg2(NUM_BLOCKS);

#ifndef STEP_FT_SIZE
#define STEP_FT_SIZE 256
#endif
constexpr int FT_SIZE = STEP_FT_SIZE, FT_WAY = 8;
#ifndef STEP_AT_SIZE
#define STEP_AT_SIZE 128
#endif
constexpr int AT_SIZE = STEP_AT_SIZE, AT_WAY = 8;
#ifndef STEP_PT_WAY
#define STEP_PT_WAY 8
#endif
constexpr int PT_WAY = STEP_PT_WAY;
constexpr int PT_SIZE = PT_WAY * NUM_BLOCKS;
constexpr int PB_SIZE = 32, PB_WAY = 8;
constexpr int STRIDE_PF_LOOKAHEAD = 2;
constexpr int PF_FILL_L2 = 2;
const uint64_t ACCURACY_DETECT_INTERVAL = 100000;

const uint64_t T_SIMILARITY = 3;
#ifndef STEP_T_JACCARD
#define STEP_T_JACCARD 75
#endif
const double T_JACCARD = STEP_T_JACCARD/100.0;
#ifndef STEP_T_RECENT_COMP
#define STEP_T_RECENT_COMP 3
#endif
const uint64_t T_RECENT_COMP = STEP_T_RECENT_COMP;
const uint64_t SUBSET_THRESHOLD = 1;

// ------------------------- Util Functions ------------------------- //
std::vector<int> pattern_bool2int(std::vector<bool> pattern);
std::vector<bool> pattern_int2bool(std::vector<int> pattern);
bool pattern_all_set(std::vector<bool> pattern);
bool is_subset(const std::vector<bool>& pattern_a, const std::vector<bool>& pattern_b);

// ------------------------- Filter Table ------------------------- //
struct FilterTableData {
    uint64_t trigger_offset;
    uint64_t second_offset;
    uint64_t region_num;
    uint64_t pc;
    uint8_t prefetch_issued = 0;
};

class FilterTable : public FT_TYPE<FilterTableData> {
    typedef FT_TYPE<FilterTableData> Super;

private:
    uint64_t build_key(uint64_t region_num);

public:
    FilterTable(int size, int num_ways);

    Entry* find(uint64_t region_num);
    Entry insert(uint64_t region_num, uint64_t trigger_offset, uint64_t pc);
    void set_second_offset(uint64_t region_num, uint64_t second_offset);
    Entry* erase(uint64_t region_num);
};


// ------------------------- Accumulate Table ------------------------- //
struct AccumulateTableData {
    uint64_t trigger_offset;
    uint64_t second_offset;
    uint64_t third_offset;
    uint64_t pc;
    bool missed_in_pt;
    std::vector<bool> pattern;
    std::vector<int> order;

    int last_stride;
    uint64_t last_offset;
    uint64_t region_num;
    bool con = false;

    int timestamp = 2;
};

class AccumulateTable : public AT_TYPE<AccumulateTableData> {
    typedef AT_TYPE<AccumulateTableData> Super;

private:
    bool __stride_prefetch = false;

    uint64_t build_key(uint64_t region_num);

public:
    bool get_stride_prefetch();
    void turn_off_stride_prefetch();

public:
    AccumulateTable(int size, int num_ways);

    Entry* set_pattern(uint64_t region_num, uint64_t offset);

    Entry insert(uint64_t region_num, uint64_t trigger_offset, uint64_t second_offset, uint64_t third_offset, uint64_t pc, bool missed_in_pt, bool con);
    Entry* erase(uint64_t region_num);
};

// ------------------------- Pattern Table ------------------------- //
struct PatternTableData {
    std::vector<int> pattern;
    uint64_t pc;
    bool con = false;
    bool foe_single_mature = false;
};

struct PrefetchPrediction;
class PatternTable : public PT_TYPE<PatternTableData> {
    typedef PT_TYPE<PatternTableData> Super;

private:
    uint64_t build_key(uint64_t trigger, uint64_t second, uint64_t third, uint64_t pc, uint64_t region_num);
    Entry prediction_entry{};

public:
    std::deque<uint64_t> con_pc;
    int con_counter = 0;

    PatternTable(int size, int num_ways);

    Entry* check_similarity(const std::vector<Entry*>& matches, const std::vector<int>& observed_offsets);
    PrefetchPrediction find_most_recent_two_offsets(uint64_t pc, uint64_t offset1, uint64_t offset2);
    PrefetchPrediction find_most_recent_one_offset(uint64_t pc, uint64_t offset1);
    void insert(uint64_t trigger, uint64_t second, uint64_t third, uint64_t pc, uint64_t region_num, std::vector<bool> pattern, uint64_t current_cycle);
    PrefetchPrediction find(CACHE* cache, uint64_t trigger, uint64_t second, uint64_t third, uint64_t pc, uint64_t region_num, int bw);
};

enum class FOEMatchType : uint8_t {
    NONE = 0,
    SINGLE = 1,
    MULTI = 2,
};

struct PrefetchPrediction {
    PatternTable::Entry* entry = nullptr;
    int issue_finished = 0;
    FOEMatchType foe_match_type = FOEMatchType::NONE;
};

// ------------------------- Prefetch Buffer ------------------------- //
struct PrefetchBufferData {
public:
    std::vector<int> pattern;
    uint64_t trigger;
    uint64_t second;
    uint64_t third;
    std::vector<int> pf_metadata;
};

class PrefetchBuffer : public PB_TYPE<PrefetchBufferData> {
    typedef PB_TYPE<PrefetchBufferData> Super;

private:
    uint64_t build_key(uint64_t region_num);

public:
    PrefetchBuffer(int size, int num_ways);

    void insert(uint64_t region_num, std::vector<int> pattern, uint64_t trigger, uint64_t second, uint64_t third, uint32_t pf_metadata);
    void prefetch(CACHE* cache, uint64_t block_num, double prefetch_accuracy);
};

// ------------------------- STEP Prefetcher ------------------------- //
class STEP {
private:
    int stride_pf_degree = 4;
    double prefetch_accuracy = 0.5;
    uint64_t accuracy_streak = 0;
    uint64_t zero_accuracy_intervals = 0;

    std::unique_ptr<FilterTable> ft;
    std::unique_ptr<AccumulateTable> at;
    std::unique_ptr<PatternTable> pt;
    std::unique_ptr<PrefetchBuffer> pb;

    PrefetchPrediction find_in_pt(CACHE* cache,uint64_t trigger, uint64_t second, uint64_t third, uint64_t pc, uint64_t region_num, int bw);
    void insert_in_pt(const AccumulateTable::Entry& entry, uint64_t region_num, uint64_t current_cycle);
    void update_accuracy_stats(CACHE* cache);
    double accuracy_calculation(uint64_t period_useless, uint64_t period_useful);

public:
    uint64_t cycle_prev = 0;
    uint64_t useful_prefetches = 0;
    uint64_t useless_prefetches = 0;

    STEP(int ft_size, int ft_ways, int at_size, int at_ways, int pt_size, int pt_ways, int pb_size, int pb_ways);
    STEP();
    void access(CACHE* cache, uint64_t block_num, uint64_t ip);
    void prefetch(CACHE* cache, uint64_t block_num);

};

} // namespace step

#endif
