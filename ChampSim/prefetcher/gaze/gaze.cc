#include "gaze.h"
#include "cache.h"

#include <assert.h>

/*
 * Gaze into the Pattern: Characterizing Spatial Patterns with Internal Temporal Correlations for Hardware Prefetching
 *
 * To appear in 31st IEEE International Symposium on High-Performance Computer Architecture (HPCA 2025),
 * 3/1/2025-3/5/2025, Las Vegas, NV, USA
 *
 * @Authors: Zixiao Chen, Chentao Wu, Yunfei Gu, Ranhao Jia, Jie Li, and Minyi Guo
 * @Manteiners: Zixiao Chen
 * @Email: chen_zx@sjtu.edu.cn
 * @Date: 12/02/2024
 */

static std::vector<gaze::Gaze> prefetchers;

namespace gaze {

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

void FilterTable::insert(uint64_t region_num, uint64_t trigger_offset, uint64_t pc) {
    uint64_t key = build_key(region_num);
    auto entry = Super::insert(key, {trigger_offset, pc});
    Super::rp_insert(key);
}

FilterTable::Entry* FilterTable::erase(uint64_t region_num) {
    uint64_t key = build_key(region_num);
    return Super::erase(key);
}

std::string FilterTable::log() {
    std::vector<std::string> headers({"RegionNum", "Trigger", "PC"});
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
    table.set_cell(row, 2, entry.data.pc);
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

AccumulateTable::Entry AccumulateTable::insert(uint64_t region_num, uint64_t trigger_offset, uint64_t second_offset, uint64_t pc, bool missed_in_pt, bool con) {
    uint64_t key = build_key(region_num);
    std::vector<bool> pattern(NUM_BLOCKS, false);
    std::vector<int> order(NUM_BLOCKS, 0);
    pattern[trigger_offset] = pattern[second_offset] = true;
    order[trigger_offset] = 1;
    order[second_offset] = 2;
    int last_stride = int(second_offset) - int(trigger_offset);
    Entry old_entry = Super::insert(key, {trigger_offset, second_offset, pc, missed_in_pt, pattern, order, last_stride, second_offset, con});
    Super::rp_insert(key);
    return old_entry;
}

AccumulateTable::Entry* AccumulateTable::erase(uint64_t region_num) {
    uint64_t key = build_key(region_num);
    return Super::erase(key);
}

std::string AccumulateTable::log() {
    std::vector<std::string> headers({"RegionNum", "Trigger", "Second", "PC", "Pattern", "Order"});
    return Super::log(headers);
}

void AccumulateTable::write_data(Entry& entry, custom_util::Table& table, int row) {
    uint64_t key = custom_util::hash_index(entry.key, this->index_len);
    table.set_cell(row, 0, key);
    table.set_cell(row, 1, entry.data.trigger_offset);
    table.set_cell(row, 2, entry.data.second_offset);
    table.set_cell(row, 3, entry.data.pc);
    table.set_cell(row, 4, custom_util::pattern_to_string(entry.data.pattern));
    table.set_cell(row, 5, custom_util::pattern_to_string(entry.data.order));
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

void PatternTable::insert(uint64_t trigger, uint64_t second, uint64_t pc, uint64_t region_num, std::vector<bool> pattern) {
    assert(pattern[trigger] && pattern[second]);
    bool all_set = pattern_all_set(pattern);

    if (trigger != 0 || second != 1) { // not spatial streaming
        uint64_t key = build_key(trigger, second, pc, region_num);
        Super::insert(key, {pattern_bool2int(pattern), pc});
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

PatternTable::Entry* PatternTable::find(uint64_t trigger, uint64_t second, uint64_t pc, uint64_t region_num) {
    if (trigger != 0 || second != 1) { // not ss
        uint64_t key = build_key(trigger, second, pc, region_num);
        return Super::find(key);
    } else {
        uint64_t hashed_pc = custom_util::my_hash_index(pc, LOG2_BLOCK_SIZE, 8);

        if (con_counter == 8 || con_pc.end() != std::find_if(con_pc.begin(), con_pc.end(), [hashed_pc](auto& x) { return x == hashed_pc; })) {
            Entry* ret = new Entry();
            ret->data.con = true;
            for (int i = 0; i < NUM_BLOCKS / 4; i++) {
                //ret->data.pattern[i] = PF_FILL_L1;
                ret->data.pattern[i] = PF_FILL_L2;
            }
            for (int i = NUM_BLOCKS / 4; i < NUM_BLOCKS; i++) {
                ret->data.pattern[i] = PF_FILL_L2;
            }
            return ret;
        } else if (con_counter > 2) {
            Entry* ret = new Entry();
            ret->data.con = true;
            for (int i = 0; i < NUM_BLOCKS / 4; i++) {
                ret->data.pattern[i] = PF_FILL_L2;
            }
            return ret;
        }
        return nullptr;
    }
    assert(0);
}

std::string PatternTable::log() {
    std::vector<std::string> headers({"Trigger", "Second", "Pattern"});
    return Super::log(headers);
}

void PatternTable::write_data(Entry& entry, custom_util::Table& table, int row) {
    table.set_cell(row, 0, int(entry.key & uint64_t((1ULL << this->index_len) - 1)));
    table.set_cell(row, 1, int((entry.key >> this->index_len) & ((1ULL << this->index_len) - 1)));
    table.set_cell(row, 2, custom_util::pattern_to_string(entry.data.pattern));
}

uint64_t PatternTable::build_key(uint64_t trigger, uint64_t second, uint64_t pc, uint64_t region_num) {
    assert(trigger >= 0 && trigger < NUM_BLOCKS && second >= 0 && second < NUM_BLOCKS);
    uint64_t key = (second << this->index_len) | trigger;
    return key;
}

// ------------------------- PB functions ------------------------- //
PrefetchBuffer::PrefetchBuffer(int size, int pattern_len, int debug_level = 0, int num_ways = 16) :
    Super(size, num_ways), pattern_len(pattern_len) {
}

void PrefetchBuffer::insert(uint64_t region_num, std::vector<int> pattern, uint64_t trigger, uint64_t second, uint32_t pf_metadata) {
    uint64_t key = this->build_key(region_num);
    if ((pf_metadata & 3) == 0 || (pf_metadata & 3) == 3) { // stride & promote
        auto entry = find(key);
        if (!entry) {
            Super::insert(key, {pattern, trigger, trigger, std::vector<int>(gaze::NUM_BLOCKS, pf_metadata)});
            Super::rp_insert(key);
        } else {
            for (int i = 0; i < NUM_BLOCKS; i++) {
                if (pattern[i] == PF_FILL_L1) {
                    if (entry->data.pattern[i] != PF_FILL_L1) {
                        if (entry->data.pf_metadata[i] == 2) { 
                            entry->data.pf_metadata[i] = 3;    
                        }
                    }
                    entry->data.pattern[i] = PF_FILL_L1;
                }
            }
            Super::rp_promote(key);
        }
    } else { // con and dis
        Super::insert(key, {pattern, trigger, second, std::vector<int>(gaze::NUM_BLOCKS, pf_metadata)});
        Super::rp_insert(key);
    }
}

void PrefetchBuffer::prefetch(CACHE* cache, uint64_t block_num) {
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
    pattern[region_offset] = 0;
    for (uint64_t i = 1; i < (REGION_SIZE / BLOCK_SIZE); i++) {
        uint64_t pf_offset = ((uint64_t)region_offset + i) % (REGION_SIZE / BLOCK_SIZE);
        if (pf_offset != trigger && pf_offset != second && pattern[pf_offset] != 0) {
            uint64_t pf_addr = (region_num << LOG2_REGION_SIZE) + (pf_offset << LOG2_BLOCK_SIZE);
            if (cache->get_occupancy(3, 0) + cache->get_occupancy(0, 0) < cache->get_size(0, 0) - 1 && cache->get_occupancy(3, 0) < cache->get_size(3, 0)) {
                pf_metadata = pf_metadatas[pf_offset];
                pf_metadata = __add_pf_sour_level(pf_metadata, 2);
                if (pattern[pf_offset] == PF_FILL_L1) {
                    pf_metadata = __add_pf_dest_level(pf_metadata, 1);
                } else {
                    pf_metadata = __add_pf_dest_level(pf_metadata, 2);
                }
                int ok = cache->prefetch_line(pf_addr, pattern[pf_offset] == PF_FILL_L2 ? true : false, pf_metadata);

                if (ok) {
                    pattern[pf_offset] = 0;
                }
            } else {
                return;
            }
        }
    }
    Super::erase(key);
    return;
}

std::string PrefetchBuffer::log() {
    std::vector<std::string> headers({"RegionNum", "Trigger", "Second", "Meta", "Pattern"});
    return Super::log(headers);
}

void PrefetchBuffer::write_data(Entry& entry, custom_util::Table& table, int row) {
    uint64_t key = custom_util::hash_index(entry.key, this->index_len);
    table.set_cell(row, 0, key);
    table.set_cell(row, 1, entry.data.trigger);
    table.set_cell(row, 2, entry.data.second);
    table.set_cell(row, 3, (uint64_t)entry.data.pf_metadata[0]);
    table.set_cell(row, 4, custom_util::pattern_to_string(entry.data.pattern));
}

uint64_t PrefetchBuffer::build_key(uint64_t region_num) {
    uint64_t key = region_num;
    return key;
}

// ------------------------- Gaze functions ------------------------- //

Gaze::Gaze(int ft_size, int ft_ways, int at_size, int at_ways, int pt_size, int pt_ways, int pb_size, int pb_ways, int cpu = 0) :
    ft(ft_size, ft_ways), at(at_size, at_ways), pt(pt_size, pt_ways), pb(pb_size, pb_ways), cpu(cpu) {
}

void Gaze::access(uint64_t block_num, uint64_t pc, CACHE* cache) {
    uint64_t region_num = block_num >> (LOG2_REGION_SIZE - LOG2_BLOCK_SIZE);
    uint64_t region_offset = __region_offset(block_num);
    auto at_entry = this->at.set_pattern(region_num, region_offset);
    if (at_entry) {
        if (at.get_stride_prefetch()) {
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
            if (at_entry->data.missed_in_pt)
                pb.insert(region_num, pattern, begin_offset, begin_offset, 0);
            else if (at_entry->data.con)
                pb.insert(region_num, pattern, begin_offset, begin_offset, 3);
            at.turn_off_stride_prefetch();
        }
        return;
    } else {
        auto entry = ft.find(region_num);
        if (!entry) {
            ft.insert(region_num, region_offset, pc);
            return;
        } else if (entry->data.trigger_offset != region_offset) { // SECOND OFFSET
            // 1. find pattern
            auto pt_entry = find_in_pt(entry->data.trigger_offset, region_offset, pc, region_num);
            // pattern empty?
            bool pattern_empty = (!pt_entry) || (2 == std::count_if(pt_entry->data.pattern.begin(), pt_entry->data.pattern.end(), [](auto& x) { return x != 0; }));
            bool all_set = pattern_empty ? false : pattern_all_set(pt_entry->data.pattern);
            
            cache->sim_stats.total_trigger++;
            if (pt_entry){
                cache->sim_stats.pht_trigger++;
            }
            if (!pattern_empty) {
                // cache->sim_stats.pht_trigger++;
                uint32_t pf_metadata = pt_entry->data.con ? 2 : 1;
                pb.insert(region_num, pt_entry->data.pattern, entry->data.trigger_offset, region_offset, pf_metadata);
            }

            // 2. insert into at
            auto at_victim = at.insert(region_num, entry->data.trigger_offset, region_offset, entry->data.pc, pattern_empty, (!pattern_empty) && pt_entry->data.con);
            ft.erase(region_num);
            if (at_victim.valid) {
                insert_in_pt(at_victim, region_num);
            }
        }
    }
}

void Gaze::eviction(uint64_t block_num) {
    uint64_t region_num = block_num >> (LOG2_REGION_SIZE - LOG2_BLOCK_SIZE);
    ft.erase(region_num);
    auto entry = at.erase(region_num);
    if (entry) {
        insert_in_pt(*entry, region_num);
    }
}

void Gaze::prefetch(CACHE* cache, uint64_t block_num) {
    pb.prefetch(cache, block_num);
}

void Gaze::log() {
    std::cout << "Filter table begin" << std::dec << std::endl;
    std::cout << this->ft.log();
    std::cout << "Filter table end" << std::endl;

    std::cout << "Accumulation table begin" << std::dec << std::endl;
    std::cout << this->at.log();
    std::cout << "Accumulation table end" << std::endl;

    std::cout << "Pattern table begin" << std::dec << std::endl;
    std::cout << this->pt.log();
    std::cout << "Pattern table end" << std::endl;

    std::cout << "Prefetch buffer begin" << std::dec << std::endl;
    std::cout << this->pb.log();
    std::cout << "Prefetch buffer end" << std::endl;
}

void Gaze::tune_stride_degree(CACHE* cache) {}

PatternTable::Entry* Gaze::find_in_pt(uint64_t trigger, uint64_t second, uint64_t pc, uint64_t region_num) {
    auto entry = pt.find(trigger, second, pc, region_num);
    if (!entry) {
        return entry;
    } else {
        return entry;
    }
}

void Gaze::insert_in_pt(const AccumulateTable::Entry& entry, uint64_t region_num) {
    uint64_t trigger = entry.data.trigger_offset, second = entry.data.second_offset, pc = entry.data.pc;
    pt.insert(trigger, second, pc, region_num, entry.data.pattern);
}

void Gaze::set_warmup(bool warmup) {
    this->warmup = warmup;
    this->pb.warmup = warmup;
}

// ------------------------- util functions ------------------------- //
std::pair<float, float> calculate_acc_and_cov(std::vector<int> pattern_1, std::vector<int> pattern_2) {
    uint64_t num_bits_1 = 0, num_bits_2 = 0, num_same = 0;

    for (int i = 0; i < NUM_BLOCKS; i++) {
        if (pattern_1[i] != 0)
            num_bits_1++;
        if (pattern_2[i] != 0)
            num_bits_2++;
        if (pattern_1[i] != 0 || pattern_2[i] != 0) {
            if (pattern_1[i] != 0 && pattern_2[i] != 0)
                num_same++;
        }
    }

    return {(float)num_same / num_bits_1, (float)num_same / num_bits_2};
}

bool different_patterns(std::vector<int> pattern_1, std::vector<int> pattern_2) {
    auto [acc, cov] = calculate_acc_and_cov(pattern_1, pattern_2);
    if (cov < 0.25)
        return true;
    return false;
}

std::vector<int> pattern_bool2int(std::vector<bool> pattern) {
    std::vector<int> pattern_int(NUM_BLOCKS, 0);
    for (int i = 0; i < NUM_BLOCKS; i++)
        pattern_int[i] = (pattern[i] ? PF_FILL_L2 : 0);
    return pattern_int;
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
} // namespace gaze

void CACHE::prefetcher_initialize() {
    std::cout << NAME << " Gaze NEW NEW prefetcher" << std::endl;

    prefetchers = std::vector<gaze::Gaze>(NUM_CPUS, gaze::Gaze(gaze::FT_SIZE, gaze::FT_WAY, gaze::AT_SIZE, gaze::AT_WAY, gaze::PT_SIZE, gaze::PT_WAY, gaze::PB_SIZE, gaze::PB_WAY, cpu));
}

uint32_t CACHE::prefetcher_cache_operate(uint64_t addr, uint64_t ip, uint8_t cache_hit, uint8_t type, uint32_t metadata_in) {
    uint64_t line_addr = (addr >> LOG2_BLOCK_SIZE); 
    uint64_t region_num = (addr >> LOG2_PAGE_SIZE);
    int offset = line_addr % gaze::NUM_BLOCKS;

    prefetchers[cpu].set_warmup(warmup);

    if (type != LOAD)
        return metadata_in;
    uint64_t block_num = addr >> LOG2_BLOCK_SIZE;
    prefetchers[cpu].access(block_num, ip, this);
    prefetchers[cpu].prefetch(this, block_num);

    return metadata_in;
}

uint32_t CACHE::prefetcher_cache_fill(uint64_t addr, uint32_t set, uint32_t way, uint8_t prefetch, uint64_t evicted_addr, uint32_t metadata_in) {
    uint64_t evicted_block_num = evicted_addr >> LOG2_BLOCK_SIZE;

    return metadata_in;
}

void CACHE::prefetcher_cycle_operate() {}

void CACHE::prefetcher_cache_eviction(uint64_t addr, uint64_t paddr) {}

void CACHE::prefetcher_final_stats() {
    prefetchers[cpu].log();
}