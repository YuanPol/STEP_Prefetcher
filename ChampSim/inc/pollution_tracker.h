#ifndef POLLUTION_TRACKER_H
#define POLLUTION_TRACKER_H

#include <cstdint>
#include <vector>
#include <bitset>

namespace pollution_tracker {

class PollutionTracker {
public:
    class Entry {
        uint64_t ip;
        uint64_t address;
        int evicted_level;
        uint64_t in_counter;
    };

    void pollution_tracker_update(uint64_t ip, uint64_t address, int level, int hit, int prefetch);

    void counter_increment();

private:
    uint64_t _counter = 0;
    std::vector<Entry> _track_table;
};
} // namespace pollution_tracker

#endif
