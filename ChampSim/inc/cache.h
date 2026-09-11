/*
 *    Copyright 2023 The ChampSim Contributors
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#ifndef CACHE_H
#define CACHE_H

#include <array>
#include <bitset>
#include <cassert>
#include <deque>
#include <functional>
#include <list>
#include <string>
#include <vector>

#include "champsim.h"
#include "champsim_constants.h"
#include "memory_class.h"
#include "operable.h"

// #define BERTI

#ifdef BERTI
extern void notify_prefetch(uint64_t addr, uint64_t tag, uint32_t cpu, uint64_t cycle);
#endif

#define __pf_type(pf_metadata) (pf_metadata & PF_TYPE_MASK)
#define __pf_dest(pf_metadata) ((pf_metadata & PF_DEST_MASK) >> 30)
#define __pf_sour(pf_metadata) ((pf_metadata & PF_SOUR_MASK) >> 28)

#define __add_pf_dest_level(pf_metadata, level) (pf_metadata | (level << 30))
#define __add_pf_sour_level(pf_metadata, level) (pf_metadata | (level << 28))
#define __decode_ipcp_type(pf_metadata) ((pf_metadata & 0x1E00) >> 9)

#define __pf_stride(pf_metadata) ((pf_metadata & PF_STRIDE_MASK) >> 27)
#define __add_pf_stride(pf_metadata) (pf_metadata | (1UL << 27))

#define __pf_first_offset(pf_metadata) ((pf_metadata & PF_FO_MASK) >> 26)
#define __add_pf_first_offset(pf_metadata) (pf_metadata | (1UL << 26))

#define __pf_second_offset(pf_metadata) ((pf_metadata & PF_SO_MASK) >> 25)
#define __add_pf_second_offset(pf_metadata) (pf_metadata | (1UL << 25))

#define __pf_third_offset(pf_metadata) ((pf_metadata & PF_TO_MASK) >> 24)
#define __add_pf_third_offset(pf_metadata) (pf_metadata | (1UL << 24))

#define __pf_stream(pf_metadata) ((pf_metadata & PF_ST_MASK) >> 20)
#define __add_pf_stream(pf_metadata) (pf_metadata | (1UL << 20))

constexpr uint32_t PF_TYPE_MASK = 3;
constexpr uint32_t PF_DEST_MASK = (1UL << 30) | (1UL << 31);
constexpr uint32_t PF_SOUR_MASK = (1UL << 28) | (1UL << 29);
constexpr uint32_t PF_STRIDE_MASK = (1UL << 27);
constexpr uint32_t PF_FO_MASK = (1UL << 26);
constexpr uint32_t PF_SO_MASK = (1UL << 25);
constexpr uint32_t PF_TO_MASK = (1UL << 24);
constexpr uint32_t PF_ST_MASK = (1UL << 20);

struct cache_stats {
    std::string name;
    // prefetch stats
    uint64_t pf_requested = 0;
    uint64_t pf_issued = 0;
    uint64_t pf_useful = 0;
    uint64_t pf_useless = 0;
    uint64_t pf_fill = 0;

    // stride prefetch stats
    uint64_t pf_stride_requested = 0;
    uint64_t pf_stride_issued = 0;
    uint64_t pf_stride_useful = 0;
    uint64_t pf_stride_useless = 0;
    uint64_t pf_stride_fill = 0;
    uint64_t pf_stride_late = 0;

    // 1st offset prefetch stats
    uint64_t pf_first_offset_requested = 0;
    uint64_t pf_first_offset_issued = 0;
    uint64_t pf_first_offset_useful = 0;
    uint64_t pf_first_offset_useless = 0;
    uint64_t pf_first_offset_fill = 0;
    uint64_t pf_first_offset_late = 0;

    // 2nd prefetch stats
    uint64_t pf_second_offset_requested = 0;
    uint64_t pf_second_offset_issued = 0;
    uint64_t pf_second_offset_useful = 0;
    uint64_t pf_second_offset_useless = 0;
    uint64_t pf_second_offset_fill = 0;
    uint64_t pf_second_offset_late = 0;

    // 3rd prefetch stats
    uint64_t pf_third_offset_requested = 0;
    uint64_t pf_third_offset_issued = 0;
    uint64_t pf_third_offset_useful = 0;
    uint64_t pf_third_offset_useless = 0;
    uint64_t pf_third_offset_fill = 0;
    uint64_t pf_third_offset_late = 0;

    // stream prefetch stats
    uint64_t pf_stream_requested = 0;
    uint64_t pf_stream_issued = 0;
    uint64_t pf_stream_useful = 0;
    uint64_t pf_stream_useless = 0;
    uint64_t pf_stream_fill = 0;
    uint64_t pf_stream_late = 0;

    // trigger
    uint64_t total_trigger = 0;
    uint64_t pht_trigger = 0;
    uint64_t pc_trigger = 0;
    uint64_t stride_trigger = 0;
    uint64_t ft_drop = 0;

    uint64_t pf_late = 0;
    uint64_t pf_useful_at_l2_from_l1 = 0;
    uint64_t pf_useless_at_l2_from_l1 = 0;
    uint64_t pf_late_at_l2_from_l1 = 0;
    uint64_t pf_useful_at_llc_from_l1 = 0;  // not used
    uint64_t pf_useless_at_llc_from_l1 = 0; // not used
    uint64_t pf_fill_this_level = 0;
    uint64_t l2_pf_to_l1 = 0;
    uint64_t mshr_full = 0;

    std::array<std::array<uint64_t, NUM_CPUS>, NUM_TYPES>
        hits = {};
    std::array<std::array<uint64_t, NUM_CPUS>, NUM_TYPES> misses = {};

    uint64_t total_miss_latency = 0;

    // ipcp
    uint64_t pref_useful[6] = {0}, pref_useless[6] = {0}, pref_filled[6] = {0}, pref_late[6] = {0};
};

struct cache_queue_stats {
    uint64_t RQ_ACCESS = 0;
    uint64_t RQ_MERGED = 0;
    uint64_t RQ_FULL = 0;
    uint64_t RQ_TO_CACHE = 0;
    uint64_t PQ_ACCESS = 0;
    uint64_t PQ_MERGED = 0;
    uint64_t PQ_FULL = 0;
    uint64_t PQ_TO_CACHE = 0;
    uint64_t WQ_ACCESS = 0;
    uint64_t WQ_MERGED = 0;
    uint64_t WQ_FULL = 0;
    uint64_t WQ_TO_CACHE = 0;
    uint64_t WQ_FORWARD = 0;
    uint64_t PTWQ_ACCESS = 0;
    uint64_t PTWQ_MERGED = 0;
    uint64_t PTWQ_FULL = 0;
    uint64_t PTWQ_TO_CACHE = 0;
};

class CACHE : public champsim::operable, public MemoryRequestConsumer, public MemoryRequestProducer {
    enum [[deprecated(
             "Prefetchers may not specify arbitrary fill levels. Use CACHE::prefetch_line(pf_addr, fill_this_level, prefetch_metadata) instead.")]] FILL_LEVEL { FILL_L1 = 1, FILL_L2 = 2, FILL_LLC = 4, FILL_DRC = 8, FILL_DRAM = 16 };

    bool try_hit(const PACKET& handle_pkt);
    bool handle_fill(const PACKET& fill_mshr);
    bool handle_miss(const PACKET& handle_pkt);
    bool handle_write(const PACKET& handle_pkt);

    struct BLOCK {
        bool valid = false;
        bool prefetch = false;
        bool dirty = false;

        uint64_t address = 0;
        uint64_t v_address = 0;
        uint64_t data = 0;

        uint32_t pf_metadata = 0;

        bool from_prefetch = false;
        uint8_t sour_level = 0; // 1 L1, 2 L2, 3 L3
        uint8_t dest_level = 0; // 1 L1, 2 L2, 3 L3
    };
    using set_type = std::vector<BLOCK>;

    std::pair<set_type::iterator, set_type::iterator> get_set_span(uint64_t address);
    std::pair<set_type::const_iterator, set_type::const_iterator> get_set_span(uint64_t address) const;
    std::size_t get_set_index(uint64_t address) const;

public:
    // DSPatch
    int bw = 0;
    // gaze
    int num_useful_gaze[4] = {0}, num_useless_gaze[4] = {0}, num_fill_gaze[4] = {0};

    struct NonTranslatingQueues : public champsim::operable {
        std::vector<PACKET> RQ, PQ, WQ, PTWQ;
        const std::size_t RQ_SIZE, PQ_SIZE, WQ_SIZE, PTWQ_SIZE;
        const uint64_t HIT_LATENCY;
        const unsigned OFFSET_BITS;
        const bool match_offset_bits;

        using stats_type = cache_queue_stats;

        stats_type sim_stats, roi_stats;

        NonTranslatingQueues(double freq_scale, std::size_t rq_size, std::size_t pq_size, std::size_t wq_size, std::size_t ptwq_size, uint64_t hit_latency,
                             unsigned offset_bits, bool match_offset) :
            champsim::operable(freq_scale),
            RQ_SIZE(rq_size), PQ_SIZE(pq_size), WQ_SIZE(wq_size), PTWQ_SIZE(ptwq_size), HIT_LATENCY(hit_latency),
            OFFSET_BITS(offset_bits), match_offset_bits(match_offset) {
            std::cout << "PQ SIZE: " << PQ_SIZE << std::endl;
            RQ.reserve(2 * RQ_SIZE);
            PQ.reserve(2 * PQ_SIZE);
            WQ.reserve(2 * WQ_SIZE);
            PTWQ.reserve(2 * PTWQ_SIZE);
        }
        void operate() override;

        template <typename R>
        bool do_add_queue(R& queue, std::size_t queue_size, const PACKET& packet);

        bool add_rq(const PACKET& packet);
        bool add_wq(const PACKET& packet);
        bool add_pq(const PACKET& packet);
        bool add_ptwq(const PACKET& packet);

        virtual bool is_ready(const PACKET& pkt) const;

        bool rq_has_ready() const;
        bool wq_has_ready() const;
        bool pq_has_ready() const;
        bool ptwq_has_ready() const;

        void begin_phase() override;
        void end_phase(unsigned cpu) override;

    private:
        void check_collision();
    };

    struct TranslatingQueues : public NonTranslatingQueues, public MemoryRequestProducer {
        void operate() override final;

        void issue_translation();
        void detect_misses();

        template <typename R>
        void do_issue_translation(R& queue);

        template <typename R>
        void do_detect_misses(R& queue);

        virtual bool is_ready(const PACKET& pkt) const override final;

        void return_data(const PACKET& packet) override final;

        using NonTranslatingQueues::NonTranslatingQueues;
    };

    uint32_t cpu = 0;
    const std::string NAME;
    const uint32_t NUM_SET, NUM_WAY, MSHR_SIZE;
    const uint32_t FILL_LATENCY;
    const unsigned OFFSET_BITS;
    set_type block{NUM_SET * NUM_WAY};
    const uint32_t PREFETCH_RESERVED_WAYS;
    const long int MAX_TAG, MAX_FILL;
    const bool prefetch_as_load;
    const bool match_offset_bits;
    const bool virtual_prefetch;
    bool ever_seen_data = false;
    const unsigned pref_activate_mask = (1 << static_cast<int>(LOAD)) | (1 << static_cast<int>(PREFETCH));

    using stats_type = cache_stats;

    stats_type sim_stats, roi_stats;

    NonTranslatingQueues& queues;
    std::deque<PACKET> MSHR;
    std::deque<PACKET> inflight_writes;

    int dpt_pf_counter, dpt_pf_useful, spt_pf_counter, spt_pf_useful = 0;

    // functions
    bool
    add_rq(const PACKET& packet) override final;
    bool add_wq(const PACKET& packet) override final;
    bool add_pq(const PACKET& packet) override final;
    bool add_ptwq(const PACKET& packet) override final;

    void return_data(const PACKET& packet) override final;
    void operate() override final;

    void initialize() override final;
    void begin_phase() override final;
    void end_phase(unsigned cpu) override final;

    std::size_t get_occupancy(uint8_t queue_type, uint64_t address) override final;
    std::size_t get_size(uint8_t queue_type, uint64_t address) override final;

    [[deprecated("Use get_set_index() instead.")]] uint64_t get_set(uint64_t address) const;
    [[deprecated("This function should not be used to access the blocks directly.")]] uint64_t get_way(uint64_t address, uint64_t set) const;

    uint64_t invalidate_entry(uint64_t inval_addr);
    int prefetch_line(uint64_t pf_addr, bool fill_this_level, uint32_t prefetch_metadata);

    [[deprecated("Use CACHE::prefetch_line(pf_addr, fill_this_level, prefetch_metadata) instead.")]] int
    prefetch_line(uint64_t ip, uint64_t base_addr, uint64_t pf_addr, bool fill_this_level, uint32_t prefetch_metadata);

    bool should_activate_prefetcher(const PACKET& pkt) const;
    std::pair<uint32_t, uint32_t> way_partition_bounds(uint32_t type) const
    {
        if (PREFETCH_RESERVED_WAYS == 0)
            return {0, NUM_WAY};

        if (type == PREFETCH)
            return {NUM_WAY - PREFETCH_RESERVED_WAYS, NUM_WAY};

        return {0, NUM_WAY - PREFETCH_RESERVED_WAYS};
    }

    void print_deadlock() override;

#include "cache_modules.inc"

    const std::bitset<NUM_REPLACEMENT_MODULES> repl_type;
    const std::bitset<NUM_PREFETCH_MODULES> pref_type;

    // constructor
    CACHE(std::string v1, double freq_scale, uint32_t v2, uint32_t v3, uint32_t v8, uint32_t fill_lat, long int max_tag, long int max_fill, unsigned offset_bits,
          bool pref_load, bool wq_full_addr, bool va_pref, uint32_t pf_reserved_ways, unsigned pref_mask, NonTranslatingQueues& queue_set, MemoryRequestConsumer* ll,
          std::bitset<NUM_PREFETCH_MODULES> pref, std::bitset<NUM_REPLACEMENT_MODULES> repl) :
        champsim::operable(freq_scale),
        MemoryRequestProducer(ll), NAME(v1), NUM_SET(v2), NUM_WAY(v3), MSHR_SIZE(v8), FILL_LATENCY(fill_lat),
        OFFSET_BITS(offset_bits),
        PREFETCH_RESERVED_WAYS((pf_reserved_ways == 0 || v3 == 0 || pf_reserved_ways < v3) ? pf_reserved_ways : (v3 - 1)),
        MAX_TAG(max_tag), MAX_FILL(max_fill), prefetch_as_load(pref_load), match_offset_bits(wq_full_addr), virtual_prefetch(va_pref),
        pref_activate_mask(pref_mask), queues(queue_set), repl_type(repl), pref_type(pref) {
    }
};

#endif
