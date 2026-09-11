#ifndef RECODER_H
#define RECODER_H

#include <vector>
#include <utility>
#include <stdint.h>

#include <iostream>
#include <fstream>

namespace recoder {
class Recoder {
public:
    void record_access(uint64_t ip, uint64_t addr, uint64_t cycle) {
        access_array.push_back(std::make_pair(std::make_pair(ip, addr), cycle));
    }
    void record_pref(uint64_t pref_addr, uint64_t cycle, uint64_t metadata) {
        pref_array.push_back(std::make_pair(pref_addr, cycle));
    }

    Recoder(std::string record_fold) :
        record_fold(record_fold) {}
    Recoder(std::string record_fold, int record_num) :
        record_num(record_num), record_fold(record_fold) {}

private:
    int record_num = 1e6;
    std::string record_fold;
    std::vector<std::pair<std::pair<uint64_t, uint64_t>, uint64_t>> access_array; // <<ip, addr>, cycle>
    std::vector<std::pair<uint64_t, uint64_t>> pref_array;                        // <pref_addr, cycle>
};
} // namespace recoder

#endif