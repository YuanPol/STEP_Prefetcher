#include "ipcp_l1.h"
#include "cache.h"
#include "environment.h"
#include "core_inst.inc"
#include <iostream>

// extern std::vector<std::reference_wrapper<O3_CPU>> ooo_cpu;
extern champsim::configured::generated_environment gen_environment{};

ipcp_l1::REGION_STREAM_TABLE rstable[NUM_CPUS][ipcp_l1::NUM_RST_ENTRIES];
int acc_filled[NUM_CPUS][5] = {0};
int acc_useful[NUM_CPUS][5] = {0};

int acc[NUM_CPUS][5] = {0};
int prefetch_degree[NUM_CPUS][5] = {0};
int num_conflicts = 0;
int test;
int sim_instructions = 0;

uint64_t eval_buffer[NUM_CPUS][1024] = {};
ipcp_l1::STAT_COLLECT stats[NUM_CPUS][5]; // for GS, CS, CPLX, NL and no class
ipcp_l1::IP_TABLE_L1 trackers_l1[NUM_CPUS][ipcp_l1::NUM_IP_TABLE_L1_ENTRIES];
ipcp_l1::CONST_STRIDE_PRED_TABLE CSPT_l1[NUM_CPUS][ipcp_l1::NUM_CSPT_ENTRIES];

std::vector<uint64_t> recent_request_filter; // to filter redundant prefetch requests

uint64_t prev_cpu_cycle[NUM_CPUS] = {0};
uint64_t num_misses[NUM_CPUS] = {0};
float mpki[NUM_CPUS] = {0};
int spec_nl[NUM_CPUS] = {0}, flag_nl[NUM_CPUS] = {0};
uint64_t num_access[NUM_CPUS] = {0};

int meta_counter[NUM_CPUS][4] = {0}; // for book-keeping
int total_count[NUM_CPUS] = {0};     // for book-keeping
int issue_counter[NUM_CPUS][5] = {0};

/* encode_metadata: The stride, prefetch class type and speculative nl fields are encoded in the metadata. */
uint32_t ipcp_l1::encode_metadata(int stride, uint16_t type, int spec_nl) {
    assert(stride < 64);
    uint32_t metadata = 0;

    // first encode stride in the last 8 bits of the metadata
    // stride: 6 bits + 1 sig
    // the lower 2 bits are used by mypref
    if (stride >= 0)
        metadata = stride;
    else
        metadata = ((-1 * stride) | 0b1000000);

    // encode the type of IP in the next 4 bits
    metadata = metadata | (type << 7);

    // encode the speculative NL bit in the next 1 bit
    metadata = metadata | (spec_nl << 11);

    metadata <<= 2;
    metadata = __add_pf_dest_level(metadata, 1);
    metadata = __add_pf_sour_level(metadata, 1);

    assert(__decode_ipcp_type(metadata) != 0);
    return metadata;
}
/* update_sig_l1: 7 bit signature is updated by performing a left-shift of 1 bit on the old signature and xoring the outcome with the delta*/

uint16_t ipcp_l1::update_sig_l1(uint16_t old_sig, int delta) {
    uint16_t new_sig = 0;
    int sig_delta = 0;

    // 7-bit sign magnitude form, since we need to track deltas from +63 to -63
    sig_delta = (delta < 0) ? (((-1) * delta) + (1 << 6)) : delta;
    new_sig = ((old_sig << 1) ^ sig_delta) & SIG_MASK;

    return new_sig;
}

/*If the actual stride and predicted stride are equal, then the confidence counter is incremented. */

int ipcp_l1::update_conf(int stride, int pred_stride, int conf) {
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

uint64_t ipcp_l1::hash_bloom(uint64_t addr) {
    uint64_t first_half, sec_half;
    first_half = addr & 0xFFF;
    sec_half = (addr >> 12) & 0xFFF;
    if ((first_half ^ sec_half) >= 4096)
        assert(0);
    return ((first_half ^ sec_half) & 0xFFF);
}

uint64_t ipcp_l1::hash_page(uint64_t addr) {
    uint64_t hash;
    while (addr != 0) {
        hash = hash ^ addr;
        addr = addr >> 6;
    }

    return hash & ((1 << NUM_PAGE_TAG_BITS) - 1);
}

void ipcp_l1::stat_col_L1(uint64_t addr, uint8_t cache_hit, uint8_t cpu, uint64_t ip) {
    uint64_t index = hash_bloom(addr);
    int ip_index = ip & IP_INDEX_MASK;
    uint16_t ip_tag = (ip >> NUM_IP_INDEX_BITS) & ((1 << NUM_IP_TAG_BITS) - 1);

    for (int i = 0; i < 5; i++) {
        if (cache_hit) {
            if (stats[cpu][i].bl_filled[index] == 1) {
                stats[cpu][i].useful++;
                stats[cpu][i].filled++;
                stats[cpu][i].bl_filled[index] = 0;
            }
        } else {
            if (ip_tag == trackers_l1[cpu][ip_index].ip_tag) {
                if (trackers_l1[cpu][ip_index].pref_type == i)
                    stats[cpu][i].misses++;
                if (stats[cpu][i].bl_filled[index] == 1) {
                    stats[cpu][i].polluted_misses++;
                    stats[cpu][i].filled++;
                    stats[cpu][i].bl_filled[index] = 0;
                }
            }
        }

        if (num_misses[cpu] % 1024 == 0) {
            for (int j = 0; j < NUM_BLOOM_ENTRIES; j++) {
                stats[cpu][i].filled += stats[cpu][i].bl_filled[j];
                stats[cpu][i].bl_filled[j] = 0;
                stats[cpu][i].bl_request[j] = 0;
            }
        }
    }
}

void CACHE::prefetcher_initialize() {
    std::cout << NAME << " IPCP_L1D prefetcher" << std::endl;
    for (int i = 0; i < ipcp_l1::NUM_RST_ENTRIES; i++)
        rstable[cpu][i].lru = i;
    for (int i = 0; i < NUM_CPUS; i++) {
        prefetch_degree[cpu][0] = 0;
        prefetch_degree[cpu][1] = 6;
        prefetch_degree[cpu][2] = 3;
        prefetch_degree[cpu][3] = 3;
        prefetch_degree[cpu][4] = 1;
    }
}

uint32_t CACHE::prefetcher_cache_operate(uint64_t addr, uint64_t ip, uint8_t cache_hit, uint8_t type, uint32_t metadata_in) {
    uint64_t curr_page = ipcp_l1::hash_page(addr >> LOG2_PAGE_SIZE); //current page
    uint64_t line_addr = addr >> LOG2_BLOCK_SIZE;                    //cache line address
    uint64_t line_offset = (addr >> LOG2_BLOCK_SIZE) & 0x3F;         //cache line offset
    uint16_t signature = 0, last_signature = 0;
    int spec_nl_threshold = 0;
    int num_prefs = 0;
    uint32_t metadata = 0;
    uint16_t ip_tag = (ip >> ipcp_l1::NUM_IP_INDEX_BITS) & ((1 << ipcp_l1::NUM_IP_TAG_BITS) - 1);
    uint64_t bl_index = 0;

    if (NUM_CPUS == 1) {
        spec_nl_threshold = 50;
    } else { //tightening the mpki constraints for multi-core
        spec_nl_threshold = 40;
    }

    // update miss counter
    if (cache_hit == 0 && !warmup)
        num_misses[cpu] += 1;
    num_access[cpu] += 1;
    ipcp_l1::stat_col_L1(addr, cache_hit, cpu, ip);
    // update spec nl bit when num misses crosses certain threshold

    // use access instead of instructions HERE!
    if (num_misses[cpu] % 256 == 0 && cache_hit == 0) {
        mpki[cpu] = ((num_misses[cpu] * 1000.0) / (gen_environment.cpu_view()[cpu].get().sim_instr()));

        if (mpki[cpu] > spec_nl_threshold)
            spec_nl[cpu] = 0;
        else
            spec_nl[cpu] = 1;
    }

    //Updating prefetch degree based on accuracy
    for (int i = 0; i < 5; i++) {
        if (sim_stats.pref_filled[i] % 256 == 0) {
            acc_useful[cpu][i] = acc_useful[cpu][i] / 2.0 + (sim_stats.pref_useful[i] - acc_useful[cpu][i]) / 2.0;
            acc_filled[cpu][i] = acc_filled[cpu][i] / 2.0 + (sim_stats.pref_filled[i] - acc_filled[cpu][i]) / 2.0;

            if (acc_filled[cpu][i] != 0)
                acc[cpu][i] = 100.0 * acc_useful[cpu][i] / (acc_filled[cpu][i]);
            else
                acc[cpu][i] = 60;

            if (acc[cpu][i] > 75) {
                prefetch_degree[cpu][i]++;
                if (i == 1) {
                    //For GS class, degree is incremented/decremented by 2.
                    prefetch_degree[cpu][i]++;
                    if (prefetch_degree[cpu][i] > 6)
                        prefetch_degree[cpu][i] = 6;
                } else if (prefetch_degree[cpu][i] > 3)
                    prefetch_degree[cpu][i] = 3;
            } else if (acc[cpu][i] < 40) {
                prefetch_degree[cpu][i]--;
                if (i == 1)
                    prefetch_degree[cpu][i]--;
                if (prefetch_degree[cpu][i] < 1)
                    prefetch_degree[cpu][i] = 1;
            }
        }
    }

    // calculate the index bit
    int index = ip & ipcp_l1::IP_INDEX_MASK;
    if (trackers_l1[cpu][index].ip_tag != ip_tag) {  // new/conflict IP
        if (trackers_l1[cpu][index].ip_valid == 0) { // if valid bit is zero, update with latest IP info
            num_conflicts++;
            trackers_l1[cpu][index].ip_tag = ip_tag;
            trackers_l1[cpu][index].last_vpage = curr_page;
            trackers_l1[cpu][index].last_line_offset = line_offset;
            trackers_l1[cpu][index].last_stride = 0;
            trackers_l1[cpu][index].signature = 0;
            trackers_l1[cpu][index].conf = 0;
            trackers_l1[cpu][index].str_valid = 0;
            trackers_l1[cpu][index].str_dir = 0;
            trackers_l1[cpu][index].pref_type = 0;
            trackers_l1[cpu][index].ip_valid = 1;
        } else { // otherwise, reset valid bit and leave the previous IP as it is
            trackers_l1[cpu][index].ip_valid = 0;
        }

        return metadata_in;
    } else { // if same IP encountered, set valid bit
        trackers_l1[cpu][index].ip_valid = 1;
    }

    // calculate the stride between the current cache line offset and the last cache line offset
    int64_t stride = 0;
    if (line_offset > trackers_l1[cpu][index].last_line_offset)
        stride = line_offset - trackers_l1[cpu][index].last_line_offset;
    else {
        stride = trackers_l1[cpu][index].last_line_offset - line_offset;
        stride *= -1;
    }

    // don't do anything if same address is seen twice in a row
    if (stride == 0)
        return metadata_in;

    int c = 0, flag = 0;

    //Checking if IP is already classified as a part of the GS class, so that for the new region we will set the tentative (spec_dense) bit.
    for (int i = 0; i < ipcp_l1::NUM_RST_ENTRIES; i++) {
        if (rstable[cpu][i].region_id == ((trackers_l1[cpu][index].last_vpage << 1) | (trackers_l1[cpu][index].last_line_offset >> 5))) {
            if (rstable[cpu][i].trained_dense == 1)
                flag = 1;
            break;
        }
    }
    for (c = 0; c < ipcp_l1::NUM_RST_ENTRIES; c++) {
        if (((curr_page << 1) | (line_offset >> 5)) == rstable[cpu][c].region_id) {
            if (rstable[cpu][c].line_access[line_offset & ipcp_l1::REGION_OFFSET_MASK] == 0) {
                rstable[cpu][c].line_access[line_offset & ipcp_l1::REGION_OFFSET_MASK] = 1;
            }

            if (rstable[cpu][c].pos_neg_count >= ipcp_l1::MAX_POS_NEG_COUNT || rstable[cpu][c].pos_neg_count <= 0) {
                rstable[cpu][c].pos_neg_count = ipcp_l1::MAX_POS_NEG_COUNT / 2;
            }

            if (stride > 0)
                rstable[cpu][c].pos_neg_count++;
            else
                rstable[cpu][c].pos_neg_count--;

            if (rstable[cpu][c].trained_dense == 0) {
                int count = 0;
                for (int i = 0; i < ipcp_l1::NUM_OF_LINES_IN_REGION; i++)
                    if (rstable[cpu][c].line_access[line_offset & ipcp_l1::REGION_OFFSET_MASK] == 1)
                        count++;

                if (count > 24) //75% of the cache lines in the region are accessed.
                {
                    rstable[cpu][c].trained_dense = 1;
                }
            }
            if (flag == 1)
                rstable[cpu][c].tentative_dense = 1;
            if (rstable[cpu][c].tentative_dense == 1 || rstable[cpu][c].trained_dense == 1) {
                if (rstable[cpu][c].pos_neg_count > (ipcp_l1::MAX_POS_NEG_COUNT / 2))
                    rstable[cpu][c].dir = 1; //1 for positive direction
                else
                    rstable[cpu][c].dir = 0; //0 for negative direction
                trackers_l1[cpu][index].str_valid = 1;

                trackers_l1[cpu][index].str_dir = rstable[cpu][c].dir;
            } else
                trackers_l1[cpu][index].str_valid = 0;

            break;
        }
    }
    //curr page has no entry in rstable. Then replace lru.
    if (c == ipcp_l1::NUM_RST_ENTRIES) {
        //check lru
        for (c = 0; c < ipcp_l1::NUM_RST_ENTRIES; c++) {
            if (rstable[cpu][c].lru == (ipcp_l1::NUM_RST_ENTRIES - 1))
                break;
        }
        for (int i = 0; i < ipcp_l1::NUM_RST_ENTRIES; i++) {
            if (rstable[cpu][i].lru < rstable[cpu][c].lru)
                rstable[cpu][i].lru++;
        }
        if (flag == 1)
            rstable[cpu][c].tentative_dense = 1;
        else
            rstable[cpu][c].tentative_dense = 0;

        rstable[cpu][c].region_id = (curr_page << 1) | (line_offset >> 5);
        rstable[cpu][c].trained_dense = 0;
        rstable[cpu][c].pos_neg_count = ipcp_l1::MAX_POS_NEG_COUNT / 2;
        rstable[cpu][c].dir = 0;
        rstable[cpu][c].lru = 0;
        for (int i = 0; i < ipcp_l1::NUM_OF_LINES_IN_REGION; i++)
            rstable[cpu][c].line_access[i] = 0;
    }

    // page boundary learning
    if (curr_page != trackers_l1[cpu][index].last_vpage) {
        test++;
        if (stride < 0)
            stride += ipcp_l1::NUM_OF_LINES_IN_REGION;
        else
            stride -= ipcp_l1::NUM_OF_LINES_IN_REGION;
    }

    // update constant stride(CS) confidence
    trackers_l1[cpu][index].conf = ipcp_l1::update_conf(stride, trackers_l1[cpu][index].last_stride, trackers_l1[cpu][index].conf);

    // update CS only if confidence is zero
    if (trackers_l1[cpu][index].conf == 0)
        trackers_l1[cpu][index].last_stride = stride;

    last_signature = trackers_l1[cpu][index].signature;
    // update complex stride(CPLX) confidence
    CSPT_l1[cpu][last_signature].conf = ipcp_l1::update_conf(stride, CSPT_l1[cpu][last_signature].stride, CSPT_l1[cpu][last_signature].conf);

    // update CPLX only if confidence is zero
    if (CSPT_l1[cpu][last_signature].conf == 0)
        CSPT_l1[cpu][last_signature].stride = stride;

    // calculate and update new signature in IP table
    signature = ipcp_l1::update_sig_l1(last_signature, stride);
    trackers_l1[cpu][index].signature = signature;

    SIG_DP(
        cout << ip << ", " << cache_hit << ", " << line_addr << ", " << addr << ", " << stride << "; ";
        cout << last_signature << ", " << CSPT_l1[cpu][last_signature].stride << ", " << CSPT_l1[cpu][last_signature].conf << "; ";
        cout << trackers_l1[cpu][index].last_stride << ", " << stride << ", " << trackers_l1[cpu][index].conf << ", "
             << "; ";);

    if (trackers_l1[cpu][index].str_valid == 1) { // stream IP
                                                  // for stream, prefetch with twice the usual degree
        if (prefetch_degree[cpu][1] < 3)
            flag = 1;
        meta_counter[cpu][0]++;
        total_count[cpu]++;
        for (int i = 0; i < prefetch_degree[cpu][1]; i++) {
            uint64_t pf_address = 0;

            if (trackers_l1[cpu][index].str_dir == 1) { // +ve stream
                pf_address = (line_addr + i + 1) << LOG2_BLOCK_SIZE;
                metadata = ipcp_l1::encode_metadata(1, ipcp_l1::S_TYPE, spec_nl[cpu]); // stride is 1
                assert(__decode_ipcp_type(metadata) == ipcp_l1::S_TYPE);
            } else { // -ve stream
                pf_address = (line_addr - i - 1) << LOG2_BLOCK_SIZE;
                metadata = ipcp_l1::encode_metadata(-1, ipcp_l1::S_TYPE, spec_nl[cpu]); // stride is -1
                assert(__decode_ipcp_type(metadata) == ipcp_l1::S_TYPE);
            }

            if (acc[cpu][1] < 75) {
                metadata = ipcp_l1::encode_metadata(0, ipcp_l1::S_TYPE, spec_nl[cpu]);
                assert(__decode_ipcp_type(metadata) == ipcp_l1::S_TYPE);
            }
            // Check if prefetch address is in same 4 KB page
            if ((pf_address >> LOG2_PAGE_SIZE) != (addr >> LOG2_PAGE_SIZE)) {
                break;
            }

            trackers_l1[cpu][index].pref_type = ipcp_l1::S_TYPE;

#ifdef DO_PREF
            int found_in_filter = 0;
            for (int i = 0; i < recent_request_filter.size(); i++) {
                if (recent_request_filter[i] == ((pf_address >> 6) & ipcp_l1::RR_TAG_MASK)) {
                    // Prefetch address is present in RR filter
                    found_in_filter = 1;
                }
            }
            //Issue prefetch request only if prefetch address is not present in RR filter
            if (found_in_filter == 0) {
                if (prefetch_line(ip, addr, pf_address, true, metadata)) {
                    issue_counter[cpu][__decode_ipcp_type(metadata)]++;
                }
                //Add to RR filter
                recent_request_filter.push_back((pf_address >> 6) & ipcp_l1::RR_TAG_MASK);
                if (recent_request_filter.size() > ipcp_l1::NUM_OF_RR_ENTRIES)
                    recent_request_filter.erase(recent_request_filter.begin());
            }
#endif
            num_prefs++;
            SIG_DP(cout << "1, ");
        }
    } else
        flag = 1;

    if (trackers_l1[cpu][index].conf > 1 && trackers_l1[cpu][index].last_stride != 0 && flag == 1) { // CS IP
        meta_counter[cpu][1]++;
        total_count[cpu]++;

        if (prefetch_degree[cpu][2] < 2)
            flag = 1;
        else
            flag = 0;

        for (int i = 0; i < prefetch_degree[cpu][2]; i++) {
            uint64_t pf_address = (line_addr + (trackers_l1[cpu][index].last_stride * (i + 1))) << LOG2_BLOCK_SIZE;

            // Check if prefetch address is in same 4 KB page
            if ((pf_address >> LOG2_PAGE_SIZE) != (addr >> LOG2_PAGE_SIZE)) {
                break;
            }

            trackers_l1[cpu][index].pref_type = ipcp_l1::CS_TYPE;
            bl_index = ipcp_l1::hash_bloom(pf_address);
            stats[cpu][ipcp_l1::CS_TYPE].bl_request[bl_index] = 1;
            if (acc[cpu][2] > 75) {
                metadata = ipcp_l1::encode_metadata(trackers_l1[cpu][index].last_stride, ipcp_l1::CS_TYPE, spec_nl[cpu]);
                assert(__decode_ipcp_type(metadata) == ipcp_l1::CS_TYPE);
            } else {
                metadata = ipcp_l1::encode_metadata(0, ipcp_l1::CS_TYPE, spec_nl[cpu]);
                assert(__decode_ipcp_type(metadata) == ipcp_l1::CS_TYPE);
            }
// if(spec_nl[cpu] == 1)
#ifdef DO_PREF
            int found_in_filter = 0;
            for (int i = 0; i < recent_request_filter.size(); i++) {
                if (recent_request_filter[i] == ((pf_address >> 6) & ipcp_l1::RR_TAG_MASK)) {
                    // Prefetch address is present in RR filter
                    found_in_filter = 1;
                }
            }
            //Issue prefetch request only if prefetch address is not present in RR filter
            if (found_in_filter == 0) {
                if (prefetch_line(ip, addr, pf_address, true, metadata)) {
                    issue_counter[cpu][__decode_ipcp_type(metadata)]++;
                }
                //Add to RR filter
                recent_request_filter.push_back((pf_address >> 6) & ipcp_l1::RR_TAG_MASK);
                if (recent_request_filter.size() > ipcp_l1::NUM_OF_RR_ENTRIES)
                    recent_request_filter.erase(recent_request_filter.begin());
            }
#endif
            num_prefs++;
            SIG_DP(cout << trackers_l1[cpu][index].last_stride << ", ");
        }
    } else
        flag = 1;

    if (CSPT_l1[cpu][signature].conf >= 0 && CSPT_l1[cpu][signature].stride != 0 && flag == 1) { // if conf>=0, continue looking for stride
        int pref_offset = 0, i = 0;                                                              // CPLX IP
        meta_counter[cpu][2]++;
        total_count[cpu]++;

        for (i = 0; i < prefetch_degree[cpu][3] + ipcp_l1::CPLX_DIST; i++) {
            pref_offset += CSPT_l1[cpu][signature].stride;
            uint64_t pf_address = ((line_addr + pref_offset) << LOG2_BLOCK_SIZE);

            // Check if prefetch address is in same 4 KB page
            if (((pf_address >> LOG2_PAGE_SIZE) != (addr >> LOG2_PAGE_SIZE)) || (CSPT_l1[cpu][signature].conf == -1) || (CSPT_l1[cpu][signature].stride == 0)) {
                // if new entry in CSPT or stride is zero, break
                break;
            }

            // we are not prefetching at L2 for CPLX type, so encode stride as 0
            trackers_l1[cpu][index].pref_type = ipcp_l1::CPLX_TYPE;
            metadata = ipcp_l1::encode_metadata(0, ipcp_l1::CPLX_TYPE, spec_nl[cpu]);
            assert(__decode_ipcp_type(metadata) == ipcp_l1::CPLX_TYPE);
            if (CSPT_l1[cpu][signature].conf > 0 && i >= ipcp_l1::CPLX_DIST) { // prefetch only when conf>0 for CPLX
                bl_index = ipcp_l1::hash_bloom(pf_address);
                stats[cpu][ipcp_l1::CPLX_TYPE].bl_request[bl_index] = 1;
                trackers_l1[cpu][index].pref_type = 3;
#ifdef DO_PREF
                int found_in_filter = 0;
                for (int i = 0; i < recent_request_filter.size(); i++) {
                    if (recent_request_filter[i] == ((pf_address >> 6) & ipcp_l1::RR_TAG_MASK)) {
                        // Prefetch address is present in RR filter
                        found_in_filter = 1;
                    }
                }
                //Issue prefetch request only if prefetch address is not present in RR filter
                if (found_in_filter == 0) {
                    if (prefetch_line(ip, addr, pf_address, true, metadata)) {
                        issue_counter[cpu][__decode_ipcp_type(metadata)]++;
                    }
                    //Add to RR filter
                    recent_request_filter.push_back((pf_address >> 6) & ipcp_l1::RR_TAG_MASK);
                    if (recent_request_filter.size() > ipcp_l1::NUM_OF_RR_ENTRIES)
                        recent_request_filter.erase(recent_request_filter.begin());
                }
#endif
                num_prefs++;
                SIG_DP(cout << pref_offset << ", ");
            }
            signature = ipcp_l1::update_sig_l1(signature, CSPT_l1[cpu][signature].stride);
        }
    }

    // if no prefetches are issued till now, speculatively issue a next_line prefetch
    if (num_prefs == 0 && spec_nl[cpu] == 1) {
        if (flag_nl[cpu] == 0)
            flag_nl[cpu] = 1;
        else {
            uint64_t pf_address = ((addr >> LOG2_BLOCK_SIZE) + 1) << LOG2_BLOCK_SIZE;
            if ((pf_address >> LOG2_PAGE_SIZE) != (addr >> LOG2_PAGE_SIZE)) {
                // update the IP table entries and return metadata_in if NL request is not to the same 4 KB page
                trackers_l1[cpu][index].last_line_offset = line_offset;
                trackers_l1[cpu][index].last_vpage = curr_page;
                return metadata_in;
            }
            bl_index = ipcp_l1::hash_bloom(pf_address);
            stats[cpu][ipcp_l1::NL_TYPE].bl_request[bl_index] = 1;
            metadata = ipcp_l1::encode_metadata(1, ipcp_l1::NL_TYPE, spec_nl[cpu]);
            assert(__decode_ipcp_type(metadata) == ipcp_l1::NL_TYPE);
#ifdef DO_PREF
            int found_in_filter = 0;
            for (int i = 0; i < recent_request_filter.size(); i++) {
                if (recent_request_filter[i] == ((pf_address >> 6) & ipcp_l1::RR_TAG_MASK)) {
                    // Prefetch address is present in RR filter
                    found_in_filter = 1;
                }
            }
            //Issue prefetch request only if prefetch address is not present in RR filter
            if (found_in_filter == 0) {
                if (prefetch_line(ip, addr, pf_address, true, metadata)) {
                    issue_counter[cpu][__decode_ipcp_type(metadata)]++;
                }
                //Add to RR filter
                recent_request_filter.push_back((pf_address >> 6) & ipcp_l1::RR_TAG_MASK);
                if (recent_request_filter.size() > ipcp_l1::NUM_OF_RR_ENTRIES)
                    recent_request_filter.erase(recent_request_filter.begin());
            }
#endif
            trackers_l1[cpu][index].pref_type = ipcp_l1::NL_TYPE;
            meta_counter[cpu][3]++;
            total_count[cpu]++;
            SIG_DP(cout << "1, ");

            if (acc[cpu][4] < 40)
                flag_nl[cpu] = 0;
        } // NL IP
    }

    SIG_DP(cout << endl);

    // update the IP table entries
    trackers_l1[cpu][index].last_line_offset = line_offset;
    trackers_l1[cpu][index].last_vpage = curr_page;

    return metadata_in;
}

uint32_t CACHE::prefetcher_cache_fill(uint64_t addr, uint32_t set, uint32_t way, uint8_t prefetch, uint64_t evicted_addr, uint32_t metadata_in) {
    if (prefetch) {
        uint32_t pref_type = __decode_ipcp_type(metadata_in);

        uint64_t index = ipcp_l1::hash_bloom(addr);
        if (stats[cpu][pref_type].bl_request[index] == 1) {
            stats[cpu][pref_type].bl_filled[index] = 1;
            stats[cpu][pref_type].bl_request[index] = 0;
        }
    }
    return metadata_in;
}

void CACHE::prefetcher_final_stats() {
    std::cout << std::endl;

    uint64_t total_request = 0, total_polluted = 0, total_useful = 0, total_late = 0;

    for (int i = 0; i < 5; i++) {
        // total_request += ipcp_stats::pref_filled[cpu][i];
        total_polluted += stats[cpu][i].polluted_misses;
        // total_useful += ipcp_stats::pref_useful[cpu][i];
        // total_late += ipcp_stats::pref_late[cpu][i];
    }

    std::cout << "stream: " << std::endl;
    std::cout << "stream:times selected: " << meta_counter[cpu][0] << std::endl;
    std::cout << "stream:pref_issued: " << issue_counter[cpu][1] << std::endl;
    std::cout << "stream:pref_filled: " << sim_stats.pref_filled[1] << std::endl;
    std::cout << "stream:pref_useful: " << sim_stats.pref_useful[1] << std::endl;
    std::cout << "stream:pref_useless: " << sim_stats.pref_useless[1] << std::endl;
    std::cout << "stream:pref_late: " << sim_stats.pref_late[1] << std::endl;
    std::cout << "stream:misses: " << stats[cpu][1].misses << std::endl;
    std::cout << "stream:misses_by_poll: " << stats[cpu][1].polluted_misses << std::endl;
    std::cout << std::endl;

    std::cout << "CS: " << std::endl;
    std::cout << "CS:times selected: " << meta_counter[cpu][1] << std::endl;
    std::cout << "CS:pref_issued: " << issue_counter[cpu][2] << std::endl;
    std::cout << "CS:pref_filled: " << sim_stats.pref_filled[2] << std::endl;
    std::cout << "CS:pref_useful: " << sim_stats.pref_useful[2] << std::endl;
    std::cout << "CS:pref_useless: " << sim_stats.pref_useless[2] << std::endl;
    std::cout << "CS:pref_late: " << sim_stats.pref_late[2] << std::endl;
    std::cout << "CS:misses: " << stats[cpu][2].misses << std::endl;
    std::cout << "CS:misses_by_poll: " << stats[cpu][2].polluted_misses << std::endl;
    std::cout << std::endl;

    std::cout << "CPLX: " << std::endl;
    std::cout << "CPLX:times selected: " << meta_counter[cpu][2] << std::endl;
    std::cout << "CPLX:pref_issued: " << issue_counter[cpu][3] << std::endl;
    std::cout << "CPLX:pref_filled: " << sim_stats.pref_filled[3] << std::endl;
    std::cout << "CPLX:pref_useful: " << sim_stats.pref_useful[3] << std::endl;
    std::cout << "CPLX:pref_useless: " << sim_stats.pref_useless[3] << std::endl;
    std::cout << "CPLX:pref_late: " << sim_stats.pref_late[3] << std::endl;
    std::cout << "CPLX:misses: " << stats[cpu][3].misses << std::endl;
    std::cout << "CPLX:misses_by_poll: " << stats[cpu][3].polluted_misses << std::endl;
    std::cout << std::endl;

    std::cout << "NL_L1: " << std::endl;
    std::cout << "NL:times selected: " << meta_counter[cpu][3] << std::endl;
    std::cout << "NL:pref_issued: " << issue_counter[cpu][4] << std::endl;
    std::cout << "NL:pref_filled: " << sim_stats.pref_filled[4] << std::endl;
    std::cout << "NL:pref_useful: " << sim_stats.pref_useful[4] << std::endl;
    std::cout << "NL:pref_useless: " << sim_stats.pref_useless[4] << std::endl;
    std::cout << "NL:pref_late: " << sim_stats.pref_late[4] << std::endl;
    std::cout << "NL:misses: " << stats[cpu][4].misses << std::endl;
    std::cout << "NL:misses_by_poll: " << stats[cpu][4].polluted_misses << std::endl;
    std::cout << std::endl;

    std::cout << "conflicts: " << num_conflicts << std::endl;
    std::cout << std::endl;

    std::cout << "test: " << test << std::endl;

    int ipcp_useful = 0, ipcp_useless = 0, ipcp_fill = 0;
    for (int i = 1; i < 5; i++) {
        ipcp_useful += sim_stats.pref_useful[i];
        ipcp_useless += sim_stats.pref_useless[i];
        ipcp_fill += sim_stats.pref_filled[i];
    }

    std::cout << sim_stats.pf_useful << ", " << ipcp_useful << ". " << sim_stats.pf_useless << ", " << ipcp_useless << ". " << sim_stats.pf_fill << ", " << ipcp_fill << ". " << std::endl;
}

void CACHE::prefetcher_cycle_operate() {}
void CACHE::prefetcher_cache_eviction(uint64_t addr, uint64_t paddr) {}
