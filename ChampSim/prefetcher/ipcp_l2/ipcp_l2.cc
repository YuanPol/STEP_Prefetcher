/*************************************************************************************************************************
Authors: 
Samuel Pakalapati - samuelpakalapati@gmail.com
Biswabandan Panda - biswap@cse.iitk.ac.in
Nilay Shah - nilays@iitk.ac.in
Neelu Shivprakash kalani - neeluk@cse.iitk.ac.in 
**************************************************************************************************************************/
/*************************************************************************************************************************
Source code for "Bouquet of Instruction Pointers: Instruction Pointer Classifier-based Spatial Hardware Prefetching" 
appeared (to appear) in ISCA 2020: https://www.iscaconf.org/isca2020/program/. The paper is available at 
https://www.cse.iitk.ac.in/users/biswap/IPCP_ISCA20.pdf. The source code can be used with the ChampSim simulator 
https://github.com/ChampSim . Note that the authors have used a modified ChampSim that supports detailed virtual 
memory sub-system. Performance numbers may increase/decrease marginally
based on the virtual memory-subsystem support. Also for PIPT L1-D caches, this code may demand 1 to 1.5KB additional 
storage for various hardware tables.     
**************************************************************************************************************************/

#include "cache.h"
#include "ipcp_l2.h"

namespace {
ipcp_l2::STAT_COLLECT stats_l2[NUM_CPUS][5]; // for GS, CS, CPLX, NL and no class
uint64_t num_misses_l2[NUM_CPUS] = {0};
//DELTA_PRED_TABLE CSPT_l2[NUM_CPUS][NUM_CSPT_L2_ENTRIES];
uint32_t spec_nl_l2[NUM_CPUS] = {0};
ipcp_l2::IP_TABLE trackers[NUM_CPUS][ipcp_l2::NUM_IP_TABLE_L2_ENTRIES];
} // namespace

namespace ipcp_l2 {
uint64_t hash_bloom_l2(uint64_t addr) {
    uint64_t first_half, sec_half;
    first_half = addr & 0xFFF;
    sec_half = (addr >> 12) & 0xFFF;
    if ((first_half ^ sec_half) >= 4096)
        assert(0);
    return ((first_half ^ sec_half) & 0xFFF);
} /*decode_stride: This function decodes 7 bit stride from the metadata from IPCP at L1. 6 bits for magnitude and 1 bit for sign. */

int decode_stride(uint32_t metadata) {
    int stride = 0;
    metadata >>= 2;
    if (metadata & 0b1000000)
        stride = -1 * (metadata & 0b111111);
    else
        stride = metadata & 0b111111;

    return stride;
}

/* update_conf_l2: If the actual stride and predicted stride are equal, then the confidence counter is incremented. */
int update_conf_l2(int stride, int pred_stride, int conf) {
    if (stride == pred_stride) { // use 2-bit saturating counter for confidence
        conf++;
        if (conf > 3)
            conf = 3;
    } else {
        conf--;
        if (conf < 0)
            conf = 0;
    }

    return conf;
}

/* encode_metadata_l2: This function encodes the stride, prefetch class type and speculative nl fields in the metadata. */
uint32_t encode_metadata_l2(int stride, uint16_t type, int spec_nl_l2) {
    assert(stride < 64);
    uint32_t metadata = 0;
    // 1001101000000
    // 1000101000000
    // first encode stride in the last 8 bits of the metadata
    if (stride > 0)
        metadata = stride;
    else
        metadata = ((-1 * stride) | 0b1000000);

    // encode the type of IP in the next 4 bits
    metadata = metadata | (type << 7);

    // encode the speculative NL bit in the next 1 bit
    metadata = metadata | (spec_nl_l2 << 11);

    metadata <<= 2;
    metadata = __add_pf_dest_level(metadata, 2);
    metadata = __add_pf_sour_level(metadata, 2);

    assert(__decode_ipcp_type(metadata) != 0);
    return metadata;
}

void stat_col_L2(uint64_t addr, uint8_t cache_hit, uint8_t cpu, uint64_t ip) {
    uint64_t index = hash_bloom_l2(addr);
    int ip_index = ip & ((1 << NUM_IP_INDEX_BITS_L2) - 1);
    uint16_t ip_tag = (ip >> NUM_IP_INDEX_BITS_L2) & ((1 << NUM_IP_TAG_BITS_L2) - 1);

    for (int i = 0; i < 5; i++) {
        if (cache_hit) {
            if (stats_l2[cpu][i].bl_filled[index] == 1) {
                stats_l2[cpu][i].useful++;
                stats_l2[cpu][i].filled++;
                stats_l2[cpu][i].bl_filled[index] = 0;
            }
        } else {
            if (ip_tag == trackers[cpu][ip_index].ip_tag) {
                if (trackers[cpu][ip_index].pref_type == i)
                    stats_l2[cpu][i].misses++;
                if (stats_l2[cpu][i].bl_filled[index] == 1) {
                    stats_l2[cpu][i].polluted_misses++;
                    stats_l2[cpu][i].filled++;
                    stats_l2[cpu][i].bl_filled[index] = 0;
                }
            }
        }

        if (num_misses_l2[cpu] % 1024 == 0) {
            for (int j = 0; j < NUM_BLOOM_ENTRIES; j++) {
                stats_l2[cpu][i].filled += stats_l2[cpu][i].bl_filled[j];
                stats_l2[cpu][i].bl_filled[j] = 0;
                stats_l2[cpu][i].bl_request[j] = 0;
            }
        }
    }
}
} // namespace ipcp_l2

void CACHE::prefetcher_initialize() {
    std::cout << NAME << " IPCP_L2C prefetcher" << std::endl;
}

uint32_t CACHE::prefetcher_cache_operate(uint64_t addr, uint64_t ip, uint8_t cache_hit, uint8_t type, uint32_t metadata_in) {
    // std::cout << "operate called" << std::endl;
    uint64_t page = addr >> LOG2_PAGE_SIZE;
    uint64_t curr_tag = (page ^ (page >> 6) ^ (page >> 12)) & ((1 << ipcp_l2::NUM_IP_TAG_BITS_L2) - 1);
    uint64_t line_offset = (addr >> LOG2_BLOCK_SIZE) & 0x3F;
    uint64_t line_addr = addr >> LOG2_BLOCK_SIZE;
    int prefetch_degree = 0;
    int64_t stride = ipcp_l2::decode_stride(metadata_in);
    uint32_t pref_type = (metadata_in & 0xF00) >> 8;
    uint16_t ip_tag = (ip >> ipcp_l2::NUM_IP_INDEX_BITS_L2) & ((1 << ipcp_l2::NUM_IP_TAG_BITS_L2) - 1);
    int num_prefs = 0;
    uint64_t bl_index = 0;
    if (NUM_CPUS == 1) {
        prefetch_degree = 3;
    } else { // tightening the degree for multi-core
        prefetch_degree = 2;
    }

    ipcp_l2::stat_col_L2(addr, cache_hit, cpu, ip);
    if (cache_hit == 0 && type != PREFETCH)
        num_misses_l2[cpu]++;

    // calculate the index bit
    int index = ip & ((1 << ipcp_l2::NUM_IP_INDEX_BITS_L2) - 1);
    if (trackers[cpu][index].ip_tag != ip_tag) {  // new/conflict IP
        if (trackers[cpu][index].ip_valid == 0) { // if valid bit is zero, update with latest IP info
            trackers[cpu][index].ip_tag = ip_tag;
            trackers[cpu][index].pref_type = pref_type;
            trackers[cpu][index].stride = stride;
        } else {
            trackers[cpu][index].ip_valid = 0; // otherwise, reset valid bit and leave the previous IP as it is
        }

        // issue a next line prefetch upon encountering new IP
        uint64_t pf_address = ((addr >> LOG2_BLOCK_SIZE) + 1) << LOG2_BLOCK_SIZE;
        //Ensure it lies on the same 4 KB page.
        if ((pf_address >> LOG2_PAGE_SIZE) == (addr >> LOG2_PAGE_SIZE)) {
#ifdef DO_PREF
            prefetch_line(ip, addr, pf_address, true, 0);
#endif
            SIG_DP(cout << "1, ");
        }
        return metadata_in;
    } else { // if same IP encountered, set valid bit
        trackers[cpu][index].ip_valid = 1;
    }

    // update the IP table upon receiving metadata from prefetch
    if (type == PREFETCH) {
        trackers[cpu][index].pref_type = pref_type;
        trackers[cpu][index].stride = stride;
        spec_nl_l2[cpu] = metadata_in & 0x1000;
    }

    SIG_DP(
        cout << ip << ", " << cache_hit << ", " << line_addr << ", ";
        cout << ", " << stride << "; ";);

    if ((trackers[cpu][index].pref_type == 1 || trackers[cpu][index].pref_type == 2) && trackers[cpu][index].stride != 0) { // S or CS class
        uint32_t metadata = 0;
        if (trackers[cpu][index].pref_type == 1) {
            prefetch_degree = prefetch_degree * 2;
            metadata = ipcp_l2::encode_metadata_l2(1, ipcp_l2::S_TYPE, spec_nl_l2[cpu]); // for stream, prefetch with twice the usual degree
        } else {
            metadata = ipcp_l2::encode_metadata_l2(1, ipcp_l2::CS_TYPE, spec_nl_l2[cpu]); // for stream, prefetch with twice the usual degree
        }

        for (int i = 0; i < prefetch_degree; i++) {
            uint64_t pf_address = (line_addr + (trackers[cpu][index].stride * (i + 1))) << LOG2_BLOCK_SIZE;

            // Check if prefetch address is in same 4 KB page
            if ((pf_address >> LOG2_PAGE_SIZE) != (addr >> LOG2_PAGE_SIZE))
                break;
            num_prefs++;
#ifdef DO_PREF
            prefetch_line(ip, addr, pf_address, true, metadata);
#endif
            SIG_DP(cout << trackers[cpu][index].stride << ", ");
        }
    }

    // if no prefetches are issued till now, speculatively issue a next_line prefetch
    if (num_prefs == 0 && spec_nl_l2[cpu] == 1) { // NL IP
        uint64_t pf_address = ((addr >> LOG2_BLOCK_SIZE) + 1) << LOG2_BLOCK_SIZE;
        //If it is not in the same 4 KB page, return.
        if ((pf_address >> LOG2_PAGE_SIZE) != (addr >> LOG2_PAGE_SIZE)) {
            return metadata_in;
        }
        bl_index = ipcp_l2::hash_bloom_l2(pf_address);
        stats_l2[cpu][ipcp_l2::NL_TYPE].bl_request[bl_index] = 1;
        uint32_t metadata = ipcp_l2::encode_metadata_l2(1, ipcp_l2::NL_TYPE, spec_nl_l2[cpu]);
        trackers[cpu][index].pref_type = 3;
#ifdef DO_PREF
        prefetch_line(ip, addr, pf_address, true, metadata);
#endif
        SIG_DP(cout << "1, ");
    }

    SIG_DP(cout << endl);
    // std::cout << "operate done" << std::endl;
    return metadata_in;
}

uint32_t CACHE::prefetcher_cache_fill(uint64_t addr, uint32_t set, uint32_t way, uint8_t prefetch, uint64_t evicted_addr, uint32_t metadata_in) {
    // std::cout << "fill called" << std::endl;
    if (prefetch) {
        uint32_t pref_type = __decode_ipcp_type(metadata_in);
        pref_type = pref_type >> 8;

        uint64_t index = ipcp_l2::hash_bloom_l2(addr);
        if (stats_l2[cpu][pref_type].bl_request[index] == 1) {
            stats_l2[cpu][pref_type].bl_filled[index] = 1;
            stats_l2[cpu][pref_type].bl_request[index] = 0;
        }
    }
    // std::cout << "fill done" << std::endl;
    return metadata_in;
}

void CACHE::prefetcher_final_stats() {}

void CACHE::prefetcher_cycle_operate() {}
void CACHE::prefetcher_cache_eviction(uint64_t addr, uint64_t paddr) {}