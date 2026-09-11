#include <algorithm>
#include <map>
#include <vector>

#include "cache.h"

// std::map<CACHE*, std::vector<uint64_t>> last_used_cycles;
std::map<std::string, std::vector<uint64_t>> last_used_cycles;

void CACHE::initialize_replacement() {
    last_used_cycles.insert({NAME, std::vector<uint64_t>(NUM_SET * NUM_WAY)});
    // std::cout << NAME << " " << last_used_cycles.size() << std::endl;
}

uint32_t CACHE::find_victim(uint32_t triggering_cpu, uint64_t instr_id, uint32_t set, const BLOCK* current_set, uint64_t ip, uint64_t full_addr, uint32_t type) {
    auto set_begin = std::next(std::begin(last_used_cycles[NAME]), set * NUM_WAY);
    auto [way_begin, way_end] = way_partition_bounds(type);
    auto begin = std::next(set_begin, static_cast<std::vector<uint64_t>::difference_type>(way_begin));
    auto end = std::next(set_begin, static_cast<std::vector<uint64_t>::difference_type>(way_end));

    // Find the way whose last use cycle is most distant
    auto victim = std::min_element(begin, end);
    assert(begin <= victim);
    assert(victim < end);
    return static_cast<uint32_t>(std::distance(set_begin, victim)); // cast protected by prior asserts
}

void CACHE::update_replacement_state(uint32_t triggering_cpu, uint32_t set, uint32_t way, uint64_t full_addr, uint64_t ip, uint64_t victim_addr, uint32_t type,
                                     uint8_t hit) {
    // Mark the way as being used on the current cycle
    // std::cout << NAME << " repl update called " << last_used_cycles.size() << std::endl;
    // std::cout << cpu << std::endl;
    // std::cout << last_used_cycles[NAME].size() << std::endl;
    // std::cout << current_cycle << std::endl;
    if (!hit || type != WRITE) // Skip this for writeback hits
        last_used_cycles[NAME].at(set * NUM_WAY + way) = current_cycle;
}

void CACHE::replacement_final_stats() {}
