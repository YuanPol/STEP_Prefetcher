#ifndef IPCP_L2_H
#define IPCP_L2_H

#include "cache.h"
#include "ooo_cpu.h"
#include <stdint.h>
#include "custom_util.h"

namespace ipcp_l2 {

#define DO_PREF
// #define SIG_DEBUG_PRINT_L2				    //Uncomment to enable debug prints
#ifdef SIG_DEBUG_PRINT_L2
#define SIG_DP(x) x
#else
#define SIG_DP(x)
#endif

constexpr int NUM_BLOOM_ENTRIES = 4096;
constexpr int NUM_IP_TABLE_L2_ENTRIES = 64;
constexpr int NUM_IP_INDEX_BITS_L2 = 6;
constexpr int NUM_IP_TAG_BITS_L2 = 9;
constexpr int S_TYPE = 1;    // stream
constexpr int CS_TYPE = 2;   // constant stride
constexpr int CPLX_TYPE = 3; // complex stride
constexpr int NL_TYPE = 4;   // next line

class STAT_COLLECT {
public:
    uint64_t useful;
    uint64_t filled;
    uint64_t misses;
    uint64_t polluted_misses;

    uint8_t bl_filled[NUM_BLOOM_ENTRIES];
    uint8_t bl_request[NUM_BLOOM_ENTRIES];

    STAT_COLLECT() {
        useful = 0;
        filled = 0;
        misses = 0;
        polluted_misses = 0;

        for (int i = 0; i < NUM_BLOOM_ENTRIES; i++) {
            bl_filled[i] = 0;
            bl_request[i] = 0;
        }
    };
};

class IP_TABLE {
public:
    uint64_t ip_tag;    // ip tag
    uint16_t ip_valid;  // ip valid bit
    uint32_t pref_type; // prefetch class type
    int stride;         // stride or stream

    IP_TABLE() {
        ip_tag = 0;
        ip_valid = 0;
        pref_type = 0;
        stride = 0;
    };
};

uint64_t hash_bloom_l2(uint64_t addr);
int decode_stride(uint32_t metadata);
int update_conf_l1(int stride, int pred_stride, int conf);
uint32_t encode_metadata_l2(int stride, uint16_t type, int spec_nl_l2);
void stat_col_L2(uint64_t addr, uint8_t cache_hit, uint8_t cpu, uint64_t ip);
} // namespace ipcp_l2

#endif