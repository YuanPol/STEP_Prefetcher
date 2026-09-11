#include "pollution_tracker.h"

namespace pollution_tracker {

void PollutionTracker::counter_increment() {
    _counter++;
}

void PollutionTracker::pollution_tracker_update(uint64_t ip, uint64_t address, int level, int hit, int prefetch) {
    // if hit
    if (hit) {
        // if in table
    }
}

} // namespace pollution_tracker