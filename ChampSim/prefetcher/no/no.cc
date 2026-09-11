#include "cache.h"

void CACHE::prefetcher_initialize() {}

uint32_t CACHE::prefetcher_cache_operate(uint64_t addr, uint64_t ip, uint8_t cache_hit, uint8_t type, uint32_t metadata_in) { return metadata_in; }

uint32_t CACHE::prefetcher_cache_fill(uint64_t addr, uint32_t set, uint32_t way, uint8_t prefetch, uint64_t evicted_addr, uint32_t metadata_in) {
    return metadata_in;
}

void CACHE::prefetcher_cycle_operate() {}

void CACHE::prefetcher_cache_eviction(uint64_t addr, uint64_t paddr) {}


void CACHE::prefetcher_final_stats() {
    std::cout << NAME << std::endl;
    if (this->NAME.find("L2C") != -1) {
        std::cout << "Num Con Filled: " << num_fill_gaze[2] << std::endl;

        std::cout << "Num Con Useful: " << num_useful_gaze[2] + num_useful_gaze[3] << " Useless:" << num_useless_gaze[2] + num_useless_gaze[3] << " Accuracy: " << (100 * ((double)num_useful_gaze[2] + num_useful_gaze[3]) / (num_useful_gaze[2] + num_useless_gaze[2] + num_useful_gaze[3] + num_useless_gaze[3])) << std::endl;
    }
}
