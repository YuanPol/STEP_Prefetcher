#ifndef BINGO_H
#define BINGO_H

/* Bingo [https://mshakerinava.github.io/papers/bingo-hpca19.pdf] */

#include "cache.h"
#include "custom_util.h"

#include <algorithm>
#include <bits/stdc++.h>
#include <deque>
#include <math.h>
#include <sstream>
#include <unordered_map>
#include <vector>

namespace bingo_pb {

constexpr int REGION_SIZE = 2 * 1024;
constexpr int LOG2_REGION_SIZE = 11;
constexpr int MIN_ADDR_WIDTH = 5;
constexpr int MAX_ADDR_WIDTH = 16;
constexpr int PC_WIDTH = 16;
#ifndef BINGO_PHT_SIZE
#define BINGO_PHT_SIZE (16 * 64)
#endif
constexpr int PHT_SIZE = BINGO_PHT_SIZE;
constexpr int PHT_WAY = 16;
constexpr int FT_SIZE = 64;
constexpr int FT_WAY = 8;
constexpr int AT_SIZE = 64;
constexpr int AT_WAY = 8;
constexpr int PB_SIZE = 32;
constexpr int PB_WAY = 8;

constexpr double L1D_THRESH = 0.2; /* from Bingo@HPCA19 */
constexpr double L2C_THRESH = 0.2; /* off */
constexpr double LLC_THRESH = 0.2; /* off */

constexpr int STRIDE_PF_LOOKAHEAD = 2;
constexpr int STREAMING_MAX_CONFIDENCE = 8;
constexpr int STREAMING_MID_CONFIDENCE = 2;
constexpr int STREAMING_PC_HISTORY = 8;
constexpr int STREAMING_PC_INDEX_BITS = LOG2_BLOCK_SIZE;
constexpr int STREAMING_PC_DISCARD_BITS = 8;

constexpr int FILL_L1 = 1;
constexpr int FILL_L2 = 2;  /* off */
constexpr int FILL_LLC = 3; /* off */

/* PC+Address matches are filled into L1 */
const int PC_ADDRESS_FILL_LEVEL = FILL_L1;

#define __region_offset(block_num) (block_num & REGION_OFFSET_MASK)

constexpr int NUM_BLOCKS = REGION_SIZE / BLOCK_SIZE;
constexpr uint64_t REGION_OFFSET_MASK = (1ULL << (LOG2_REGION_SIZE - LOG2_BLOCK_SIZE)) - 1;

template <class T>
inline T square(T x) { return x * x; }

inline bool pattern_all_set(const std::vector<bool>& pattern)
{
    return std::all_of(pattern.begin(), pattern.end(), [](bool bit) { return bit; });
}

inline bool pattern_has_prefetch(const std::vector<int>& pattern)
{
    return std::any_of(pattern.begin(), pattern.end(), [](int value) { return value != 0; });
}

class FilterTableData {
public:
    uint64_t pc = 0;
    int offset = 0;
    bool first_access_hit = false;
};

class FilterTable : public custom_util::LRUSetAssociativeCache<FilterTableData> {
    typedef custom_util::LRUSetAssociativeCache<FilterTableData> Super;

public:
    FilterTable(int size, int debug_level = 0, int num_ways = 16) :
        Super(size, num_ways, debug_level)
    {
    }

    Entry* find(uint64_t region_number)
    {
        uint64_t key = this->build_key(region_number);
        Entry* entry = Super::find(key);
        if (!entry)
            return nullptr;
        Super::set_mru(key);
        return entry;
    }

    void insert(uint64_t region_number, uint64_t pc, int offset, bool first_access_hit)
    {
        uint64_t key = this->build_key(region_number);
        Super::insert(key, {pc, offset, first_access_hit});
        Super::set_mru(key);
    }

    Entry* erase(uint64_t region_number)
    {
        uint64_t key = this->build_key(region_number);
        return Super::erase(key);
    }

    std::string log()
    {
        std::vector<std::string> headers({"Region", "PC", "Offset", "FirstHit"});
        return Super::log(headers);
    }

private:
    void write_data(Entry& entry, custom_util::Table& table, int row)
    {
        uint64_t key = custom_util::hash_index(entry.key, this->index_len);
        table.set_cell(row, 0, key);
        table.set_cell(row, 1, entry.data.pc);
        table.set_cell(row, 2, entry.data.offset);
        table.set_cell(row, 3, entry.data.first_access_hit);
    }

    uint64_t build_key(uint64_t region_number)
    {
        uint64_t key = region_number & ((1ULL << 37) - 1);
        return custom_util::hash_index(key, this->index_len);
    }
};

class AccumulationTableData {
public:
    uint64_t trigger_offset = 0;
    uint64_t second_offset = 0;
    uint64_t pc = 0;
    bool missed_in_pt = false;
    std::vector<bool> pattern;
    int last_stride = 0;
    uint64_t last_offset = 0;
    bool con = false;
    uint64_t region_number = 0;
};

class AccumulationTable : public custom_util::LRUSetAssociativeCache<AccumulationTableData> {
    typedef custom_util::LRUSetAssociativeCache<AccumulationTableData> Super;

private:
    bool stride_prefetch_ready = false;

public:
    AccumulationTable(int size, int pattern_len, int debug_level = 0, int num_ways = 16) :
        Super(size, num_ways, debug_level), pattern_len(pattern_len)
    {
    }

    Entry* set_pattern(uint64_t region_number, int offset)
    {
        uint64_t key = this->build_key(region_number);
        Entry* entry = Super::find(key);
        if (!entry)
            return nullptr;

        if (!entry->data.pattern[offset]) {
            int stride = int(offset) - int(entry->data.last_offset);
            if (entry->data.missed_in_pt || entry->data.con)
                this->stride_prefetch_ready = (stride == entry->data.last_stride);
            entry->data.pattern[offset] = true;
            entry->data.last_offset = offset;
            entry->data.last_stride = stride;
        }

        Super::set_mru(key);
        return entry;
    }

    Entry insert(uint64_t region_number, uint64_t trigger_offset, uint64_t second_offset, uint64_t pc, bool missed_in_pt, bool con)
    {
        uint64_t key = this->build_key(region_number);
        std::vector<bool> pattern(this->pattern_len, false);
        pattern[trigger_offset] = true;
        pattern[second_offset] = true;

        int last_stride = int(second_offset) - int(trigger_offset);
        Entry old_entry = Super::insert(key, {trigger_offset, second_offset, pc, missed_in_pt, pattern, last_stride, second_offset, con, region_number});
        Super::set_mru(key);
        return old_entry;
    }

    Entry* erase(uint64_t region_number)
    {
        uint64_t key = this->build_key(region_number);
        return Super::erase(key);
    }

    bool get_stride_prefetch() const
    {
        return this->stride_prefetch_ready;
    }

    void turn_off_stride_prefetch()
    {
        this->stride_prefetch_ready = false;
    }

    std::string log()
    {
        std::vector<std::string> headers({"Region", "PC", "Trigger", "Second", "MissPT", "Con", "Pattern"});
        return Super::log(headers);
    }

private:
    void write_data(Entry& entry, custom_util::Table& table, int row)
    {
        table.set_cell(row, 0, entry.data.region_number);
        table.set_cell(row, 1, entry.data.pc);
        table.set_cell(row, 2, entry.data.trigger_offset);
        table.set_cell(row, 3, entry.data.second_offset);
        table.set_cell(row, 4, entry.data.missed_in_pt);
        table.set_cell(row, 5, entry.data.con);
        table.set_cell(row, 6, custom_util::pattern_to_string(entry.data.pattern));
    }

    uint64_t build_key(uint64_t region_number)
    {
        uint64_t key = region_number & ((1ULL << 37) - 1);
        return custom_util::hash_index(key, this->index_len);
    }

    int pattern_len;
};

enum Event {
    PC_ADDRESS = 0,
    PC_OFFSET = 1,
    MISS = 2
};

class PatternHistoryTableData {
public:
    std::vector<bool> pattern;
};

class PatternHistoryTable : public custom_util::LRUSetAssociativeCache<PatternHistoryTableData> {
    typedef custom_util::LRUSetAssociativeCache<PatternHistoryTableData> Super;

public:
    PatternHistoryTable(int size, int pattern_len, int min_addr_width, int max_addr_width, int pc_width, int debug_level = 0, int num_ways = 16) :
        Super(size, num_ways, debug_level),
        pattern_len(pattern_len), min_addr_width(min_addr_width),
        max_addr_width(max_addr_width), pc_width(pc_width)
    {
    }

    /* NOTE: In BINGO, address is actually block number. */
    void insert(uint64_t pc, uint64_t trigger, uint64_t second, uint64_t address, std::vector<bool> pattern)
    {
        assert(pattern[trigger] && pattern[second]);

        int offset = address % this->pattern_len;
        std::vector<bool> rotated_pattern = custom_util::my_rotate(pattern, -offset);
        uint64_t key = this->build_key(pc, address);
        Super::insert(key, {rotated_pattern});
        Super::set_mru(key);

        if (trigger == 0 && second == 1)
            this->update_streaming_confidence(pc, pattern);
    }

    std::vector<std::vector<bool>> find(uint64_t pc, uint64_t address)
    {
        uint64_t key = this->build_key(pc, address);
        uint64_t index = key % this->num_sets;
        uint64_t tag = key / this->num_sets;
        auto& set = this->entries[index];
        uint64_t min_tag_mask = (1ULL << (this->pc_width + this->min_addr_width - this->index_len)) - 1;
        uint64_t max_tag_mask = (1ULL << (this->pc_width + this->max_addr_width - this->index_len)) - 1;

        std::vector<std::vector<bool>> matches;
        this->last_event = MISS;
        for (int i = 0; i < this->num_ways; i += 1) {
            if (!set[i].valid)
                continue;

            bool min_match = ((set[i].tag & min_tag_mask) == (tag & min_tag_mask));
            bool max_match = ((set[i].tag & max_tag_mask) == (tag & max_tag_mask));
            std::vector<bool>& cur_pattern = set[i].data.pattern;
            if (max_match) {
                this->last_event = PC_ADDRESS;
                Super::set_mru(set[i].key);
                matches.clear();
                matches.push_back(cur_pattern);
                break;
            }
            if (min_match) {
                this->last_event = PC_OFFSET;
                matches.push_back(cur_pattern);
            }
        }

        int offset = address % this->pattern_len;
        for (auto& match : matches)
            match = custom_util::my_rotate(match, +offset);
        return matches;
    }

    std::vector<int> find_streaming(uint64_t trigger, uint64_t second, uint64_t pc)
    {
        if (trigger != 0 || second != 1)
            return {};

        uint64_t hashed_pc = custom_util::my_hash_index(pc, STREAMING_PC_INDEX_BITS, STREAMING_PC_DISCARD_BITS);
        bool strong_stream = (this->con_counter == STREAMING_MAX_CONFIDENCE) || this->contains_streaming_pc(hashed_pc);
        bool weak_stream = this->con_counter > STREAMING_MID_CONFIDENCE;

        if (!strong_stream && !weak_stream)
            return {};

        std::vector<int> pattern(this->pattern_len, 0);
        int quarter_bound = std::max(this->pattern_len / 4, 2);
        if (strong_stream) {
            for (int i = 2; i < quarter_bound; i += 1)
                pattern[i] = FILL_L1;
            for (int i = quarter_bound; i < this->pattern_len; i += 1)
                pattern[i] = FILL_L2;
        } else {
            for (int i = 2; i < quarter_bound; i += 1)
                pattern[i] = FILL_L2;
        }

        if (!pattern_has_prefetch(pattern))
            return {};
        return pattern;
    }

    Event get_last_event() const
    {
        return this->last_event;
    }

    std::string log()
    {
        std::vector<std::string> headers({"PC", "Offset", "Address", "Pattern"});
        return Super::log(headers);
    }

private:
    void write_data(Entry& entry, custom_util::Table& table, int row)
    {
        uint64_t base_key = entry.key >> (this->pc_width + this->min_addr_width);
        uint64_t index_key = entry.key & ((1ULL << (this->pc_width + this->min_addr_width)) - 1);
        index_key = custom_util::hash_index(index_key, this->index_len); /* unhash */
        uint64_t key = (base_key << (this->pc_width + this->min_addr_width)) | index_key;

        uint64_t offset = key & ((1ULL << this->min_addr_width) - 1);
        key >>= this->min_addr_width;
        uint64_t pc = key & ((1ULL << this->pc_width) - 1);
        key >>= this->pc_width;
        uint64_t address = (key << this->min_addr_width) + offset;

        table.set_cell(row, 0, pc);
        table.set_cell(row, 1, offset);
        table.set_cell(row, 2, address);
        table.set_cell(row, 3, custom_util::pattern_to_string(entry.data.pattern));
    }

    uint64_t build_key(uint64_t pc, uint64_t address)
    {
        pc &= (1ULL << this->pc_width) - 1;
        address &= (1ULL << this->max_addr_width) - 1;
        uint64_t offset = address & ((1ULL << this->min_addr_width) - 1);
        uint64_t base = (address >> this->min_addr_width);
        uint64_t index_key = custom_util::hash_index((pc << this->min_addr_width) | offset, this->index_len);
        return (base << (this->pc_width + this->min_addr_width)) | index_key;
    }

    void update_streaming_confidence(uint64_t pc, const std::vector<bool>& pattern)
    {
        bool all_set = pattern_all_set(pattern);
        if (all_set) {
            if (this->con_counter < STREAMING_MAX_CONFIDENCE)
                this->con_counter++;

            uint64_t hashed_pc = custom_util::my_hash_index(pc, STREAMING_PC_INDEX_BITS, STREAMING_PC_DISCARD_BITS);
            auto it = std::find(this->con_pc.begin(), this->con_pc.end(), hashed_pc);
            if (it == this->con_pc.end()) {
                if (this->con_pc.size() == STREAMING_PC_HISTORY)
                    this->con_pc.pop_back();
                this->con_pc.push_front(hashed_pc);
            }
            return;
        }

        if (this->con_counter > STREAMING_MID_CONFIDENCE)
            this->con_counter >>= 1;
        else if (this->con_counter > 0)
            this->con_counter--;
    }

    bool contains_streaming_pc(uint64_t hashed_pc) const
    {
        return std::find(this->con_pc.begin(), this->con_pc.end(), hashed_pc) != this->con_pc.end();
    }

    int pattern_len;
    int min_addr_width, max_addr_width, pc_width;
    Event last_event = MISS;

    std::deque<uint64_t> con_pc;
    int con_counter = 0;
};

class PrefetchBufferData {
public:
    std::vector<int> pattern;
};

class PrefetchBuffer : public custom_util::LRUSetAssociativeCache<PrefetchBufferData> {
    typedef custom_util::LRUSetAssociativeCache<PrefetchBufferData> Super;

public:
    PrefetchBuffer(int size, int pattern_len, int debug_level = 0, int num_ways = 16) :
        Super(size, num_ways), pattern_len(pattern_len)
    {
        if (this->debug_level >= 1) {
            std::cerr << "PrefetchBuffer::PrefetchBuffer(size=" << size << ", pattern_len=" << pattern_len
                      << ", debug_level=" << debug_level << ", num_ways=" << num_ways << ")" << std::dec << std::endl;
        }
    }

    void insert(uint64_t region_number, const std::vector<int>& pattern)
    {
        if (this->debug_level >= 2) {
            std::cerr << "PrefetchBuffer::insert(region_number=0x" << std::hex << region_number
                      << ", pattern=" << custom_util::pattern_to_string(pattern) << ")" << std::dec << std::endl;
        }

        uint64_t key = this->build_key(region_number);
        Entry* entry = Super::find(key);
        if (!entry) {
            Super::insert(key, {pattern});
            Super::rp_insert(key);
            return;
        }

        for (int i = 0; i < this->pattern_len; i += 1) {
            int new_fill = pattern[i];
            if (new_fill == 0)
                continue;
            int& existing_fill = entry->data.pattern[i];
            if (existing_fill == 0)
                existing_fill = new_fill;
            else
                existing_fill = std::min(existing_fill, new_fill);
        }
        Super::rp_promote(key);
    }

    int prefetch(CACHE* cache, uint64_t block_num)
    {
        uint64_t base_addr = block_num << LOG2_BLOCK_SIZE;
        int region_offset = block_num % this->pattern_len;
        uint64_t region_number = block_num / this->pattern_len;
        uint64_t key = this->build_key(region_number);
        Entry* entry = Super::find(key);
        if (!entry)
            return 0;

        Super::set_mru(key);
        int pf_issued = 0;
        std::vector<int>& pattern = entry->data.pattern;
        pattern[region_offset] = 0;

        for (int d = 1; d < this->pattern_len; d += 1) {
            for (int sgn = +1; sgn >= -1; sgn -= 2) {
                int pf_offset = region_offset + sgn * d;
                if (pf_offset < 0 || pf_offset >= this->pattern_len || pattern[pf_offset] == 0)
                    continue;

                uint64_t pf_address = (region_number * this->pattern_len + pf_offset) << LOG2_BLOCK_SIZE;
                if (cache->get_occupancy(3, 0) + cache->get_occupancy(0, 0) >= cache->get_size(0, 0) - 1 ||
                    cache->get_occupancy(3, 0) >= cache->get_size(3, 0)) {
                    return pf_issued;
                }

                uint32_t pf_metadata = 0;
                pf_metadata = __add_pf_sour_level(pf_metadata, 1);
                if (pattern[pf_offset] == FILL_L1)
                    pf_metadata = __add_pf_dest_level(pf_metadata, 1);
                else
                    pf_metadata = __add_pf_dest_level(pf_metadata, 2);

                cache->prefetch_line(0, base_addr, pf_address, pattern[pf_offset] == FILL_L1, pf_metadata);
                pf_issued += 1;
                pattern[pf_offset] = 0;
            }
        }

        Super::erase(key);
        return pf_issued;
    }

    std::string log()
    {
        std::vector<std::string> headers({"Region", "Pattern"});
        return Super::log(headers);
    }

private:
    void write_data(Entry& entry, custom_util::Table& table, int row)
    {
        uint64_t key = custom_util::hash_index(entry.key, this->index_len);
        table.set_cell(row, 0, key);
        table.set_cell(row, 1, custom_util::pattern_to_string(entry.data.pattern));
    }

    uint64_t build_key(uint64_t region_number)
    {
        return custom_util::hash_index(region_number, this->index_len);
    }

    int pattern_len;
};

class Bingo {
public:
    Bingo(int pattern_len, int min_addr_width, int max_addr_width, int pc_width, int filter_table_size,
          int accumulation_table_size, int pht_size, int pht_ways, int pb_size, int pb_way, int debug_level = 0) :
        pattern_len(pattern_len),
        filter_table(filter_table_size, debug_level),
        accumulation_table(accumulation_table_size, pattern_len, debug_level),
        pht(pht_size, pattern_len, min_addr_width, max_addr_width, pc_width, debug_level, pht_ways),
        pf_buffer(pb_size, pattern_len, debug_level, pb_way)
    {
    }

    void access(uint64_t block_number, uint64_t pc)
    {
        uint64_t region_number = block_number / this->pattern_len;
        int region_offset = block_number % this->pattern_len;

        AccumulationTable::Entry* at_entry = this->accumulation_table.set_pattern(region_number, region_offset);
        if (at_entry) {
            this->issue_stride_prefetch(region_number, *at_entry);
            return;
        }

        FilterTable::Entry* entry = this->filter_table.find(region_number);
        if (!entry) {
            std::vector<int> pattern = this->find_in_phts(pc, block_number);
            bool first_access_hit = !pattern.empty();

            this->filter_table.insert(region_number, pc, region_offset, first_access_hit);
            if (first_access_hit)
                this->pf_buffer.insert(region_number, pattern);
            return;
        }

        if (entry->data.offset == region_offset)
            return;

        int trigger_offset = entry->data.offset;
        std::vector<int> streaming_pattern;
        if (!entry->data.first_access_hit)
            streaming_pattern = this->pht.find_streaming(trigger_offset, region_offset, pc);
        bool streaming_hit = !streaming_pattern.empty();
        if (streaming_hit)
            this->pf_buffer.insert(region_number, streaming_pattern);

        bool missed_in_pt = !entry->data.first_access_hit && !streaming_hit;
        AccumulationTable::Entry victim = this->accumulation_table.insert(region_number, trigger_offset, region_offset, entry->data.pc, missed_in_pt, streaming_hit);
        this->filter_table.erase(region_number);
        if (victim.valid)
            this->insert_in_phts(victim);
    }

    int prefetch(CACHE* cache, uint64_t block_number)
    {
        return this->pf_buffer.prefetch(cache, block_number);
    }

    void eviction(uint64_t block_number)
    {
        uint64_t region_number = block_number / this->pattern_len;
        this->filter_table.erase(region_number);
        AccumulationTable::Entry* entry = this->accumulation_table.erase(region_number);
        if (entry)
            this->insert_in_phts(*entry);
    }

    void set_debug_level(int debug_level)
    {
        this->debug_level = debug_level;
    }

    Event get_event(uint64_t block_number)
    {
        uint64_t region_number = block_number / this->pattern_len;
        return this->pht_events[region_number];
    }

    void add_prefetch(uint64_t block_number)
    {
        Event ev = this->get_event(block_number);
        this->prefetch_cnt[ev] += 1;
    }

    void reset_stats()
    {
        this->pht_access_cnt = 0;
        this->pht_pc_address_cnt = 0;
        this->pht_pc_offset_cnt = 0;
        this->pht_miss_cnt = 0;

        for (int i = 0; i < 2; i += 1) {
            this->prefetch_cnt[i] = 0;
            this->useful_cnt[i] = 0;
            this->useless_cnt[i] = 0;
        }

        this->pref_level_cnt.clear();
        this->region_pref_cnt = 0;

        this->voter_sum = 0;
        this->vote_cnt = 0;
        this->voter_sqr_sum = 0;
    }

    uint64_t get_prefetch_cnt(Event ev)
    {
        return this->prefetch_cnt[ev];
    }

    void log()
    {
        std::cerr << "Filter table begin" << std::dec << std::endl;
        std::cerr << this->filter_table.log();
        std::cerr << "Filter table end" << std::endl;

        std::cerr << "Accumulation table begin" << std::dec << std::endl;
        std::cerr << this->accumulation_table.log();
        std::cerr << "Accumulation table end" << std::endl;

        std::cerr << "PHT table begin" << std::dec << std::endl;
        std::cerr << this->pht.log();
        std::cerr << "PHT table end" << std::endl;

        std::cerr << "Prefetch buffer begin" << std::dec << std::endl;
        std::cerr << this->pf_buffer.log();
        std::cerr << "Prefetch buffer end" << std::endl;
    }

private:
    void issue_stride_prefetch(uint64_t region_number, AccumulationTable::Entry& at_entry)
    {
        if (!this->accumulation_table.get_stride_prefetch())
            return;

        int stride = at_entry.data.last_stride;
        int begin_offset = static_cast<int>(at_entry.data.last_offset);
        at_entry.data.last_offset = 0;
        at_entry.data.last_stride = 0;

        std::vector<int> pattern(this->pattern_len, 0);
        for (int i = 1; i <= this->stride_pf_degree; i += 1) {
            int pf_offset = begin_offset + (i + STRIDE_PF_LOOKAHEAD) * stride;
            if (pf_offset < 0 || pf_offset >= this->pattern_len)
                continue;
            if (!at_entry.data.pattern[pf_offset])
                pattern[pf_offset] = FILL_L1;
        }

        if (pattern_has_prefetch(pattern))
            this->pf_buffer.insert(region_number, pattern);

        this->accumulation_table.turn_off_stride_prefetch();
    }

    std::vector<int> find_in_phts(uint64_t pc, uint64_t address)
    {
        if (this->debug_level >= 1)
            std::cerr << "[Bingo] find_in_phts(pc=" << pc << ", address=" << address << ")" << std::endl;

        std::vector<std::vector<bool>> matches = this->pht.find(pc, address);
        this->pht_access_cnt += 1;
        Event pht_last_event = this->pht.get_last_event();
        uint64_t region_number = address / this->pattern_len;
        if (pht_last_event != MISS)
            this->pht_events[region_number] = pht_last_event;

        std::vector<int> pattern;
        if (pht_last_event == PC_ADDRESS) {
            this->pht_pc_address_cnt += 1;
            pattern.resize(this->pattern_len, 0);
            for (int i = 0; i < this->pattern_len; i += 1)
                if (matches[0][i])
                    pattern[i] = PC_ADDRESS_FILL_LEVEL;
        } else if (pht_last_event == PC_OFFSET) {
            this->pht_pc_offset_cnt += 1;
            pattern = this->vote(matches);
        } else if (pht_last_event == MISS) {
            this->pht_miss_cnt += 1;
        }

        if (pht_last_event != MISS) {
            this->region_pref_cnt += 1;
            for (int value : pattern)
                if (value != 0)
                    this->pref_level_cnt[value] += 1;
        }

        return pattern;
    }

    void insert_in_phts(const AccumulationTable::Entry& entry)
    {
        if (this->debug_level >= 1)
            std::cerr << "[Bingo] insert_in_phts(...)" << std::endl;

        uint64_t pc = entry.data.pc;
        uint64_t trigger = entry.data.trigger_offset;
        uint64_t second = entry.data.second_offset;
        uint64_t address = entry.data.region_number * this->pattern_len + trigger;
        this->pht.insert(pc, trigger, second, address, entry.data.pattern);
    }

    std::vector<int> vote(const std::vector<std::vector<bool>>& x)
    {
        int n = x.size();
        if (n == 0)
            return {};

        this->vote_cnt += 1;
        this->voter_sum += n;
        this->voter_sqr_sum += square(n);

        bool pf_flag = false;
        std::vector<int> res(this->pattern_len, 0);
        for (int i = 0; i < this->pattern_len; i += 1) {
            int cnt = 0;
            for (int j = 0; j < n; j += 1)
                if (x[j][i])
                    cnt += 1;

            double p = 1.0 * cnt / n;
            if (p >= L1D_THRESH)
                res[i] = FILL_L1;
            else if (p >= L2C_THRESH)
                res[i] = FILL_L2;
            else if (p >= LLC_THRESH)
                res[i] = FILL_LLC;
            else
                res[i] = 0;

            if (res[i] != 0)
                pf_flag = true;
        }

        if (!pf_flag)
            return {};
        return res;
    }

    int stride_pf_degree = 4;
    int pattern_len;
    FilterTable filter_table;
    AccumulationTable accumulation_table;
    PatternHistoryTable pht;
    PrefetchBuffer pf_buffer;
    int debug_level = 0;

    std::unordered_map<uint64_t, Event> pht_events;

    uint64_t pht_access_cnt = 0;
    uint64_t pht_pc_address_cnt = 0;
    uint64_t pht_pc_offset_cnt = 0;
    uint64_t pht_miss_cnt = 0;

    uint64_t prefetch_cnt[2] = {0};
    uint64_t useful_cnt[2] = {0};
    uint64_t useless_cnt[2] = {0};

    std::unordered_map<int, uint64_t> pref_level_cnt;
    uint64_t region_pref_cnt = 0;

    uint64_t vote_cnt = 0;
    uint64_t voter_sum = 0;
    uint64_t voter_sqr_sum = 0;
};

} // namespace bingo_pb

#endif
