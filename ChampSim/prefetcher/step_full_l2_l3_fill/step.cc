#include "step.h"
#include <algorithm>
#include <cassert>
#include <iostream>

#ifndef STEP_PREFETCHER_DISABLE_FIRST_OFFSET
#define STEP_PREFETCHER_DISABLE_FIRST_OFFSET 0
#endif

#ifndef STEP_PREFETCHER_DISABLE_SECOND_OFFSET
#define STEP_PREFETCHER_DISABLE_SECOND_OFFSET 0
#endif

#ifndef STEP_PREFETCHER_DISABLE_THIRD_OFFSET
#define STEP_PREFETCHER_DISABLE_THIRD_OFFSET 0
#endif

/* Author: Yuanji Ye (yuanji.ye@tum.de)
    Description:
    STEP: Spatial Footprint Prefetcher with Multi-Point Temporal Triggers
*/
static std::vector<step::STEP> prefetchers;

namespace step {

// ------------------------- FT functions ------------------------- //

FilterTable::FilterTable(int size, int num_ways) :
    Super(size, num_ways) {}

FilterTable::Entry* FilterTable::find(uint64_t region_num) {
    uint64_t key = build_key(region_num);
    Entry* entry = Super::find(key);
    if (!entry) {
        return nullptr;
    } else {
        Super::rp_promote(key);
        return entry;
    }
}


FilterTable::Entry FilterTable::insert(uint64_t region_num, uint64_t trigger_offset, uint64_t pc) {
    uint64_t key = build_key(region_num);
    Entry entry = Super::insert(key, {trigger_offset, 64, region_num, pc, 0});
    Super::rp_insert(key);
    return entry;
}

void FilterTable::set_second_offset(uint64_t region_num, uint64_t second_offset) {
    uint64_t key = build_key(region_num);
    Entry* entry = Super::find(key);
    assert(entry);
    entry->data.second_offset = second_offset;
    Super::rp_promote(key);
}

FilterTable::Entry* FilterTable::erase(uint64_t region_num) {
    uint64_t key = build_key(region_num);
    return Super::erase(key);
}

std::string FilterTable::log() {
    std::vector<std::string> headers({"RegionNum", "Trigger", "Second", "PC"});
    return Super::log(headers);
}

uint64_t FilterTable::build_key(uint64_t region_num) {
    uint64_t key = region_num & ((1ULL << 37) - 1);
    return custom_util::hash_index(key, this->index_len);
}

void FilterTable::write_data(Entry& entry, custom_util::Table& table, int row) {
    uint64_t key = custom_util::hash_index(entry.key, this->index_len);
    table.set_cell(row, 0, key);
    table.set_cell(row, 1, entry.data.trigger_offset);
    table.set_cell(row, 2, entry.data.second_offset);
    table.set_cell(row, 3, entry.data.pc);
}


// ------------------------- AT functions ------------------------- //
AccumulateTable::AccumulateTable(int size, int num_ways) :
    Super(size, num_ways) {}

AccumulateTable::Entry* AccumulateTable::set_pattern(uint64_t region_num, uint64_t offset) {
    uint64_t key = build_key(region_num);
    Entry* entry = Super::find(key);
    if (!entry)
        return nullptr;
    else {
        if (!entry->data.pattern[offset]) {
            entry->data.timestamp++;
            int stride = int(offset) - int(entry->data.last_offset);
            if (entry->data.missed_in_pt || entry->data.con)
                this->__stride_prefetch = (stride == entry->data.last_stride);
            entry->data.order[offset] = entry->data.timestamp;
            entry->data.pattern[offset] = true;
            entry->data.last_offset = offset;
            entry->data.last_stride = stride;
        }
        Super::rp_promote(key);
        return entry;
    }
}

AccumulateTable::Entry AccumulateTable::insert(uint64_t region_num, uint64_t trigger_offset, uint64_t second_offset, uint64_t third_offset, uint64_t pc, bool missed_in_pt, bool con) {
    uint64_t key = build_key(region_num);
    std::vector<bool> pattern(NUM_BLOCKS, false);
    std::vector<int> order(NUM_BLOCKS, 0);
    pattern[trigger_offset] = pattern[second_offset] = pattern[third_offset] = true;
    order[trigger_offset] = 1;
    order[second_offset] = 2;
    order[third_offset] = 3;
    int last_stride = int(third_offset) - int(second_offset);
    Entry old_entry = Super::insert(key, {trigger_offset, second_offset,third_offset, pc, missed_in_pt, pattern, order, last_stride, third_offset, con});
    Super::rp_insert(key);
    return old_entry;
}

AccumulateTable::Entry* AccumulateTable::erase(uint64_t region_num) {
    uint64_t key = build_key(region_num);
    return Super::erase(key);
}

std::string AccumulateTable::log() {
    std::vector<std::string> headers({"RegionNum", "Trigger", "Second", "Third", "PC", "Pattern", "Order"});
    return Super::log(headers);
}

void AccumulateTable::write_data(Entry& entry, custom_util::Table& table, int row) {
    uint64_t key = custom_util::hash_index(entry.key, this->index_len);
    table.set_cell(row, 0, key);
    table.set_cell(row, 1, entry.data.trigger_offset);
    table.set_cell(row, 2, entry.data.second_offset);
    table.set_cell(row, 3, entry.data.third_offset);
    table.set_cell(row, 4, entry.data.pc);
    table.set_cell(row, 5, custom_util::pattern_to_string(entry.data.pattern));
    table.set_cell(row, 6, custom_util::pattern_to_string(entry.data.order));
}

uint64_t AccumulateTable::build_key(uint64_t region_num) {
    uint64_t key = region_num & ((1ULL << 37) - 1);
    return custom_util::hash_index(key, this->index_len);
}

bool AccumulateTable::get_stride_prefetch() {
    return __stride_prefetch;
}

void AccumulateTable::turn_off_stride_prefetch() {
    __stride_prefetch = false;
}

// ------------------------- PHT functions ------------------------- //
PatternTable::PatternTable(int size, int num_ways) :
    Super(size, num_ways) {
    std::cout << "Pattern Table index_len: " << Super::index_len << std::endl;
}


PatternTable::Entry* PatternTable::check_similarity(const std::vector<Entry*>& matches, const std::vector<int>& observed_offsets) {
    if (matches.empty()) {
        return nullptr;
    }
    // if only one entry is found, return directly
    int consider_count = std::min(T_RECENT_COMP, static_cast<uint64_t>(matches.size()));
    if (consider_count <= 1) {
        return new Entry(*matches[0]);
    }

    auto mask_observed_offsets = [&](std::vector<bool>& pattern) {
        for (int offset : observed_offsets) {
            if (offset >= 0 && offset < static_cast<int>(pattern.size())) {
                pattern[offset] = false;
            }
        }
    };

    // compare with the most recent pattern
    int similar_count = 1;
    int containment_count = 0; // also consider the inclusive relationship
    const auto& most_recent_pattern = matches[0]->data.pattern;
    std::vector<bool> most_recent_pattern_bool = custom_util::pattern_int2bool(most_recent_pattern);
    mask_observed_offsets(most_recent_pattern_bool);
    uint64_t most_recent_mask = custom_util::pattern_to_int(most_recent_pattern_bool);

    for (int i = 1; i < consider_count; i++) {
        const auto& current_pattern = matches[i]->data.pattern;
        std::vector<bool> current_pattern_bool = custom_util::pattern_int2bool(current_pattern);
        mask_observed_offsets(current_pattern_bool);
        uint64_t current_mask = custom_util::pattern_to_int(current_pattern_bool);
        uint64_t union_mask = most_recent_mask | current_mask;

        bool is_similar = false;
        if (union_mask == 0) {
            is_similar = true;
        } else {
            int union_bits = custom_util::count_bits(union_mask);
            int intersection_bits = custom_util::count_bits(most_recent_mask & current_mask);
            double jaccard = union_bits == 0 ? 1.0 : static_cast<double>(intersection_bits) / union_bits;
            if (jaccard > T_JACCARD) {
                is_similar = true;
            }
        }

        if (is_similar) {
            similar_count++;
        } else if (is_subset(most_recent_pattern_bool, current_pattern_bool) ||
                   is_subset(current_pattern_bool, most_recent_pattern_bool)) {
            containment_count++;
        }
    }

    uint64_t required_count = std::min(T_SIMILARITY, static_cast<uint64_t>(consider_count));
    if (similar_count+containment_count >= required_count) {
        return new Entry(*matches[0]);
    }
    return nullptr;
}

PrefetchPrediction PatternTable::find_most_recent_two_offsets(uint64_t pc, uint64_t offset1, uint64_t offset2) {
    // Find all potential candidates based on offsets.
    auto all_candidates = this->find_partial_two_offsets(offset1, offset2);
    if (all_candidates.empty()) {
        return {nullptr, 0};
    }

    // Add PC filter
    std::vector<Entry*> pc_matches;
    for (Entry* candidate : all_candidates) {
        if (candidate->data.pc == pc) {
            pc_matches.push_back(candidate);
        }
    }

    if (!pc_matches.empty()) {
        // If we have entries that match the PC, they take absolute priority.
        // We will base our entire decision on their consensus.
        
        std::sort(pc_matches.begin(), pc_matches.end(), [](Entry* a, Entry* b) {
            return a->insert_time > b->insert_time;
        });
        std::vector<int> observed_offsets;
        if (offset1 < NUM_BLOCKS) {
            observed_offsets.push_back(static_cast<int>(offset1));
        }
        Entry* consensus_entry = check_similarity(pc_matches, observed_offsets);
        if (consensus_entry) {
            return {consensus_entry, 2};
        }

    } 

    std::sort(all_candidates.begin(), all_candidates.end(), [](Entry* a, Entry* b) {
        return a->insert_time > b->insert_time;
    });

    // provide the observed offsets
    std::vector<int> observed_offsets;
    observed_offsets.reserve(2);
    if (offset1 < NUM_BLOCKS) {
        observed_offsets.push_back(static_cast<int>(offset1));
    }
    if (offset2 < NUM_BLOCKS) {
        observed_offsets.push_back(static_cast<int>(offset2));
    }

    Entry* consensus_entry = check_similarity(all_candidates, observed_offsets);

    if (consensus_entry) {
#if STEP_PREFETCHER_DISABLE_THIRD_OFFSET
        return {consensus_entry, 2};
#else
        // do the intersection
        int consider_count = static_cast<int>(std::min(T_RECENT_COMP, static_cast<uint64_t>(all_candidates.size())));
        std::vector<bool> intersection = custom_util::pattern_int2bool(all_candidates[0]->data.pattern);
        for (int offset : observed_offsets) {
            if (offset >= 0 && offset < static_cast<int>(intersection.size())) {
                intersection[offset] = false;
            }
        }
        for (int i = 1; i < consider_count; i++) {
            std::vector<bool> current = custom_util::pattern_int2bool(all_candidates[i]->data.pattern);
            for (int offset : observed_offsets) {
                if (offset >= 0 && offset < static_cast<int>(current.size())) {
                    current[offset] = false;
                }
            }
            for (size_t j = 0; j < intersection.size(); j++) {
                intersection[j] = intersection[j] && current[j];
            }
        }

        bool has_intersection = std::any_of(intersection.begin(), intersection.end(), [](bool v) { return v; });
        if (has_intersection) {
            consensus_entry->data.pattern = pattern_bool2int(intersection);
            return {consensus_entry, 1};
        }

        delete consensus_entry;
        consensus_entry = nullptr;
#endif
    }

    return {nullptr, 0};

}

PrefetchPrediction PatternTable::find_most_recent_one_offset(uint64_t pc, uint64_t offset1) {
    // 1. Find all candidates that match the first offset
    auto all_candidates = this->find_partial_one_offset(offset1);
    if (all_candidates.empty()) {
        return {nullptr, 0};
    }

    // 2. match the candiates with pc + offset
    std::vector<Entry*> pc_matches;
    for (Entry* candidate : all_candidates) {
        if (candidate->data.pc == pc) {
            pc_matches.push_back(candidate);
        }
    }

    if (!pc_matches.empty()) {
        
        std::sort(pc_matches.begin(), pc_matches.end(), [](Entry* a, Entry* b) {
            return a->insert_time > b->insert_time;
        });
        std::vector<int> observed_offsets;
        if (offset1 < NUM_BLOCKS) {
            observed_offsets.push_back(static_cast<int>(offset1));
        }
        Entry* consensus_entry = check_similarity(pc_matches, observed_offsets);

        // do the intersection
        if (consensus_entry != nullptr) {
            int consider_count = static_cast<int>(std::min(T_RECENT_COMP, static_cast<uint64_t>(pc_matches.size())));
            std::vector<bool> intersection = custom_util::pattern_int2bool(pc_matches[0]->data.pattern);
            for (int offset : observed_offsets) {
                if (offset >= 0 && offset < static_cast<int>(intersection.size())) {
                    intersection[offset] = false;
                }
            }
            for (int i = 1; i < consider_count; i++) {
                std::vector<bool> current = custom_util::pattern_int2bool(pc_matches[i]->data.pattern);
                for (int offset : observed_offsets) {
                    if (offset >= 0 && offset < static_cast<int>(current.size())) {
                        current[offset] = false;
                    }
                }
                for (size_t j = 0; j < intersection.size(); j++) {
                    intersection[j] = intersection[j] && current[j];
                }
            }

            bool has_intersection = std::any_of(intersection.begin(), intersection.end(), [](bool v) { return v; });
            if (has_intersection) {
                consensus_entry->data.pattern = pattern_bool2int(intersection);
                return {consensus_entry, 2};
            }

            delete consensus_entry;
        }

    } 

    return {nullptr, 0};
}

void PatternTable::insert(uint64_t trigger, uint64_t second,  uint64_t third, uint64_t pc, uint64_t region_num, std::vector<bool> pattern,uint64_t current_cycle) {
    assert(pattern[trigger] && pattern[second] && pattern[third]);
    bool all_set = pattern_all_set(pattern);

    if (trigger != 0 || second != 1) { // not spatial streaming

        uint64_t key = build_key(trigger, second, third, pc, region_num);
        Super::insert(key, {pattern_bool2int(pattern), pc},current_cycle);
        Super::rp_insert(key);

    } else { // spatial streaming
        if (all_set) {
            if (con_counter < 8)
                con_counter++;
            uint64_t hashed_pc = custom_util::my_hash_index(pc, LOG2_BLOCK_SIZE, 8);
            if (con_pc.end() == std::find_if(con_pc.begin(), con_pc.end(), [hashed_pc](auto& x) { return x == hashed_pc; })) {
                if (con_pc.size() == 8)
                    con_pc.pop_back();
                con_pc.push_front(hashed_pc);
            }
        } else {
            if (con_counter > 2)
                con_counter >> 1;
            else if (con_counter > 0)
                con_counter--;
        }
    }
}

PrefetchPrediction PatternTable::find(CACHE* cache, uint64_t trigger, uint64_t second,  uint64_t third, uint64_t pc, uint64_t region_num, int bw) {
    if (trigger != 0 || second != 1) { // not ss
        if (second == 64){ // one offsets event
            if (STEP_PREFETCHER_DISABLE_FIRST_OFFSET) {
                return {nullptr, 0};
            }
            if(cache->get_occupancy(3, 0) + cache->get_occupancy(0, 0) > (cache->get_size(0, 0)-1) && cache->get_occupancy(3, 0) > (cache->get_size(3, 0))){
                return {nullptr, 0};
            }
            return find_most_recent_one_offset(pc,trigger);
        }
        else if (third == 64){ // Two offsets event
            if (STEP_PREFETCHER_DISABLE_SECOND_OFFSET) {
                return {nullptr, 0};
            }
            if(cache->get_occupancy(3, 0) + cache->get_occupancy(0, 0) > (cache->get_size(0, 0)-1) && cache->get_occupancy(3, 0) > (cache->get_size(3, 0))){
                return {nullptr, 0};
            }
            return find_most_recent_two_offsets(pc,trigger,second);
        }
        else{ // three offsets event
            if (STEP_PREFETCHER_DISABLE_THIRD_OFFSET) {
                return {nullptr, 0};
            }
            uint64_t key = build_key(trigger, second, third, pc, region_num);
            auto entry = Super::find(key);
            if(!entry){
                return PrefetchPrediction{nullptr, 0};
            }
            return PrefetchPrediction{Super::find(key),2};
        }
    } else { // stream pattern
        uint64_t hashed_pc = custom_util::my_hash_index(pc, LOG2_BLOCK_SIZE, 8);

        if (con_counter == 8 || con_pc.end() != std::find_if(con_pc.begin(), con_pc.end(), [hashed_pc](auto& x) { return x == hashed_pc; })) {
            Entry* ret = new Entry();
            ret->data.con = true;
            ret->data.pattern.assign(NUM_BLOCKS, 0);
            for (int i = 0; i < NUM_BLOCKS / 4; i++) {
                ret->data.pattern[i] = PF_FILL_L2;
            }
            for (int i = NUM_BLOCKS / 4; i < NUM_BLOCKS; i++) {
                ret->data.pattern[i] = PF_FILL_L3;
            }
            return PrefetchPrediction{ret,2};
        } else if (con_counter > 2) {
            Entry* ret = new Entry();
            ret->data.con = true;
            ret->data.pattern.assign(NUM_BLOCKS, 0);
            for (int i = 0; i < NUM_BLOCKS / 4; i++) {
                ret->data.pattern[i] = PF_FILL_L3;
            }
            return PrefetchPrediction{ret,2};
        }
        return PrefetchPrediction{nullptr,0};
    }
    assert(0);
}

std::string PatternTable::log() {
    std::vector<std::string> headers({"Trigger", "Second", "Third", "Pattern"});
    return Super::log(headers);
}

void PatternTable::write_data(Entry& entry, custom_util::Table& table, int row) {
    table.set_cell(row, 0, int(entry.key & uint64_t((1ULL << this->index_len) - 1)));
    table.set_cell(row, 1, int((entry.key >> this->index_len) & ((1ULL << this->index_len) - 1)));
    table.set_cell(row, 2, int((entry.key >> (this->index_len+LOG2_NUM_BLOCKS)) & ((1ULL << this->index_len) - 1)));
    table.set_cell(row, 3, custom_util::pattern_to_string(entry.data.pattern));
}

uint64_t PatternTable::build_key(uint64_t trigger, uint64_t second, uint64_t third, uint64_t pc, uint64_t region_num) {
    assert(trigger >= 0 && trigger < NUM_BLOCKS && second >= 0 && second < NUM_BLOCKS && third >= 0 && third < NUM_BLOCKS);
    uint64_t key = (third << (this->index_len+LOG2_NUM_BLOCKS)) | (second << this->index_len) | trigger;
    return key;
}


// ------------------------- PB functions ------------------------- //
PrefetchBuffer::PrefetchBuffer(int size, int pattern_len, int debug_level = 0, int num_ways = 16) :
    Super(size, num_ways), pattern_len(pattern_len) {
}

void PrefetchBuffer::insert(uint64_t region_num, std::vector<int> pattern, uint64_t trigger, uint64_t second, uint64_t third, uint32_t pf_metadata) {
    uint64_t key = this->build_key(region_num);
    if ((pf_metadata & 3) == 0 || (pf_metadata & 3) == 3) { // stride & promote
        auto entry = find(key);
        if (!entry) {
            Super::insert(key, {pattern, trigger, second, third, std::vector<int>(step::NUM_BLOCKS, pf_metadata)});
            Super::rp_insert(key);
        } else {
            for (int i = 0; i < NUM_BLOCKS; i++) {
                // currently we fill everything into L2 thus this is an abandoned logic but can be useful later
                if (pattern[i] == PF_FILL_L2) {
                    if (entry->data.pattern[i] != PF_FILL_L2) {
                        if (entry->data.pf_metadata[i] == 2) { 
                            entry->data.pf_metadata[i] = 3;    
                        }
                    }
                    entry->data.pattern[i] = PF_FILL_L2;
                }
            }
            Super::rp_promote(key);
        }
    } else {
        Super::insert(key, {pattern, trigger, second, third, std::vector<int>(step::NUM_BLOCKS, pf_metadata)});
        Super::rp_insert(key);
    }
}

void PrefetchBuffer::prefetch(CACHE* cache, uint64_t block_num, double prefetch_accuracy, uint32_t random_number) {
    uint64_t region_offset = __region_offset(block_num);
    uint64_t region_num = block_num >> (LOG2_REGION_SIZE - LOG2_BLOCK_SIZE);
    uint64_t key = this->build_key(region_num);
    auto entry = Super::find(key);
    if (!entry) {
        return;
    }
    Super::rp_promote(key);
    std::vector<int>& pattern = entry->data.pattern;
    auto pf_metadatas = entry->data.pf_metadata;
    uint32_t pf_metadata = 0;
    uint64_t trigger = entry->data.trigger;
    uint64_t second = entry->data.second;
    uint64_t third = entry->data.third;
    pattern[region_offset] = 0;
    uint8_t max_issue_num = 64;

    uint8_t issue_count = std::count_if(pattern.begin(), pattern.end(),
                                        [](int x) { return x != 0; });

    uint8_t issued_count = 0;

    for (uint64_t i = 1; i < (REGION_SIZE / BLOCK_SIZE); i++) {
        uint64_t pf_offset = ((uint64_t)region_offset + i) % (REGION_SIZE / BLOCK_SIZE);
        if (pf_offset != trigger && pf_offset != second && pf_offset != third && pattern[pf_offset] != 0) {
            uint64_t pf_addr = (region_num << LOG2_REGION_SIZE) + (pf_offset << LOG2_BLOCK_SIZE);
            // if prefetch is not 100 percent accurate, we then need to leave the demand request a slot
            if ((prefetch_accuracy<0.99)){
                if (cache->get_occupancy(3, 0) + cache->get_occupancy(0, 0) < cache->get_size(0, 0) - 1 && cache->get_occupancy(3, 0) < cache->get_size(3, 0)) {}
                else{
                    return;
                }
            }
            if (issued_count < max_issue_num){
                pf_metadata = pf_metadatas[pf_offset];
                if (pattern[pf_offset] == PF_FILL_L2) {
                    pf_metadata = __add_pf_dest_level(pf_metadata, 2);
                } else {
                    pf_metadata = __add_pf_dest_level(pf_metadata, 3);
                }
                bool fill_this_level = (pattern[pf_offset] == PF_FILL_L2);
                int ok = cache->prefetch_line(pf_addr, fill_this_level, pf_metadata);

                if (ok) {
                    pattern[pf_offset] = 0;
                } else {
                    return;
                }
                issued_count++;
            }
        }
    }
    Super::erase(key);
    return;
}

std::string PrefetchBuffer::log() {
    std::vector<std::string> headers({"RegionNum", "Trigger", "Second", "Third", "Meta", "Pattern"});
    return Super::log(headers);
}

void PrefetchBuffer::write_data(Entry& entry, custom_util::Table& table, int row) {
    uint64_t key = custom_util::hash_index(entry.key, this->index_len);
    table.set_cell(row, 0, key);
    table.set_cell(row, 1, entry.data.trigger);
    table.set_cell(row, 2, entry.data.second);
    table.set_cell(row, 3, entry.data.third);
    table.set_cell(row, 4, (uint64_t)entry.data.pf_metadata[0]);
    table.set_cell(row, 5, custom_util::pattern_to_string(entry.data.pattern));
}

uint64_t PrefetchBuffer::build_key(uint64_t region_num) {
    uint64_t key = region_num;
    return key;
}

// ------------------------- STEP functions ------------------------- //

STEP::STEP(int ft_size, int ft_ways, int at_size, int at_ways, 
           int pt_size, int pt_ways, int pb_size, int pb_ways, int cpu) 
    : cpu(cpu), one_accuracy_count(5,0), zero_accuracy_count(5,0), pc_offset_freq(8, 0){
    ft = std::make_unique<FilterTable>(ft_size, ft_ways);
    at = std::make_unique<AccumulateTable>(at_size, at_ways);
    pt = std::make_unique<PatternTable>(pt_size, pt_ways);
    pb = std::make_unique<PrefetchBuffer>(pb_size, pb_ways);
}

void STEP::access(CACHE* cache, uint64_t block_num, uint64_t pc) {
    update_accuracy_stats(cache);
    
    uint64_t region_num = block_num >> (LOG2_REGION_SIZE - LOG2_BLOCK_SIZE);
    uint64_t region_offset = __region_offset(block_num);
    auto at_entry = this->at->set_pattern(region_num, region_offset);

    if (at_entry) {
        // stride prefetching trigger
        if (at->get_stride_prefetch()) {
            int stride = at_entry->data.last_stride;
            int begin_offset = at_entry->data.last_offset;
            at_entry->data.last_offset = at_entry->data.last_stride = 0;
            std::vector<int> pattern(NUM_BLOCKS, 0);
            for (int i = 1; i <= stride_pf_degree; i++) {
                if (begin_offset + (i + STRIDE_PF_LOOKAHEAD) * stride < NUM_BLOCKS && begin_offset + (i + STRIDE_PF_LOOKAHEAD) * stride >= 0) {
                    if (!(at_entry->data.pattern[begin_offset + (i + STRIDE_PF_LOOKAHEAD) * stride]))
                        pattern[begin_offset + (i + STRIDE_PF_LOOKAHEAD) * stride] = PF_FILL_L2;
                }
            }
            if (at_entry->data.missed_in_pt){
                uint32_t pf_metadata = __add_pf_stride(0);
                pb->insert(region_num, pattern, begin_offset, begin_offset, begin_offset, pf_metadata);
            }
            else if (at_entry->data.con){
                uint32_t pf_metadata = __add_pf_stride(3);
                pb->insert(region_num, pattern, begin_offset, begin_offset, begin_offset, pf_metadata);
            }
            at->turn_off_stride_prefetch();
        }
        return;
    } else {
        auto entry = ft->find(region_num);

        // FOE
        if (!entry) {
            bool pattern_data_con = false;
            bool pattern_empty = true;
            auto [pt_entry,issue_finished] = find_in_pt(cache,region_offset, 64, 64, pc, region_num, cache->bw);
            if (pt_entry) {
                uint32_t pf_metadata = pt_entry->data.con ? 2 : 1;
                pattern_data_con = pt_entry->data.con;
    
                if(issue_finished == 2){
                    pf_metadata = __add_pf_first_offset(pf_metadata);   
                }
                pb->insert(region_num, pt_entry->data.pattern, region_offset, region_offset, region_offset, pf_metadata);
            }

            // ft update
            auto ft_victim = ft->insert(region_num, region_offset, pc);
            if (issue_finished == 2){
                auto new_ft_entry = ft->find(region_num);
                new_ft_entry->data.prefetch_issued = 1;
            }
            return;

        // SOE
        } else if (entry->data.trigger_offset != region_offset && entry->data.second_offset == 64) { // SECOND OFFSET
            ft->set_second_offset(region_num, region_offset);
            bool pattern_data_con = false;
            bool pattern_empty = true;
            auto [pt_entry,issue_finished] = find_in_pt(cache, entry->data.trigger_offset, region_offset, 64, pc, region_num, cache->bw);
            pattern_empty = (!pt_entry);
            bool all_set = pattern_empty ? false : pattern_all_set(pt_entry->data.pattern);

            if (pt_entry) {
                uint32_t pf_metadata = pt_entry->data.con ? 2 : 1;
                pattern_data_con = pt_entry->data.con;
                if (issue_finished == 1 && entry->data.prefetch_issued == 1){
                    // Intersection by FO, disable the SO Intersection
                }
                else{
                    // No Intersection FO + Intersection SO, prefetch the intersection
                    if(issue_finished == 1 && entry->data.prefetch_issued == 0 ){pf_metadata = __add_pf_second_offset(pf_metadata);}
                    // Intersection FO + PC+SO match, prefetch the whole entry
                    else if(issue_finished == 2){pf_metadata = __add_pf_second_offset(pf_metadata);}
                    else{printf("Error: Pattern should be empty");}
                    pb->insert(region_num, pt_entry->data.pattern, entry->data.trigger_offset, region_offset, 64, pf_metadata);
                    if (issue_finished == 2){
                        entry->data.prefetch_issued = 2;
                    }
                }
            }

        // TOE
        } else if (entry->data.trigger_offset != region_offset && entry->data.second_offset != region_offset) { 
            
            
            bool pattern_data_con = false;
            bool pattern_empty = true;
            if (entry->data.prefetch_issued != 2){
                auto [pt_entry,issue_finished] = find_in_pt(cache,entry->data.trigger_offset, entry->data.second_offset, region_offset, pc, region_num, cache->bw);
                pattern_empty = (!pt_entry) || (3 == std::count_if(pt_entry->data.pattern.begin(), pt_entry->data.pattern.end(), [](auto& x) { return x != 0; }));
                bool all_set = pattern_empty ? false : pattern_all_set(pt_entry->data.pattern);
                if (!pattern_empty) {
                    uint32_t pf_metadata = pt_entry->data.con ? 2 : 1;
                    pattern_data_con = pt_entry->data.con;
                    pf_metadata = __add_pf_third_offset(pf_metadata);
                    pb->insert(region_num, pt_entry->data.pattern, entry->data.trigger_offset, entry->data.second_offset, region_offset, pf_metadata);
                    if (issue_finished == 2){
                        entry->data.prefetch_issued = 3;
                    }
                }
            }
        
            // 2. insert into at
            auto at_victim = at->insert(region_num, entry->data.trigger_offset, entry->data.second_offset, region_offset, entry->data.pc, entry->data.prefetch_issued==0 | ((accuracy_fo < 0.5)&(entry->data.prefetch_issued==1)) | ((accuracy_so < 0.5)&(entry->data.prefetch_issued==2)), pattern_data_con);
            ft->erase(region_num);
            if (at_victim.valid) {
                insert_in_pt(at_victim, region_num, cache->current_cycle);
            }
        }
    }
}


void STEP::prefetch(CACHE* cache, uint64_t ip, uint64_t block_num) {
    // uint32_t random_number = randgen->getRandom();
    uint32_t random_number = 0;
    pb->prefetch(cache, block_num, prefetch_accuracy,random_number);
}


void STEP::log() {
    std::cout << "Filter table begin" << std::dec << std::endl;
    std::cout << this->ft->log();
    std::cout << "Filter table end" << std::endl;

    std::cout << "Accumulation table begin" << std::dec << std::endl;
    std::cout << this->at->log();
    std::cout << "Accumulation table end" << std::endl;

    // std::cout << "Pattern table begin" << std::dec << std::endl;
    // std::cout << this->pt->log();
    // std::cout << "Pattern table end" << std::endl;

    std::cout << "Prefetch buffer begin" << std::dec << std::endl;
    std::cout << this->pb->log();
    std::cout << "Prefetch buffer end" << std::endl;

}

PrefetchPrediction STEP::find_in_pt(CACHE* cache, uint64_t trigger, uint64_t second, uint64_t third, uint64_t pc, uint64_t region_num, int bw) {
    return pt->find(cache,trigger, second, third, pc, region_num, bw);
}

void STEP::insert_in_pt(const AccumulateTable::Entry& entry, uint64_t region_num, uint64_t current_cycle) {
    //std::cout << "[PT INSERT]"<< "RN:" << region_num << std::endl;
    //pt->log();
    uint64_t trigger = entry.data.trigger_offset, second = entry.data.second_offset, third = entry.data.third_offset, pc = entry.data.pc;
    pt->insert(trigger, second, third, pc, region_num, entry.data.pattern,current_cycle);
}

void STEP::set_warmup(bool warmup) {
    this->warmup = warmup;
    this->pb->warmup = warmup;
}

// ------------------------- util functions ------------------------- //
bool is_subset(const std::vector<bool>& pattern_a, const std::vector<bool>& pattern_b) {
    int false_counter = 0;
    for (size_t i = 0; i < pattern_a.size(); i++) {
        if (pattern_a[i] && !pattern_b[i]) {
            false_counter++;
            if (false_counter > SUBSET_THRESHOLD){
                return false;
            }
        }
    }
    return true;
}

void STEP::update_accuracy_stats(CACHE* cache){
    if (cache->current_cycle - cycle_prev >= ACCURACY_DETECT_INTERVAL){
        uint64_t period_useful_prefetches = cache->sim_stats.pf_useful - useful_prefetches;
        uint64_t period_useless_prefetches = cache->sim_stats.pf_useless - useless_prefetches;
        uint64_t period_useful_fo_prefetches = cache->sim_stats.pf_first_offset_useful - useful_fo_prefetches;
        uint64_t period_useless_fo_prefetches = cache->sim_stats.pf_first_offset_useless - useless_fo_prefetches;
        uint64_t period_useful_so_prefetches = cache->sim_stats.pf_second_offset_useful - useful_so_prefetches;
        uint64_t period_useless_so_prefetches = cache->sim_stats.pf_second_offset_useless - useless_so_prefetches;

        accuracy_fo = accuracy_calculation(period_useless_fo_prefetches,period_useful_fo_prefetches,0);
        accuracy_so = accuracy_calculation(period_useless_so_prefetches,period_useful_so_prefetches,1);
        prefetch_accuracy = accuracy_calculation(period_useless_prefetches,period_useful_prefetches,2);
       
        std::cout << "Accuracy of FO is : " << period_useful_fo_prefetches << "/" << (period_useless_fo_prefetches+period_useful_fo_prefetches) << "/" << accuracy_fo << std::endl;
        std::cout << "Accuracy  is : " << period_useful_prefetches << "/" << (period_useless_prefetches+period_useful_prefetches) << "/" << prefetch_accuracy << std::endl;
        cycle_prev = cache->current_cycle;
        useful_fo_prefetches = cache->sim_stats.pf_first_offset_useful;
        useless_fo_prefetches = cache->sim_stats.pf_first_offset_useless;
        useful_prefetches = cache->sim_stats.pf_useful;
        useless_prefetches = cache->sim_stats.pf_useless;
        useful_so_prefetches = cache->sim_stats.pf_second_offset_useful;
        useless_so_prefetches = cache->sim_stats.pf_second_offset_useless;
    }
}
double STEP::accuracy_calculation(uint64_t period_useless,uint64_t period_useful,uint64_t type){
    double accuracy = 0;
    if (period_useless+period_useful!=0){
            accuracy = static_cast<double> (period_useful) / (period_useless+period_useful);
            if (period_useless+period_useful > 50){

                if (accuracy >= 0.75){
                    if (this->one_accuracy_count[type] < 4){
                        this->one_accuracy_count[type] += 1;
                    }
                }
                else {
                    if (this->one_accuracy_count[type] > 0){
                        this->one_accuracy_count[type] -= 1;
                    }
                }
            }
            else{
                if (accuracy >= 0.75){
                    if (this->one_accuracy_count[type] < 4){
                        this->one_accuracy_count[type] += 1;
                    }
                    accuracy = 0.25*this->one_accuracy_count[type];
                }
                else if (accuracy > 0.25){
                    accuracy = 0.25;
                }
            }
    }
    else{
        accuracy = 0;
        if (this->one_accuracy_count[type] > 0){
            this->one_accuracy_count[type] -= 1;
        }
        if(this->zero_accuracy_count[type] == 100){
            accuracy = 0.25;
            this->zero_accuracy_count[type] = 0;
        }
        this->zero_accuracy_count[type] += 1;
    }
    return accuracy;
}

std::vector<int> pattern_bool2int(std::vector<bool> pattern) {
    std::vector<int> pattern_int(NUM_BLOCKS, 0);
    for (int i = 0; i < NUM_BLOCKS; i++)
        pattern_int[i] = (pattern[i] ? PF_FILL_L2 : 0);
    return pattern_int;
}

std::vector<bool> pattern_int2bool(std::vector<int> pattern) {
    std::vector<bool> pattern_bool(NUM_BLOCKS, false);
    for (int i = 0; i < NUM_BLOCKS; i++)
        pattern_bool[i] = (pattern[i] ? true : false);
    return pattern_bool;
}

bool pattern_all_set(std::vector<bool> pattern) {
    for (int i = 0; i < NUM_BLOCKS; i++)
        if (!pattern[i])
            return false;
    return true;
}

bool pattern_all_set(std::vector<int> pattern) {
    for (int i = 0; i < NUM_BLOCKS; i++)
        if (pattern[i] == 0)
            return false;
    return true;
}
} // namespace step

void CACHE::prefetcher_initialize() {
    std::cout << NAME << " STEP prefetcher" << std::endl;

    prefetchers.clear();
    prefetchers.reserve(NUM_CPUS);
    for (int i = 0; i < NUM_CPUS; ++i) {
        prefetchers.emplace_back(
            step::FT_SIZE, step::FT_WAY,
            step::AT_SIZE, step::AT_WAY,
            step::PT_SIZE, step::PT_WAY,
            step::PB_SIZE, step::PB_WAY,
            i);
    }
}

uint32_t CACHE::prefetcher_cache_operate(uint64_t addr, uint64_t ip, uint8_t cache_hit, uint8_t type, uint32_t metadata_in) {
    if (type != LOAD)
        return metadata_in;

    prefetchers[cpu].set_warmup(warmup);

    uint64_t block_num = addr >> LOG2_BLOCK_SIZE;
    prefetchers[cpu].access(this, block_num, ip);
    prefetchers[cpu].prefetch(this, ip, block_num);

    return metadata_in;
}

uint32_t CACHE::prefetcher_cache_fill(uint64_t addr, uint32_t set, uint32_t way, uint8_t prefetch, uint64_t evicted_addr, uint32_t metadata_in) {
    (void)addr;
    (void)set;
    (void)way;
    (void)prefetch;
    (void)evicted_addr;
    return metadata_in;
}

void CACHE::prefetcher_cache_eviction(uint64_t addr, uint64_t paddr) {
    (void)addr;
    (void)paddr;
}

void CACHE::prefetcher_cycle_operate() {}

void CACHE::prefetcher_final_stats() {
    prefetchers[cpu].log();
}
