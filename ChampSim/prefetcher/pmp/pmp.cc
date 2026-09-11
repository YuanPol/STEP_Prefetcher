#include "pmp.h"
#include "custom_util.h"

#include <bits/stdc++.h>
#include <random>

#include "cache.h"
#include "ooo_cpu.h"

namespace {

const int DEBUG_LEVEL = 0;
bool SUPPORT_VA = false;

// (1 << 12) >> 6 = 64
// 64 cache blocks in a region
constexpr int PATTERN_LEN = (1 << pmp::IN_REGION_BITS) / BLOCK_SIZE;
constexpr int FT_SIZE = 64;
constexpr int FT_WAY = 8;
constexpr int AT_SIZE = 32;
constexpr int AT_WAY = 16;
// Offset Pattern Table
constexpr int OPT_WAYS = 1;
constexpr int OPT_SIZE = (1 << pmp::OFFSET_BITS) * OPT_WAYS;
constexpr int OFFSET_MAX_CONF = 32;
// PC Pattern Table
constexpr int PPT_WAYS = 1;
constexpr int PPT_SIZE = (1 << pmp::PC_BITS) * PPT_WAYS;

constexpr int PC_MAX_CONF = 32;
constexpr int PF_BUFFER_SIZE = 32;
constexpr int PF_BUFFER_WAY = 8;

static std::vector<pmp::PMP> prefetchers;

} // namespace

void pmp::PMP::access(uint64_t block_number, uint64_t pc) {
    if (this->debug_level >= 2)
        std::cerr << "[ PMP] access(block_number=0x" << std::hex << block_number << ", pc=0x" << pc << ")" << std::dec << std::endl;

    uint64_t region_number = block_number >> OFFSET_BITS;
    int region_offset = __fine_offset(block_number);
    bool success = this->accumulation_table.set_pattern(region_number, __coarse_offset(region_offset));
    if (success)
        return;
    FilterTable::Entry* entry = this->filter_table.find(region_number);
    if (!entry) {
        this->filter_table.insert(region_number, region_offset, pc);
        std::vector<int> pattern = this->find_in_opt(pc, block_number);
        if (pattern.empty()) {
            return;
        }

        this->pf_buffer.insert(region_number, pattern);
        return;
    } else if (entry->data.offset != region_offset) {
        uint64_t region_number = custom_util::hash_index(entry->key, this->filter_table.get_index_len());
        AccumulationTable::Entry victim =
            this->accumulation_table.insert(region_number, entry->data.pc, entry->data.offset, region_offset);
        this->accumulation_table.set_pattern(region_number, __coarse_offset(region_offset));
        this->filter_table.erase(region_number);
        if (victim.valid) {
            invalid_by_max++;
            this->insert_in_opt(victim);
        }
    }
}

void pmp::PMP::eviction(uint64_t block_number) {
    if (this->debug_level >= 2)
        std::cerr << "[ PMP] eviction(block_number=" << block_number << ")" << std::dec << std::endl;
    uint64_t region_number = block_number / this->pattern_len;
    this->filter_table.erase(region_number);
    AccumulationTable::Entry* entry = this->accumulation_table.erase(region_number);
    if (entry) {
        invalid_by_eviction++;
        this->insert_in_opt(*entry);
    }
}

int pmp::PMP::prefetch(CACHE* cache, uint64_t block_number) {
    if (this->debug_level >= 2)
        std::cerr << " PMP::prefetch(cache=" << cache->NAME << ", block_number=" << std::hex << block_number << ")" << std::dec
                  << std::endl;
    int pf_issued = this->pf_buffer.prefetch(cache, block_number);
    if (this->debug_level >= 2)
        std::cerr << "[ PMP::prefetch] pf_issued=" << pf_issued << std::dec << std::endl;
    return pf_issued;
}

void pmp::PMP::set_debug_level(int debug_level) {
    this->filter_table.set_debug_level(debug_level);
    this->accumulation_table.set_debug_level(debug_level);
    this->opt.set_debug_level(debug_level);
    this->ppt.set_debug_level(debug_level);
    this->debug_level = debug_level;
}

void pmp::PMP::log() {
    std::cerr << "Filter table begin" << std::dec << std::endl;
    std::cerr << this->filter_table.log();
    std::cerr << "Filter table end" << std::endl;

    std::cerr << "Accumulation table begin" << std::dec << std::endl;
    std::cerr << this->accumulation_table.log();
    std::cerr << "Accumulation table end" << std::endl;

    std::cerr << "Offset pattern table begin" << std::dec << std::endl;
    std::cerr << this->opt.log();
    std::cerr << "Offset pattern table end" << std::endl;

    std::cerr << "PC pattern table begin" << std::dec << std::endl;
    std::cerr << this->ppt.log();
    std::cerr << "PC pattern table end" << std::endl;

    std::cerr << "Prefetch buffer begin" << std::dec << std::endl;
    std::cerr << this->pf_buffer.log();
    std::cerr << "Prefetch buffer end" << std::endl;
}

std::vector<int> pmp::PMP::find_in_opt(uint64_t pc, uint64_t block_number) {
    if (this->debug_level >= 2) {
        std::cerr << "[ PMP] find_in_opt(pc=0x" << std::hex << pc << ", address=0x" << block_number << ")" << std::dec << std::endl;
    }
    std::vector<OffsetPatternTableData> matches = this->opt.find(pc, block_number);
    std::vector<OffsetPatternTableData> matches_pc = this->ppt.find(pc, block_number);
    std::vector<int> pattern;
    std::vector<int> pattern_pc;
    std::vector<int> result_pattern(this->pattern_len, 0);
    if (!matches.empty()) {
        pattern = this->vote(matches);
        pattern_pc = this->vote(matches_pc, true);
        // if (pattern_pc.empty()) {
        //     for (int i = 0; i < this->pattern_len; i++) {
        //         result_pattern[i] = pattern[i] == FILL_L1_PMP ? FILL_L2_PMP : pattern[i] == FILL_L2_PMP ? FILL_LLC_PMP : 0;
        //     }
        // } else {
        //     for (int i = 0; i < this->pattern_len; i++) {
        //         if (pattern[i] == FILL_L1_PMP && pattern_pc[i / PATTERN_DEGRADE_LEVEL] == FILL_L1_PMP) {
        //             result_pattern[i] = FILL_L1_PMP;
        //         } else if (pattern[i] == FILL_L1_PMP || pattern_pc[i / PATTERN_DEGRADE_LEVEL] == FILL_L1_PMP || pattern[i] == FILL_L2_PMP || pattern_pc[i / PATTERN_DEGRADE_LEVEL] == FILL_L2_PMP) {
        //             result_pattern[i] = FILL_L2_PMP;
        //         }
        //     }
        // }
        // better performance
        if (pattern_pc.empty()) {
            for (int i = 0; i < this->pattern_len; i++) {
                result_pattern[i] = pattern[i];
            }
        } else {
            for (int i = 0; i < this->pattern_len; i++) {
                result_pattern[i] = pattern[i];
            }
        }
    }

    int offset = __coarse_offset(__fine_offset(block_number));
    result_pattern = custom_util::my_rotate(result_pattern, +offset);
    return result_pattern;
}

void pmp::PMP::insert_in_opt(const pmp::AccumulationTable::Entry& entry) {
    uint64_t region_number = custom_util::hash_index(entry.key, this->accumulation_table.get_index_len());
    uint64_t address = (region_number << OFFSET_BITS) + entry.data.offset;
    if (this->debug_level >= 2) {
        std::cerr << "[ PMP] insert_in_opt(" << std::hex << " address=0x" << address << ")" << std::dec << std::endl;
    }
    const std::vector<bool>& pattern = entry.data.pattern;
    if (custom_util::count_bits(custom_util::pattern_to_int(pattern)) != 1) {
        this->opt.insert(address, entry.data.pc, pattern, false, entry.data.second_offset);
        this->ppt.insert(address, entry.data.pc, custom_util::pattern_degrade(pattern, PATTERN_DEGRADE_LEVEL), true, entry.data.second_offset);
    }
}

std::vector<int> pmp::PMP::vote(const std::vector<pmp::OffsetPatternTableData>& x, bool is_pc_opt) {
    if (this->debug_level >= 2)
        std::cerr << " PMP::vote(...)" << std::endl;
    int n = x.size();
    if (n == 0) {
        if (this->debug_level >= 2)
            std::cerr << "[ PMP::vote] There are no voters." << std::endl;
        return std::vector<int>();
    }

    if (this->debug_level >= 2) {
        std::cerr << "[ PMP::vote] Taking a vote among:" << std::endl;
        for (int i = 0; i < n; i += 1)
            std::cerr << "<" << std::setw(3) << i + 1 << "> " << custom_util::pattern_to_string(x[i].pattern) << std::endl;
    }
    bool pf_flag = false;
    int pattern_len = is_pc_opt ? this->pattern_len / PATTERN_DEGRADE_LEVEL : this->pattern_len;
    std::vector<int> res(pattern_len, 0);

    for (int i = 0; i < pattern_len; i += 1) {
        int cnt = 0;
        for (int j = 0; j < n; j += 1) {
            cnt += x[j].pattern[i];
        }
        double p = 1.0 * cnt / x[0].pattern[0];
        if (p > 1) {
            std::cout << "cnt:" << cnt << ",total:" << x[0].pattern[0] << std::endl;
            assert(p <= 1);
        }

        if (x[0].pattern[0] <= START_CONF) {
            break;
        }

        if (is_pc_opt) {
            if (p >= PC_L1D_THRESH)
                res[i] = FILL_L1_PMP;
            else if (p >= PC_L2C_THRESH)
                res[i] = FILL_L2_PMP;
            else if (p >= PC_LLC_THRESH)
                res[i] = FILL_LLC_PMP;
            else
                res[i] = 0;
        } else {
            if (p >= L1D_THRESH)
                res[i] = FILL_L1_PMP;
            else if (p >= L2C_THRESH)
                res[i] = FILL_L2_PMP;
            else if (p >= LLC_THRESH)
                res[i] = FILL_LLC_PMP;
            else
                res[i] = 0;
        }
    }
    if (this->debug_level >= 2) {
        std::cerr << "<res> " << custom_util::pattern_to_string(res) << std::endl;
    }

    return res;
}

void CACHE::prefetcher_initialize() {
    std::cout << NAME << " PMP prefetcher" << std::endl;
    prefetchers = std::vector<pmp::PMP>(
        NUM_CPUS, pmp::PMP(PATTERN_LEN,
                           pmp::OFFSET_BITS, OPT_SIZE, OFFSET_MAX_CONF, OPT_WAYS,
                           pmp::PC_BITS, PPT_SIZE, PC_MAX_CONF, PPT_WAYS,
                           FT_SIZE, FT_WAY,
                           AT_SIZE, AT_WAY,
                           PF_BUFFER_SIZE, PF_BUFFER_WAY,
                           FILL_L1, FILL_L2, FILL_LLC,
                           DEBUG_LEVEL, cpu));
}

uint32_t CACHE::prefetcher_cache_operate(uint64_t addr, uint64_t ip, uint8_t cache_hit, uint8_t type, uint32_t metadata_in) {
    if (DEBUG_LEVEL >= 2) {
        std::cerr << "CACHE::l1d_prefetcher_operate(addr=0x" << std::hex << addr << ", ip=0x" << ip << ", cache_hit=" << std::dec
                  << (int)cache_hit << ", type=" << (int)type << ")" << std::dec << std::endl;
        std::cerr << "[CACHE::l1d_prefetcher_operate] CACHE{core=" << this->cpu << ", NAME=" << this->NAME << "}" << std::dec
                  << std::endl;
    }

    if (type != LOAD)
        return metadata_in;

    uint64_t block_number = addr >> pmp::BOTTOM_BITS;

    prefetchers[cpu].access(block_number, ip);

    prefetchers[cpu].prefetch(this, block_number);

    if (DEBUG_LEVEL >= 3) {
        prefetchers[cpu].log();
        std::cerr << "=======================================" << std::dec << std::endl;
    }
    return metadata_in;
}

uint32_t CACHE::prefetcher_cache_fill(uint64_t addr, uint32_t set, uint32_t way, uint8_t prefetch, uint64_t evicted_addr, uint32_t metadata_in) {
    uint64_t evicted_block_number = evicted_addr >> LOG2_BLOCK_SIZE;

    if (this->block[set * NUM_WAY + way].valid == 0)
        return metadata_in;

    for (int i = 0; i < NUM_CPUS; i += 1) {
        if (!block[set * NUM_WAY + way].prefetch)
            prefetchers[i].eviction(evicted_block_number);
    }
    return metadata_in;
}

void CACHE::prefetcher_cycle_operate() {}
void CACHE::prefetcher_cache_eviction(uint64_t addr, uint64_t paddr) {}
void CACHE::prefetcher_final_stats() {
    std::cout << "Prefetch Request to L1: " << pmp::prefetch_to_l1 << ", "
              << "Prefetch Request to L2: " << pmp::prefetch_to_l2 << std::endl;
    std::cout << "Invalid by Eviction: " << prefetchers[cpu].invalid_by_eviction << std::endl;
    std::cout << "Invalid by Max: " << prefetchers[cpu].invalid_by_max << std::endl;
    prefetchers[cpu].log();

    std::cout << "Filter by PPT: " << pmp::filter_by_ppt << std::endl;
}
