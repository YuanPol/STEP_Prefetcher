#ifndef _DSPATCH_H_
#define _DSPATCH_H_

#include <vector>
#include <deque>
#include <limits.h>
#include "bitmap.h"
#include "prefetcher.h"
#include "cache.h"

#define DSPATCH_MAX_BW_LEVEL 5

using namespace std;

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

enum DSPatch_pref_candidate {
    PAT_NONE = 0,
    PAT_COVP,
    PAT_ACCP,
    Num_DSPatch_pref_candidates
};

const char* Map_DSPatch_pref_candidate(DSPatch_pref_candidate candidate);

class DSPatch_counter {
private:
    uint32_t counter;

public:
    DSPatch_counter() :
        counter(0) {}
    ~DSPatch_counter() {}
    inline void incr(uint32_t max = UINT_MAX) { counter = (counter < max ? counter + 1 : counter); }
    inline void decr(uint32_t min = 0) { counter = (counter > min ? counter - 1 : counter); }
    inline uint32_t value() { return counter; }
    inline void reset() { counter = 0; }
};

class DSPatch_PBEntry {
public:
    uint64_t page;
    uint64_t trigger_pc;
    uint32_t trigger_offset;
    Bitmap bmp_real;

    DSPatch_PBEntry() :
        page(0xdeadbeef), trigger_pc(0xdeadbeef), trigger_offset(0) {
        bmp_real.reset();
    }
    ~DSPatch_PBEntry() {}
};

class DSPatch_SPTEntry {
public:
    uint64_t signature;
    Bitmap bmp_cov;
    Bitmap bmp_acc;
    DSPatch_counter measure_covP, measure_accP;
    DSPatch_counter or_count;
    /* TODO: add confidence counters */

    DSPatch_SPTEntry() :
        signature(0xdeadbeef) {
        bmp_cov.reset();
        bmp_acc.reset();
        measure_covP.reset();
        measure_accP.reset();
        or_count.reset();
    }
    ~DSPatch_SPTEntry() {}
};

class DSPatch : public Prefetcher {
private:
    deque<DSPatch_PBEntry*> page_buffer;
    DSPatch_SPTEntry** spt;
    deque<uint64_t> pref_buffer;

    /* 0 => b/w is less than 25% of peak
	 * 1 => b/w is more than 25% and less than 50% of peak
	 * 2 => b/w is more than 50% and less than 75% of peak
	 * 3 => b/w is more than 75% of peak
	 */
    uint8_t bw_bucket;

    /* stats */
    struct
    {
        struct
        {
            uint64_t lookup;
            uint64_t hit;
            uint64_t evict;
            uint64_t insert;
        } pb;

        struct
        {
            uint64_t called;
            uint64_t selection_dist[DSPatch_pref_candidate::Num_DSPatch_pref_candidates];
            uint64_t reset;
            uint64_t total;
        } gen_pref;

        struct
        {
            uint64_t called;
            uint64_t none;
            uint64_t accp_reason1;
            uint64_t accp_reason2;
            uint64_t covp_reason1;
            uint64_t covp_reason2;
        } dyn_selection;

        struct
        {
            uint64_t called;
            uint64_t or_count_incr;
            uint64_t measure_covP_incr;
            uint64_t bmp_cov_reset;
            uint64_t bmp_cov_update;
            uint64_t measure_accP_incr;
            uint64_t measure_accP_decr;
            uint64_t bmp_acc_update;
        } spt;

        struct
        {
            uint64_t called;
            uint64_t bw_histogram[DSPATCH_MAX_BW_LEVEL];
        } bw;

        struct
        {
            uint64_t spilled;
            uint64_t buffered;
            uint64_t issued;
        } pref_buffer;
    } stats;

private:
    void init_knobs();
    void init_stats();
    DSPatch_pref_candidate select_bitmap(DSPatch_SPTEntry* sptentry, Bitmap& bmp_selected);
    DSPatch_PBEntry* search_pb(uint64_t page);
    void buffer_prefetch(vector<uint64_t> pref_addr);
    void issue_prefetch(vector<uint64_t>& pref_addr);
    uint64_t create_signature(uint64_t pc, uint64_t page, uint32_t offset);
    uint32_t get_spt_index(uint64_t signature);
    uint32_t get_hash(uint32_t key);
    void add_to_spt(DSPatch_PBEntry* pbentry);
    DSPatch_pref_candidate dyn_selection(DSPatch_SPTEntry* sptentry, Bitmap& bmp_selected);
    void generate_prefetch(uint64_t pc, uint64_t page, uint32_t offset, uint64_t address);

public:
    PrefetchBuffer pb;
    DSPatch(string type);
    ~DSPatch();
    void invoke_prefetcher(uint64_t pc, uint64_t address, uint8_t cache_hit, uint8_t type, vector<uint64_t>& pref_addr);
    int prefetch(CACHE* cache, uint64_t block_num);
    void dump_stats();
    void print_config();
    void update_bw(uint8_t bw);
};

#endif
