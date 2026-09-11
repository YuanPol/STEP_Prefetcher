#ifndef BINGO_H
#define BINGO_H

/* Bingo [https://mshakerinava.github.io/papers/bingo-hpca19.pdf] */

#include "cache.h"
#include "custom_util.h"

#include <vector>
#include <bits/stdc++.h>
#include <unordered_map>
#include <sstream>
#include <algorithm>
#include <math.h>

namespace bingo_pb {

constexpr int REGION_SIZE = 2 * 1024;
constexpr int LOG2_REGION_SIZE = 11;
constexpr int MIN_ADDR_WIDTH = 5;
constexpr int MAX_ADDR_WIDTH = 16;
constexpr int PC_WIDTH = 16;
#ifndef BINGO_PHT_SIZE
#define BINGO_PHT_SIZE (16 * 1024)
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

class FilterTableData {
public:
    uint64_t pc;
    int offset;
};

class FilterTable : public custom_util::LRUSetAssociativeCache<FilterTableData> {
    typedef custom_util::LRUSetAssociativeCache<FilterTableData> Super;

public:
    FilterTable(int size, int debug_level = 0, int num_ways = 16) :
        Super(size, num_ways, debug_level) {
        // assert(__builtin_popcount(size) == 1);
    }

    Entry* find(uint64_t region_number) {
        uint64_t key = this->build_key(region_number);
        Entry* entry = Super::find(key);
        if (!entry) {
            return nullptr;
        }
        Super::set_mru(key);
        return entry;
    }

    void insert(uint64_t region_number, uint64_t pc, int offset) {
        uint64_t key = this->build_key(region_number);
        // assert(!Super::find(key));
        Super::insert(key, {pc, offset});
        Super::set_mru(key);
    }

    Entry* erase(uint64_t region_number) {
        uint64_t key = this->build_key(region_number);
        return Super::erase(key);
    }

    std::string log() {
        std::vector<std::string> headers({"Region", "PC", "Offset"});
        return Super::log(headers);
    }

private:
    /* @override */
    void write_data(Entry& entry, custom_util::Table& table, int row) {
        uint64_t key = custom_util::hash_index(entry.key, this->index_len);
        table.set_cell(row, 0, key);
        table.set_cell(row, 1, entry.data.pc);
        table.set_cell(row, 2, entry.data.offset);
    }

    uint64_t build_key(uint64_t region_number) {
        uint64_t key = region_number & ((1ULL << 37) - 1);
        return custom_util::hash_index(key, this->index_len);
    }

    /*==========================================================*/
    /* Entry   = [tag, offset, PC, valid, LRU]                  */
    /* Storage = size * (37 - lg(sets) + 5 + 16 + 1 + lg(ways)) */
    /* 64 * (37 - lg(4) + 5 + 16 + 1 + lg(16)) = 488 Bytes      */
    /*==========================================================*/
};

class AccumulationTableData {
public:
    uint64_t pc;
    int offset;
    std::vector<bool> pattern;
};

class AccumulationTable : public custom_util::LRUSetAssociativeCache<AccumulationTableData> {
    typedef custom_util::LRUSetAssociativeCache<AccumulationTableData> Super;

public:
    AccumulationTable(int size, int pattern_len, int debug_level = 0, int num_ways = 16) :
        Super(size, num_ways, debug_level), pattern_len(pattern_len) {
        // assert(__builtin_popcount(size) == 1);
        // assert(__builtin_popcount(pattern_len) == 1);
    }

    /**
     * @return False if the tag wasn't found and true if the pattern bit was successfully set
     */
    bool set_pattern(uint64_t region_number, int offset) {
        uint64_t key = this->build_key(region_number);
        Entry* entry = Super::find(key);
        if (!entry) {
            return false;
        }
        entry->data.pattern[offset] = true;
        Super::set_mru(key);
        return true;
    }

    /* NOTE: `region_number` is probably truncated since it comes from the filter table */
    Entry insert(uint64_t region_number, uint64_t pc, int offset) {
        uint64_t key = this->build_key(region_number);
        // assert(!Super::find(key));
        std::vector<bool> pattern(this->pattern_len, false);
        pattern[offset] = true;
        Entry old_entry = Super::insert(key, {pc, offset, pattern});
        Super::set_mru(key);
        return old_entry;
    }

    Entry* erase(uint64_t region_number) {
        uint64_t key = this->build_key(region_number);
        return Super::erase(key);
    }

    std::string log() {
        std::vector<std::string> headers({"Region", "PC", "Offset", "Pattern"});
        return Super::log(headers);
    }

private:
    /* @override */
    void write_data(Entry& entry, custom_util::Table& table, int row) {
        uint64_t key = custom_util::hash_index(entry.key, this->index_len);
        table.set_cell(row, 0, key);
        table.set_cell(row, 1, entry.data.pc);
        table.set_cell(row, 2, entry.data.offset);
        table.set_cell(row, 3, custom_util::pattern_to_string(entry.data.pattern));
    }

    uint64_t build_key(uint64_t region_number) {
        uint64_t key = region_number & ((1ULL << 37) - 1);
        return custom_util::hash_index(key, this->index_len);
    }

    int pattern_len;

    /*===============================================================*/
    /* Entry   = [tag, map, offset, PC, valid, LRU]                  */
    /* Storage = size * (37 - lg(sets) + 32 + 5 + 16 + 1 + lg(ways)) */
    /* 128 * (37 - lg(8) + 32 + 5 + 16 + 1 + lg(16)) = 1472 Bytes    */
    /*===============================================================*/
};

enum Event { PC_ADDRESS = 0,
             PC_OFFSET = 1,
             MISS = 2 };

class PatternHistoryTableData {
public:
    std::vector<bool> pattern;
};

class PatternHistoryTable : public custom_util::LRUSetAssociativeCache<PatternHistoryTableData> {
    typedef custom_util::LRUSetAssociativeCache<PatternHistoryTableData> Super;

public:
    PatternHistoryTable(int size, int pattern_len, int min_addr_width, int max_addr_width, int pc_width,
                        int debug_level = 0, int num_ways = 16) :
        Super(size, num_ways, debug_level),
        pattern_len(pattern_len), min_addr_width(min_addr_width),
        max_addr_width(max_addr_width), pc_width(pc_width) {
    }

    /* NOTE: In BINGO, address is actually block number. */
    void insert(uint64_t pc, uint64_t address, std::vector<bool> pattern) {
        // assert((int)pattern.size() == this->pattern_len);
        int offset = address % this->pattern_len;
        pattern = custom_util::my_rotate(pattern, -offset);
        uint64_t key = this->build_key(pc, address);
        Super::insert(key, {pattern});
        Super::set_mru(key);
    }

    /**
     * First searches for a PC+Address match. If no match is found, returns all PC+Offset matches.
     * @return All un-rotated patterns if matches were found, returns an empty vector otherwise
     */
    std::vector<std::vector<bool>> find(uint64_t pc, uint64_t address) {
        uint64_t key = this->build_key(pc, address);
        uint64_t index = key % this->num_sets;
        uint64_t tag = key / this->num_sets;
        auto& set = this->entries[index];
        uint64_t min_tag_mask = (1 << (this->pc_width + this->min_addr_width - this->index_len)) - 1;
        uint64_t max_tag_mask = (1 << (this->pc_width + this->max_addr_width - this->index_len)) - 1;
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
        for (int i = 0; i < (int)matches.size(); i += 1)
            matches[i] = custom_util::my_rotate(matches[i], +offset);
        return matches;
    }

    Event get_last_event() { return this->last_event; }

    std::string log() {
        std::vector<std::string> headers({"PC", "Offset", "Address", "Pattern"});
        return Super::log(headers);
    }

private:
    /* @override */
    void write_data(Entry& entry, custom_util::Table& table, int row) {
        uint64_t base_key = entry.key >> (this->pc_width + this->min_addr_width);
        uint64_t index_key = entry.key & ((1 << (this->pc_width + this->min_addr_width)) - 1);
        index_key = custom_util::hash_index(index_key, this->index_len); /* unhash */
        uint64_t key = (base_key << (this->pc_width + this->min_addr_width)) | index_key;

        /* extract PC, offset, and address */
        uint64_t offset = key & ((1 << this->min_addr_width) - 1);
        key >>= this->min_addr_width;
        uint64_t pc = key & ((1 << this->pc_width) - 1);
        key >>= this->pc_width;
        uint64_t address = (key << this->min_addr_width) + offset;

        table.set_cell(row, 0, pc);
        table.set_cell(row, 1, offset);
        table.set_cell(row, 2, address);
        table.set_cell(row, 3, custom_util::pattern_to_string(entry.data.pattern));
    }

    uint64_t build_key(uint64_t pc, uint64_t address) {
        pc &= (1 << this->pc_width) - 1;            /* use `pc_width` bits from pc */
        address &= (1 << this->max_addr_width) - 1; /* use `addr_width` bits from address */
        uint64_t offset = address & ((1 << this->min_addr_width) - 1);
        uint64_t base = (address >> this->min_addr_width);
        /* key = base + hash_index( pc + offset )
         * The index must be computed from only PC+Offset to ensure that all entries with the same
         * PC+Offset end up in the same set */
        uint64_t index_key = custom_util::hash_index((pc << this->min_addr_width) | offset, this->index_len);
        uint64_t key = (base << (this->pc_width + this->min_addr_width)) | index_key;
        return key;
    }

    int pattern_len;
    int min_addr_width, max_addr_width, pc_width;
    Event last_event;

    /*======================================================*/
    /* Entry   = [tag, map, valid, LRU]                     */
    /* Storage = size * (32 - lg(sets) + 32 + 1 + lg(ways)) */
    /* 8K * (32 - lg(512) + 32 + 1 + lg(16)) = 60K Bytes    */
    /*======================================================*/
};

class PrefetchBufferData {
public:
    std::vector<int> pattern;
};

class PrefetchBuffer : public custom_util::LRUSetAssociativeCache<PrefetchBufferData> {
    typedef custom_util::LRUSetAssociativeCache<PrefetchBufferData> Super;

public:
    PrefetchBuffer(int size, int pattern_len, int debug_level = 0, int num_ways = 16) :
        Super(size, num_ways), pattern_len(pattern_len) {
        if (this->debug_level >= 1)
            std::cerr << "PrefetchBuffer::PrefetchBuffer(size=" << size << ", pattern_len=" << pattern_len
                      << ", debug_level=" << debug_level << ", num_ways=" << num_ways << ")" << std::dec << std::endl;
    }

    void insert(uint64_t region_number, std::vector<int> pattern) {
        if (this->debug_level >= 2)
            std::cerr << "PrefetchBuffer::insert(region_number=0x" << std::hex << region_number
                      << ", pattern=" << custom_util::pattern_to_string(pattern) << ")" << std::dec << std::endl;
        uint64_t key = this->build_key(region_number);
        Super::insert(key, {pattern});
        Super::rp_insert(key);
    }

    int prefetch(CACHE* cache, uint64_t block_num) {
        uint64_t base_addr = block_num << LOG2_BLOCK_SIZE;
        int region_offset = block_num % this->pattern_len;
        uint64_t region_number = block_num / this->pattern_len;
        uint64_t key = this->build_key(region_number);
        Entry* entry = Super::find(key);
        if (!entry) {
            return 0;
        }
        Super::set_mru(key);
        int pf_issued = 0;
        std::vector<int>& pattern = entry->data.pattern;
        pattern[region_offset] = 0; /* accessed block will be automatically fetched if necessary (miss) */
        int pf_offset;
        /* prefetch blocks that are close to the recent access first (locality!) */
        for (int d = 1; d < this->pattern_len; d += 1) {
            /* prefer positive strides */
            for (int sgn = +1; sgn >= -1; sgn -= 2) {
                pf_offset = region_offset + sgn * d;
                if (0 <= pf_offset && pf_offset < this->pattern_len && pattern[pf_offset] > 0) {
                    uint64_t pf_address = (region_number * this->pattern_len + pf_offset) << LOG2_BLOCK_SIZE;
                    if (cache->get_occupancy(3, 0) + cache->get_occupancy(0, 0) < cache->get_size(0, 0) - 1 && cache->get_occupancy(3, 0) < cache->get_size(3, 0)) {
                        uint32_t pf_metadata = 0;
                        pf_metadata = __add_pf_sour_level(pf_metadata, 1);
                        if (pattern[pf_offset] == FILL_L1) {
                            pf_metadata = __add_pf_dest_level(pf_metadata, 1);
                        } else {
                            pf_metadata = __add_pf_dest_level(pf_metadata, 2);
                        }
                        int ok = cache->prefetch_line(0, base_addr, pf_address, pattern[pf_offset] == FILL_L1, pf_metadata);
                        // assert(ok == 1);
                        pf_issued += 1;
                        pattern[pf_offset] = 0;
                    } else {
                        /* prefetching limit is reached */
                        return pf_issued;
                    }
                }
            }
        }
        Super::erase(key);
        return pf_issued;
    }

    std::string log() {
        std::vector<std::string> headers({"Region", "Pattern"});
        return Super::log(headers);
    }

private:
    void write_data(Entry& entry, custom_util::Table& table, int row) {
        uint64_t key = custom_util::hash_index(entry.key, this->index_len);
        table.set_cell(row, 0, key);
        table.set_cell(row, 1, custom_util::pattern_to_string(entry.data.pattern));
    }

    uint64_t build_key(uint64_t region_number) {
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
        pf_buffer(pb_size, pattern_len, debug_level, pb_way) {}

    void access(uint64_t block_number, uint64_t pc) {
        uint64_t region_number = block_number / this->pattern_len;
        int region_offset = block_number % this->pattern_len;
        bool success = this->accumulation_table.set_pattern(region_number, region_offset);
        if (success)
            return;
        FilterTable::Entry* entry = this->filter_table.find(region_number);
        if (!entry) {
            /* trigger access */
            this->filter_table.insert(region_number, pc, region_offset);
            std::vector<int> pattern = this->find_in_phts(pc, block_number);
            if (pattern.empty())
                return;

            this->pf_buffer.insert(region_number, pattern);
            return;
        }
        if (entry->data.offset != region_offset) {
            /* move from filter table to accumulation table */
            uint64_t region_number = custom_util::hash_index(entry->key, this->filter_table.get_index_len());
            AccumulationTable::Entry victim = this->accumulation_table.insert(region_number, entry->data.pc, entry->data.offset);
            this->accumulation_table.set_pattern(region_number, region_offset);
            this->filter_table.erase(region_number);
            if (victim.valid) {
                /* move from accumulation table to pattern history table */
                this->insert_in_phts(victim);
            }
        }
        return;
    }

    int prefetch(CACHE* cache, uint64_t block_number) {
        int pf_issued = this->pf_buffer.prefetch(cache, block_number);
        return pf_issued;
    }

    void eviction(uint64_t block_number) {
        /* end of generation */
        uint64_t region_number = block_number / this->pattern_len;
        this->filter_table.erase(region_number);
        AccumulationTable::Entry* entry = this->accumulation_table.erase(region_number);
        if (entry) {
            /* move from accumulation table to pattern history table */
            this->insert_in_phts(*entry);
        }
    }

    void set_debug_level(int debug_level) { this->debug_level = debug_level; }

    /* stats */
    Event get_event(uint64_t block_number) {
        uint64_t region_number = block_number / this->pattern_len;
        // assert(this->pht_events.count(region_number) == 1);
        return this->pht_events[region_number];
    }

    void add_prefetch(uint64_t block_number) {
        Event ev = this->get_event(block_number);
        this->prefetch_cnt[ev] += 1;
    }

    void reset_stats() {
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
    }

    uint64_t get_prefetch_cnt(Event ev) {
        return this->prefetch_cnt[ev];
    }

    void log() {
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
    std::vector<int> find_in_phts(uint64_t pc, uint64_t address) {
        if (this->debug_level >= 1) {
            std::cerr << "[Bingo] find_in_phts(pc=" << pc << ", address=" << address << ")" << std::endl;
        }
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
        } else {
            /* error: unknown event! */
            // assert(0);
        }
        /* stats */
        if (pht_last_event != MISS) {
            this->region_pref_cnt += 1;
            for (int i = 0; i < (int)pattern.size(); i += 1)
                if (pattern[i] != 0)
                    this->pref_level_cnt[pattern[i]] += 1;
            // assert(this->pref_level_cnt.size() <= 3); /* L1, L2, L3 */
        }
        /* ===== */
        return pattern;
    }

    void insert_in_phts(const AccumulationTable::Entry& entry) {
        if (this->debug_level >= 1) {
            std::cerr << "[Bingo] insert_in_phts(...)" << std::endl;
        }
        uint64_t pc = entry.data.pc;
        uint64_t region_number = custom_util::hash_index(entry.key, this->accumulation_table.get_index_len());
        uint64_t address = region_number * this->pattern_len + entry.data.offset;
        const std::vector<bool>& pattern = entry.data.pattern;
        this->pht.insert(pc, address, pattern);
    }

    std::vector<int> vote(const std::vector<std::vector<bool>>& x) {
        int n = x.size();
        if (n == 0) {
            return std::vector<int>();
        }
        /* stats */
        this->vote_cnt += 1;
        this->voter_sum += n;
        this->voter_sqr_sum += square(n);
        /* ===== */
        bool pf_flag = false;
        std::vector<int> res(this->pattern_len, 0);
        // for (int i = 0; i < n; i += 1)
        // assert((int)x[i].size() == this->pattern_len);
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
            return std::vector<int>();
        return res;
    }

    int pattern_len;
    FilterTable filter_table;
    AccumulationTable accumulation_table;
    PatternHistoryTable pht;
    PrefetchBuffer pf_buffer;
    int debug_level = 0;

    /* stats */
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
