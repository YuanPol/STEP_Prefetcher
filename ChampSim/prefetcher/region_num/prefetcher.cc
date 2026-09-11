/* Prefetcher [https://parsa.epfl.ch/stems/papers/isca06.pdf] */
/* PC+Offset */

#include "cache.h"
#include <bits/stdc++.h>
#include "custom_util.h"
#include "prefetcher.h"

using namespace std;

namespace {
std::vector<spb::Prefetcher> prefetchers;
double roi_match_probs[NUM_CPUS];
} // namespace

void CACHE::prefetcher_initialize() {
    std::cout << NAME << " Prefetcher prefetcher" << std::endl;
    if (cpu != 0)
        return;

    /* create prefetcher for all cores */
    assert(PAGE_SIZE % REGION_SIZE == 0);
    prefetchers = std::vector<spb::Prefetcher>(NUM_CPUS, spb::Prefetcher(REGION_SIZE >> LOG2_BLOCK_SIZE, ADDR_WIDTH, PC_WIDTH, PHT_SIZE, FT_SIZE, FT_WAY, AT_SIZE, AT_WAY, PB_SIZE));
}

uint32_t CACHE::prefetcher_cache_operate(uint64_t addr, uint64_t ip, uint8_t cache_hit, uint8_t type, uint32_t metadata_in) {
    /* call prefetcher and send prefetches */
    uint64_t block_number = addr >> LOG2_BLOCK_SIZE;

    prefetchers[cpu].access(block_number, ip);

    prefetchers[cpu].prefetch(this, block_number);

    return metadata_in;
}

uint32_t CACHE::prefetcher_cache_fill(uint64_t addr, uint32_t set, uint32_t way, uint8_t prefetch, uint64_t evicted_addr, uint32_t metadata_in) {
    uint64_t evicted_block = evicted_addr >> LOG2_BLOCK_SIZE;

    /* inform all spb modules of the eviction */
    for (int i = 0; i < NUM_CPUS; i += 1)
        prefetchers[i].eviction(evicted_block);
    return metadata_in;
}

void CACHE::prefetcher_cycle_operate() {}

void CACHE::prefetcher_final_stats() {
    cout << "* CPU " << cpu << " Total PHT Match Probability: " << prefetchers[cpu].get_match_prob() << endl;
    prefetchers[cpu].log();
}
