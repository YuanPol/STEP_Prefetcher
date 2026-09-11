#include "ghb.h"
#include "cache.h"

namespace {
constexpr int PREFETCH_DEGREE = 4;
constexpr int PREFETCH_LOOKAHEAD = 4;
ghb::IT index_table;
ghb::GHB global_history_buffer;
} // namespace

void CACHE::prefetcher_initialize() {
    std::cout << NAME << " GHB-based prefetcher" << std::endl;
}

/* For each L2 cache access (both hit and miss), the algorithm uses
the PC of the access to index into the IT and insert the cacheline address (say A) into the GHB.
Using the PC and the link pointers in GHB entries, the algorithm retrieves the sequence of last 3
addresses by this PC that accessed L2 cache. The stride is computed by taking the difference between
two consecutive addresses in the sequence. If two strides match (say d), the prefetcher simply issues
prefetch requests to cachelines A+ ld, A + (l + 1)d, A + (l + 2)d, ..., A + (l + n)d, where l is the prefetch
look-ahead and n is the prefetch degree. For your design, please statically set both l and n to 4. Please
also size the IT and GHB so that they are 256 entries each. For more detail on the GHB based stride
prefetcher implementation, please read the original GHB paper [10]. Doing so will be important for
you to implement Task 1 correctly
*/
uint32_t CACHE::prefetcher_cache_operate(uint64_t addr, uint64_t ip, uint8_t cache_hit, uint8_t type, uint32_t metadata_in) {
    uint64_t cl_addr = addr >> LOG2_BLOCK_SIZE;
    int debug = 1;

    // if(debug){
    //   std::cout << "addr: " << addr << ", cl_addr: " << cl_addr << ", ip: " << ip << std::endl;
    //   std::cout << "IndexTable: " << std::endl;
    //   for (auto it = index_table.begin(); it != index_table.end(); it++){
    //     std::cout << it->first << ' ' << it->second << ", " << std::endl;
    //   }
    //   std::cout << std::endl;

    //   std::cout << "GlobalHistoryBuffer: " << std::endl;
    //   for (auto it = global_history_buffer.begin(); it != global_history_buffer.end(); it++){
    //     std::cout << it->first << ' ' << it->second << ", " << std::endl;
    //   }
    //   std::cout << std::endl;
    // }

    auto it = ::index_table.find(ip);
    if (it == ::index_table.end()) // not in IT
    {
        ghb::IT::iterator it_IT = ::index_table.insert(ip);
        ghb::GHB::iterator it_GHB = ::global_history_buffer.insert(cl_addr, -1, ::index_table, it_IT); // insert into GHB

        return metadata_in;
    } else {                  // in IT
        if (it->second == -1) // check in ghb?
        {
            // no: insert into GHB
            ghb::GHB::iterator it_GHB = ::global_history_buffer.insert(cl_addr, -1, ::index_table, it); // insert into GHB
            return metadata_in;
        } else { // yes:
            // 1. insert into ghb
            ghb::GHB::iterator it_GHB = ::global_history_buffer.insert(cl_addr, it->second, ::index_table, it); // insert into GHB
            // 2. check patterns
            int stride = ::global_history_buffer.get_patterns();
            if (stride == 0)
                return metadata_in;
            else {
                for (int i = 0; i < ::PREFETCH_DEGREE; i++) {
                    uint64_t pf_addr = (cl_addr + (stride * (i + 1 + ::PREFETCH_LOOKAHEAD))) << LOG2_BLOCK_SIZE;

                    // only issue a prefetch if the prefetch address is in the same 4 KB page
                    // as the current demand access address
                    if ((pf_addr >> LOG2_PAGE_SIZE) != (addr >> LOG2_PAGE_SIZE))
                        break;

                    // std::cout << ip << ' ' << (addr >> LOG2_BLOCK_SIZE) << ' ' << (pf_addr >> LOG2_BLOCK_SIZE) << std::endl;
                    // check the MSHR occupancy to decide if we're going to prefetch to the L2 or LLC
                    if (get_occupancy(0, pf_addr) < (get_size(0, pf_addr) >> 1)) {
                        // std::cout << ip << ' ' << addr << ' ' << pf_addr << std::endl;
                        prefetch_line(ip, addr, pf_addr, true, metadata_in);
                    } else
                        prefetch_line(ip, addr, pf_addr, false, metadata_in);
                }
                // std::cout << std::endl;
            }
        }
    }

    return metadata_in;
}

uint32_t CACHE::prefetcher_cache_fill(uint64_t addr, uint32_t set, uint32_t way, uint8_t prefetch, uint64_t evicted_addr, uint32_t metadata_in) {
    return metadata_in;
}

void CACHE::prefetcher_cycle_operate() {}

void CACHE::prefetcher_cache_eviction(uint64_t addr, uint64_t paddr) {}

void CACHE::prefetcher_final_stats() {}
