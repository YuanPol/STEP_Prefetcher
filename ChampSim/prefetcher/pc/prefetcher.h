#ifndef SMS_H
#define SMS_H

#include <vector>

#include "custom_util.h"
#include "cache.h"

namespace {
/* Prefetcher settings */
constexpr int REGION_SIZE = 4 * 1024;
constexpr int LOG2_REGION_SIZE = champsim::lg2(REGION_SIZE);
constexpr int PC_WIDTH = 16;
constexpr int ADDR_WIDTH = 16;
constexpr int PHT_SIZE = 1024;
constexpr int FT_SIZE = 64;
constexpr int FT_WAY = 8;
constexpr int AT_SIZE = 64;
constexpr int AT_WAY = 8;
constexpr int PB_SIZE = 32;
} // namespace

namespace spb {
class FilterTableData {
public:
    uint64_t region_num;
    uint64_t pc;
    uint64_t block_num;
};

class FilterTable : public custom_util::SRRIPSetAssociativeCache<FilterTableData> {
    typedef custom_util::SRRIPSetAssociativeCache<FilterTableData> Super;

public:
    FilterTable(int size, int num_ways) :
        Super(size, num_ways) { assert(__builtin_popcount(size) == 1); }

    Entry* find(uint64_t region_number) {
        uint64_t key = build_key(region_number);
        Entry* entry = Super::find(key);
        if (!entry)
            return nullptr;
        Super::rp_promote(key);
        return entry;
    }

    void insert(uint64_t region_number, uint64_t pc, uint64_t block_num) {
        assert(!this->find(region_number));
        uint64_t key = build_key(region_number);
        // std::cout << key << std::endl;
        Super::insert(key, {region_number, pc, block_num});
        Super::rp_promote(key);
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
        table.set_cell(row, 2, entry.data.block_num);
    }

    uint64_t build_key(uint64_t region_number) {
        uint64_t key = region_number & ((1ULL << 37) - 1);
        return custom_util::hash_index(key, this->index_len);
    }
};

class AccumulationTableData {
public:
    uint64_t pc;
    uint64_t block_num;
    std::vector<bool> pattern;
};

class AccumulationTable : public custom_util::LRUSetAssociativeCache<AccumulationTableData> {
    typedef custom_util::LRUSetAssociativeCache<AccumulationTableData> Super;

public:
    AccumulationTable(int size, int num_ways, int pattern_len) :
        Super(size, num_ways), pattern_len(pattern_len) {
        assert(__builtin_popcount(size) == 1);
        assert(__builtin_popcount(pattern_len) == 1);
    }

    bool set_pattern(uint64_t region_number, int offset) {
        uint64_t key = build_key(region_number);
        Entry* entry = Super::find(key);
        if (!entry)
            return false;
        entry->data.pattern[offset] = true;
        Super::rp_insert(key);
        // std::cout << entry->data.offset << " " << offset << " " << custom_util::pattern_to_string(entry->data.pattern) << std::endl;
        return true;
    }

    Entry insert(FilterTable::Entry& entry) {
        uint64_t key = build_key(entry.data.region_num);
        assert(!this->find(key));
        std::vector<bool> pattern(this->pattern_len, false);
        int offset = entry.data.block_num % pattern_len;
        assert(offset >= 0 && offset < REGION_SIZE / BLOCK_SIZE);
        pattern[offset] = true;
        Entry old_entry = Super::insert(key, {entry.data.pc, entry.data.block_num, pattern});
        Super::rp_insert(key);
        return old_entry;
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
        table.set_cell(row, 2, entry.data.block_num);
        table.set_cell(row, 3, custom_util::pattern_to_string(entry.data.pattern));
    }
    uint64_t build_key(uint64_t page_num) {
        uint64_t key = page_num & ((1ULL << 37) - 1);
        return custom_util::hash_index(key, this->index_len);
    }
    int pattern_len;
};

class PatternHistoryTableData {
public:
    std::vector<bool> pattern;
};

class PatternHistoryTable : custom_util::LRUSetAssociativeCache<PatternHistoryTableData> {
    typedef custom_util::LRUSetAssociativeCache<PatternHistoryTableData> Super;

public:
    PatternHistoryTable(
        int size, int pattern_len, int addr_width, int pc_width, int num_ways = 16) :
        Super(size, num_ways),
        pattern_len(pattern_len), addr_width(addr_width),
        pc_width(pc_width) {
        assert(this->pc_width >= 0);
        assert(this->addr_width >= 0);
        assert(this->pc_width + this->addr_width > 0);
        assert(__builtin_popcount(pattern_len) == 1);
        this->index_len = __builtin_ctz(this->num_sets);
    }

    /* address is actually block number */
    void insert(uint64_t pc, uint64_t block_num, std::vector<bool> pattern) {
        assert((int)pattern.size() == this->pattern_len);
        int offset = block_num % this->pattern_len;
        // pattern = custom_util::my_rotate(pattern, -offset);
        uint64_t key = this->build_key(pc, block_num);
        Super::insert(key, {pattern});
        this->set_mru(key);
    }

    /**
     * @return An un-rotated pattern if match was found, otherwise an empty vector.
     */
    std::vector<bool> find(uint64_t pc, uint64_t block_num) {
        uint64_t key = this->build_key(pc, block_num);
        Entry* entry = Super::find(key);
        if (!entry)
            return std::vector<bool>();
        this->set_mru(key);
        std::vector<bool> pattern = entry->data.pattern;
        int offset = block_num % this->pattern_len;
        // pattern = custom_util::my_rotate(pattern, +offset);
        return pattern;
    }

    std::string log() {
        std::vector<std::string> headers({"PC", "Offset", "Pattern"});
        return Super::log(headers);
    }

private:
    /* @override */
    void write_data(Entry& entry, custom_util::Table& table, int row) {
        uint64_t key = entry.key;

        /* extract PC, offset, and address */
        uint64_t offset = key & ((1 << this->addr_width) - 1);
        key >>= this->addr_width;
        uint64_t pc = key & ((1 << this->pc_width) - 1);

        table.set_cell(row, 0, pc);
        table.set_cell(row, 1, offset);
        table.set_cell(row, 2, custom_util::pattern_to_string(entry.data.pattern));
    }
    uint64_t build_key(uint64_t pc, uint64_t block_num) {
        pc &= (1 << this->pc_width) - 1; /* use [addr_width] bits from address */
        uint64_t key = pc;

        return key;
    }

    int pattern_len, index_len;
    int addr_width, pc_width;
};

class PrefetchBufferData {
public:
    std::vector<int> pattern;
};

class PrefetchBuffer : public custom_util::LRUSetAssociativeCache<PrefetchBufferData> {
    typedef custom_util::LRUSetAssociativeCache<PrefetchBufferData> Super;

public:
    PrefetchBuffer(int size, int pattern_len, int debug_level = 0, int num_ways = 8) :
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
                        pf_metadata = __add_pf_dest_level(pf_metadata, 1);
                        int ok = cache->prefetch_line(0, base_addr, pf_address, true, pf_metadata);
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

class Prefetcher {
public:
    Prefetcher(int pattern_len, int addr_width, int pc_width, int pattern_history_table_size,
               int filter_table_size, int filter_table_way, int accumulation_table_size, int accumulation_table_way, int pb_size) :
        pattern_len(pattern_len),
        filter_table(filter_table_size, filter_table_way),
        accumulation_table(accumulation_table_size, accumulation_table_size, pattern_len),
        pht(pattern_history_table_size, pattern_len, addr_width, pc_width),
        pb(pb_size, pattern_len) {}

    void access(uint64_t block_number, uint64_t pc) {
        if (this->debug_level >= 1) {
            std::cerr << "[Prefetcher] access(block_number=" << block_number << ", pc=" << pc << ")" << std::endl;
        }
        uint64_t region_number = block_number / this->pattern_len;
        int region_offset = block_number % this->pattern_len;
        bool success = this->accumulation_table.set_pattern(region_number, region_offset);
        if (success)
            return;
        FilterTable::Entry* entry = this->filter_table.find(region_number);
        if (!entry) {
            /* trigger access */
            this->filter_table.insert(region_number, pc, block_number);
            std::vector<bool> pattern = this->find_in_pht(pc, block_number);
            if (pattern.empty())
                return;

            this->pb.insert(region_number, custom_util::pattern_convert(pattern));
            std::vector<uint64_t> to_prefetch;
            return;
        }
        if (entry->data.block_num % pattern_len != region_offset) {
            /* move from filter table to accumulation table */
            AccumulationTable::Entry victim = this->accumulation_table.insert(*entry);
            this->accumulation_table.set_pattern(region_number, region_offset);
            this->filter_table.erase(region_number);
            if (victim.valid) {
                /* move from accumulation table to pattern history table */
                this->insert_in_pht(victim);
            }
        }
        return;
    }

    int prefetch(CACHE* cache, uint64_t block_num) {
        int pf_issued = this->pb.prefetch(cache, block_num);
        return pf_issued;
    }

    void eviction(uint64_t block_number) {
        /* end of generation */
        uint64_t region_number = block_number / this->pattern_len;
        this->filter_table.erase(region_number);
        AccumulationTable::Entry* entry = this->accumulation_table.erase(region_number);
        if (entry) {
            /* move from accumulation table to pattern history table */
            this->insert_in_pht(*entry);
        }
    }

    void set_debug_level(int debug_level) { this->debug_level = debug_level; }

    double get_match_prob() {
        return 1.0 * this->pht_match_cnt / this->pht_lookup_cnt;
    }

    void reset_match_prob() {
        this->pht_lookup_cnt = 0;
        this->pht_match_cnt = 0;
    }

public:
    std::vector<bool> find_in_pht(uint64_t pc, uint64_t block_number) {
        if (this->debug_level >= 1) {
            std::cerr << "[Prefetcher] find_in_pht(pc=" << pc << ", block_number=" << block_number << ")" << std::endl;
        }

        this->pht_lookup_cnt += 1;
        std::vector<bool> pattern = this->pht.find(pc, block_number);
        if (!pattern.empty())
            this->pht_match_cnt += 1;
        return pattern;
    }

    void insert_in_pht(const AccumulationTable::Entry& entry) {
        if (this->debug_level >= 1) {
            std::cerr << "[Prefetcher] insert_in_pht(...)" << std::endl;
        }
        const std::vector<bool>& pattern = entry.data.pattern;
        this->pht.insert(entry.data.pc, entry.data.block_num, pattern);
        // std::cout << entry.data.offset << " " << custom_util::pattern_to_string(entry.data.pattern) << std::endl;
    }

    void log() {
        std::cerr << "Filter table begin" << std::dec << std::endl;
        std::cerr << this->filter_table.log();
        std::cerr << "Filter table end" << std::endl;

        std::cerr << "Accumulation table begin" << std::dec << std::endl;
        std::cerr << this->accumulation_table.log();
        std::cerr << "Accumulation table end" << std::endl;

        std::cerr << "PHT begin" << std::dec << std::endl;
        std::cerr << this->pht.log();
        std::cerr << "PHT end" << std::endl;

        std::cerr << "Prefetch buffer begin" << std::dec << std::endl;
        std::cerr << this->pb.log();
        std::cerr << "Prefetch buffer end" << std::endl;
    }

    int pattern_len;
    FilterTable filter_table;
    AccumulationTable accumulation_table;
    PatternHistoryTable pht;
    PrefetchBuffer pb;
    int debug_level = 0;

    /* stats */
    uint64_t pht_lookup_cnt = 0;
    uint64_t pht_match_cnt = 0;
};
} // namespace spb

#endif