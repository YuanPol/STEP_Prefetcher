#ifndef CUSTOM_UTIL_H
#define CUSTOM_UTIL_H

#include "champsim.h"

#include <stdint.h>
#include <bits/stdc++.h>
#include <vector>
#include <unordered_map>
#include <functional>
#include <sstream>
#include <random>
#include <bitset>
#include <string>

namespace custom_util {

#define ADD(x, MAX) (x = x >= MAX ? x : x + 1)
#define ADD_ANY(x, y, MAX) (x = x + y >= MAX ? MAX : x + y)
#define TIME(x, y, MAX) (x = x * y > MAX ? MAX : x * y)
#define SHIFT(x, y, MAX) (x = (x << y) > MAX ? MAX : x << y)
#define ADD_BACKOFF(x, MAX) (x = (x == MAX ? x >> 1 : x + 1))
#define SUB(x, MIN) (x = (x <= MIN ? x : x - 1))
#define FLIP(x) (~x)

uint64_t get_hash(uint64_t key);
int transfer(int origin);
int count_bits(uint64_t a);
int count_bits(const std::vector<bool>& x);
uint64_t pattern_to_int(const std::vector<bool>& pattern);
std::vector<bool> pattern_convert2(const std::vector<int>& x);
std::vector<bool> pattern_convert2(const std::vector<uint32_t>& x);
std::vector<int> pattern_convert(const std::vector<bool>& x);
std::vector<bool> pattern_degrade(const std::vector<bool>& x, int level);
std::vector<bool> pattern_int2bool(std::vector<int> pattern);
double jaccard_similarity(std::vector<bool> pattern1, std::vector<bool> pattern2);
double jaccard_similarity(std::vector<bool> pattern1, std::vector<int> pattern2);
int pattern_distance(uint64_t p1, uint64_t p2);
uint64_t hash_index(uint64_t key, int index_len);
uint64_t my_hash_index(uint64_t key, int index_len, int discard_lsb_len);
void gen_random(char* s, const int len);
uint32_t folded_xor(uint64_t value, uint32_t num_folds);

template <class T>
std::string pattern_to_string(const std::vector<T>& pattern) {
    std::ostringstream oss;
    for (unsigned i = 0; i < pattern.size(); i += 1)
        oss << int(pattern[i]) << " ";
    return oss.str();
}

template <class T>
std::string
array_to_string(std::vector<T> array, bool hex = false, uint32_t size = 0) {
    std::stringstream ss;
    if (size == 0) size = array.size();
    for (uint32_t index = 0; index < size; ++index) {
        if (hex) {
            ss << std::hex << array[index] << std::dec;
        } else {
            ss << array[index];
        }
        ss << ",";
    }
    return ss.str();
}

template <class T>
std::vector<T> my_rotate(const std::vector<T>& x, int n) {
    std::vector<T> y;
    int len = x.size();
    if (len == 0)
        return y;
    n = n % len;
    for (int i = 0; i < len; i += 1)
        y.push_back(x[(i - n + len) % len]);
    return y;
}

class HashZoo {
public:
    static uint32_t jenkins(uint32_t key);
    static uint32_t knuth(uint32_t key);
    static uint32_t murmur3(uint32_t key);
    static uint32_t jenkins32(uint32_t key);
    static uint32_t hash32shift(uint32_t key);
    static uint32_t hash32shiftmult(uint32_t key);
    static uint32_t hash64shift(uint32_t key);
    static uint32_t hash5shift(uint32_t key);
    static uint32_t hash7shift(uint32_t key);
    static uint32_t Wang6shift(uint32_t key);
    static uint32_t Wang5shift(uint32_t key);
    static uint32_t Wang4shift(uint32_t key);
    static uint32_t Wang3shift(uint32_t key);

    static uint32_t three_hybrid1(uint32_t key);
    static uint32_t three_hybrid2(uint32_t key);
    static uint32_t three_hybrid3(uint32_t key);
    static uint32_t three_hybrid4(uint32_t key);
    static uint32_t three_hybrid5(uint32_t key);
    static uint32_t three_hybrid6(uint32_t key);
    static uint32_t three_hybrid7(uint32_t key);
    static uint32_t three_hybrid8(uint32_t key);
    static uint32_t three_hybrid9(uint32_t key);
    static uint32_t three_hybrid10(uint32_t key);
    static uint32_t three_hybrid11(uint32_t key);
    static uint32_t three_hybrid12(uint32_t key);

    static uint32_t four_hybrid1(uint32_t key);
    static uint32_t four_hybrid2(uint32_t key);
    static uint32_t four_hybrid3(uint32_t key);
    static uint32_t four_hybrid4(uint32_t key);
    static uint32_t four_hybrid5(uint32_t key);
    static uint32_t four_hybrid6(uint32_t key);
    static uint32_t four_hybrid7(uint32_t key);
    static uint32_t four_hybrid8(uint32_t key);
    static uint32_t four_hybrid9(uint32_t key);
    static uint32_t four_hybrid10(uint32_t key);
    static uint32_t four_hybrid11(uint32_t key);
    static uint32_t four_hybrid12(uint32_t key);

    static uint32_t getHash(uint32_t selector, uint32_t key);
};

/**
* A class for printing beautiful data tables.
* It's useful for logging the information contained in tabular structures.
*/
class Table {
public:
    Table(int width, int height) :
        width(width), height(height), cells(height, std::vector<std::string>(width)) {}

    void set_row(int row, const std::vector<std::string>& data, int start_col = 0);
    void set_col(int col, const std::vector<std::string>& data, int start_row = 0);
    void set_cell(int row, int col, std::string data);
    void set_cell(int row, int col, double data);
    void set_cell(int row, int col, int64_t data);
    void set_cell(int row, int col, int data);
    void set_cell(int row, int col, uint64_t data);

    std::string to_string();
    std::string data_row(int row, const std::vector<int>& widths);
    static std::string top_line(const std::vector<int>& widths);
    static std::string mid_line(const std::vector<int>& widths);
    static std::string bot_line(const std::vector<int>& widths);
    static std::string line(const std::vector<int>& widths, std::string left, std::string mid, std::string right);

private:
    unsigned width;
    unsigned height;
    std::vector<std::vector<std::string>> cells;
};

template <class T>
class InfiniteCache {
public:
    // Fake parameters for key generation
    InfiniteCache(int size, int num_ways, int debug_level = 0) :
        size(size), num_ways(num_ways), num_sets(size / num_ways), debug_level(debug_level) {
        /* calculate `index_len` (number of bits required to store the index) */
        for (int max_index = num_sets - 1; max_index > 0; max_index >>= 1)
            this->index_len += 1;
    }

    class Entry {
    public:
        uint64_t key;
        uint64_t index;
        uint64_t tag;
        bool valid;
        T data;
    };

    Entry* erase(uint64_t key) {
        Entry* entry = this->find(key);
        if (!entry)
            return nullptr;
        entry->valid = false;
        this->last_erased_entry = *entry;
        int num_erased = this->entries.erase(key);
        assert(num_erased == 1);
        return &this->last_erased_entry;
    }

    /**
     * @return The old state of the entry that was written to.
     */
    Entry insert(uint64_t key, const T& data) {
        Entry* entry = this->find(key);
        if (entry != nullptr) {
            Entry old_entry = *entry;
            entry->data = data;
            return old_entry;
        }
        entries[key] = {key, 0, key, true, data};
        return {};
    }

    Entry* find(uint64_t key) {
        auto it = this->entries.find(key);
        if (it == this->entries.end())
            return nullptr;
        Entry& entry = (*it).second;
        assert(entry.tag == key && entry.valid);
        return &entry;
    }

    /**
     * For debugging purposes.
     */
    std::string log(std::vector<std::string> headers, std::function<void(Entry&, Table&, int)> write_data) {
        Table table(headers.size(), entries.size() + 1);
        table.set_row(0, headers);
        unsigned i = 0;
        for (auto& x : this->entries)
            write_data(x.second, table, ++i);
        return table.to_string();
    }

    std::vector<Entry> get_valid_entries() {
        std::vector<Entry> res;
        res.reserve(this->entries.size());
        for (auto e : this->entries) {
            res.push_back(e.second);
        }
        return res;
    }

    std::string log(std::vector<std::string> headers) {
        std::vector<Entry> valid_entries = this->get_valid_entries();
        Table table(headers.size(), valid_entries.size() + 1);
        table.set_row(0, headers);
        for (unsigned i = 0; i < valid_entries.size(); i += 1)
            this->write_data(valid_entries[i], table, i + 1);
        return table.to_string();
    }

    int get_index_len() { return this->index_len; }
    void set_debug_level(int debug_level) { this->debug_level = debug_level; }

protected:
    virtual void write_data(Entry& entry, Table& table, int row) {}

    void rp_promote(uint64_t key) {}
    void rp_insert(uint64_t key) {}
    Entry last_erased_entry;
    std::unordered_map<uint64_t, Entry> entries;
    int debug_level = 0;
    int num_ways;
    int num_sets;
    int index_len;
    int size;
};

template <class T>
class InfiniteWayCache {
public:
    // Fake parameters for key generation
    InfiniteWayCache(int size, int num_ways, int debug_level = 0) :
        size(size), num_ways(num_ways), num_sets(size / num_ways),
        debug_level(debug_level), entries(size / num_ways) {
        /* calculate `index_len` (number of bits required to store the index) */
        for (int max_index = num_sets - 1; max_index > 0; max_index >>= 1)
            this->index_len += 1;
    }

    class Entry {
    public:
        uint64_t key;
        uint64_t index;
        uint64_t tag;
        bool valid;
        T data;
    };

    Entry* erase(uint64_t key) {
        Entry* entry = this->find(key);
        if (!entry)
            return nullptr;
        uint64_t tag = key / num_sets;
        uint64_t index = key % num_sets;
        entry->valid = false;
        this->last_erased_entry = *entry;
        int num_erased = this->entries[index].erase(tag);
        assert(num_erased == 1);
        return &this->last_erased_entry;
    }

    /**
     * @return The old state of the entry that was written to.
     */
    Entry insert(uint64_t key, const T& data) {
        Entry* entry = this->find(key);
        if (entry != nullptr) {
            Entry old_entry = *entry;
            entry->data = data;
            return old_entry;
        }
        uint64_t tag = key / num_sets;
        uint64_t index = key % num_sets;
        entries[index][tag] = {key, index, tag, true, data};
        return {};
    }

    Entry* find(uint64_t key) {
        uint64_t tag = key / num_sets;
        uint64_t index = key % num_sets;
        auto it = this->entries[index].find(tag);
        if (it == this->entries[index].end())
            return nullptr;
        Entry& entry = (*it).second;
        assert(entry.tag == tag && entry.valid);
        return &entry;
    }

    /**
     * For debugging purposes.
     */
    std::string log(std::vector<std::string> headers, std::function<void(Entry&, Table&, int)> write_data) {
        Table table(headers.size(), entries.size() + 1);
        table.set_row(0, headers);
        unsigned i = 0;
        for (auto& x : this->entries)
            write_data(x.second, table, ++i);
        return table.to_string();
    }

    std::vector<Entry> get_valid_entries() {
        std::vector<Entry> res;
        int size = 0;
        for (auto set : this->entries)
            size += set.size();
        res.reserve(size);
        for (auto set : this->entries) {
            for (auto e : set)
                res.push_back(e.second);
        }
        return res;
    }

    std::string log(std::vector<std::string> headers) {
        std::vector<Entry> valid_entries = this->get_valid_entries();
        Table table(headers.size(), valid_entries.size() + 1);
        table.set_row(0, headers);
        for (unsigned i = 0; i < valid_entries.size(); i += 1)
            this->write_data(valid_entries[i], table, i + 1);
        return table.to_string();
    }

    int get_index_len() { return this->index_len; }
    void set_debug_level(int debug_level) { this->debug_level = debug_level; }

protected:
    virtual void write_data(Entry& entry, Table& table, int row) {}

    void rp_promote(uint64_t key) {}
    void rp_insert(uint64_t key) {}
    Entry last_erased_entry;
    std::vector<std::unordered_map<uint64_t, Entry>> entries;
    int debug_level = 0;
    int num_ways;
    int num_sets;
    int index_len;
    int size;
};

template <class T>
class SetAssociativeCache {
public:
    class Entry {
    public:
        uint64_t key;
        uint64_t index;
        uint64_t tag;
        bool valid;
        T data;
    };

    SetAssociativeCache(int size, int num_ways, int debug_level = 0) :
        size(size), num_ways(num_ways), num_sets(size / num_ways), entries(num_sets, std::vector<Entry>(num_ways)),
        cams(num_sets, std::unordered_map<uint64_t, int>(num_ways)), debug_level(debug_level) {
        // assert(size % num_ways == 0);
        for (int i = 0; i < num_sets; i += 1)
            for (int j = 0; j < num_ways; j += 1)
                entries[i][j].valid = false;
        /* calculate `index_len` (number of bits required to store the index) */
        for (int max_index = num_sets - 1; max_index > 0; max_index >>= 1)
            this->index_len += 1;
    }

    /**
     * Invalidates the entry corresponding to the given key.
     * @return A pointer to the invalidated entry
     */
    Entry* erase(uint64_t key) {
        Entry* entry = this->find(key);
        uint64_t index = key & ((1 << this->index_len) - 1);
        uint64_t tag = key >> this->index_len;
        auto& cam = cams[index];
        int num_erased = cam.erase(tag);
        if (entry)
            entry->valid = false;
        // assert(entry ? num_erased == 1 : num_erased == 0);
        return entry;
    }

    /**
     * @return The old state of the entry that was updated
     */
    Entry insert(uint64_t key, const T& data) {
        Entry* entry = this->find(key);
        if (entry != nullptr) {
            Entry old_entry = *entry;
            entry->data = data;
            return old_entry;
        }
        uint64_t index = key & ((1 << this->index_len) - 1);
        uint64_t tag = key >> this->index_len;
        std::vector<Entry>& set = this->entries[index];
        int victim_way = -1;
        for (int i = 0; i < this->num_ways; i += 1)
            if (!set[i].valid) {
                victim_way = i;
                break;
            }
        if (victim_way == -1) {
            victim_way = this->select_victim(index);
        }
        Entry& victim = set[victim_way];
        Entry old_entry = victim;
        victim = {key, index, tag, true, data};
        auto& cam = cams[index];
        if (old_entry.valid) {
            int num_erased = cam.erase(old_entry.tag);
            // assert(num_erased == 1);
        }
        cam[tag] = victim_way;
        return old_entry;
    }

    Entry* find(uint64_t key) {
        uint64_t index = key & ((1 << this->index_len) - 1);
        uint64_t tag = key >> this->index_len;
        auto& cam = cams[index];
        if (cam.find(tag) == cam.end())
            return nullptr;
        int way = cam[tag];
        Entry& entry = this->entries[index][way];
        // assert(entry.tag == tag && entry.valid);
        if (!entry.valid)
            return nullptr;
        return &entry;
    }

    void flush() {
        for (int i = 0; i < num_sets; i += 1) {
            cams[i].clear();
            for (int j = 0; j < num_ways; j += 1)
                entries[i][j].valid = false;
        }
    }

    /**
     * Creates a table with the given headers and populates the rows by calling `write_data` on all
     * valid entries contained in the cache. This function makes it easy to visualize the contents
     * of a cache.
     * @return The constructed table as a std::string
     */
    std::string log(std::vector<std::string> headers) {
        std::vector<Entry> valid_entries = this->get_valid_entries();
        Table table(headers.size(), valid_entries.size() + 1);
        table.set_row(0, headers);
        for (unsigned i = 0; i < valid_entries.size(); i += 1)
            this->write_data(valid_entries[i], table, i + 1);
        return table.to_string();
    }

    int get_index_len() { return this->index_len; }

    void set_debug_level(int debug_level) { this->debug_level = debug_level; }

protected:
    /* should be overriden in children */
    virtual void write_data(Entry& entry, Table& table, int row) {}

    /**
     * @return The way of the selected victim
     */
    virtual int select_victim(uint64_t index) {
        /* random eviction policy if not overriden */
        return rand() % this->num_ways;
    }

    std::vector<Entry> get_valid_entries() {
        std::vector<Entry> valid_entries;
        for (int i = 0; i < num_sets; i += 1)
            for (int j = 0; j < num_ways; j += 1)
                if (entries[i][j].valid)
                    valid_entries.push_back(entries[i][j]);
        return valid_entries;
    }

    int size;
    int num_ways;
    int num_sets;
    int index_len = 0; /* in bits */
    std::vector<std::vector<Entry>> entries;
    std::vector<std::unordered_map<uint64_t, int>> cams;
    int debug_level = 0;
};

template <class T>
class LRUSetAssociativeCache : public SetAssociativeCache<T> {
    typedef SetAssociativeCache<T> Super;

public:
    LRUSetAssociativeCache(int size, int num_ways, int debug_level = 0) :
        Super(size, num_ways, debug_level), lru(this->num_sets, std::vector<uint64_t>(num_ways)) {}

    void set_mru(uint64_t key) { *this->get_lru(key) = this->t++; }

    void set_lru(uint64_t key) { *this->get_lru(key) = 0; }

    void rp_promote(uint64_t key) { set_mru(key); }

    void rp_insert(uint64_t key) { set_mru(key); }

protected:
    /* @override */
    int select_victim(uint64_t index) {
        std::vector<uint64_t>& lru_set = this->lru[index];
        return min_element(lru_set.begin(), lru_set.end()) - lru_set.begin();
    }

    uint64_t* get_lru(uint64_t key) {
        uint64_t index = key % this->num_sets;
        uint64_t tag = key / this->num_sets;
        // assert(this->cams[index].count(tag) == 1);
        int way = this->cams[index][tag];
        return &this->lru[index][way];
    }

    std::vector<std::vector<uint64_t>> lru;
    uint64_t t = 1;
};

template <class T>
class LFUSetAssociativeCache : public SetAssociativeCache<T> {
    typedef SetAssociativeCache<T> Super;

public:
    LFUSetAssociativeCache(int size, int num_ways, int debug_level = 0) :
        Super(size, num_ways, debug_level), frq_(this->num_sets, std::vector<uint64_t>(num_ways)) {}

    void rp_promote(uint64_t key) { (*this->get_frequency(key))++; }

    void rp_insert(uint64_t key) { (*this->get_frequency(key)) = 1; }

protected:
    /* @override */
    int select_victim(uint64_t index) {
        std::vector<uint64_t>& frq_set = this->frq_[index];
        return min_element(frq_set.begin(), frq_set.end()) - frq_set.begin();
    }

    uint64_t* get_frequency(uint64_t key) {
        uint64_t index = key % this->num_sets;
        uint64_t tag = key / this->num_sets;
        // assert(this->cams[index].count(tag) == 1);
        int way = this->cams[index][tag];
        return &this->frq_[index][way];
    }

    std::vector<std::vector<uint64_t>> frq_;
};

template <class T>
class FuzzSetAssociativeTable {
public:
    class Entry {
    public:
        uint64_t key;
        uint64_t index;
        uint64_t tag;
        bool valid;
        T data;
        uint64_t insert_time;
    };

    FuzzSetAssociativeTable(int size, int num_ways, int debug_level = 0) :
        size(size), num_ways(num_ways), num_sets(size / num_ways), entries(num_sets, std::vector<Entry>(num_ways)),
        cams(num_sets, std::unordered_map<uint64_t, int>(num_ways)), debug_level(debug_level) {
        // assert(size % num_ways == 0);
        for (int i = 0; i < num_sets; i += 1){
            for (int j = 0; j < num_ways; j += 1){
                entries[i][j].insert_time = 0;
                entries[i][j].valid = false;
            }
        }
        /* calculate `index_len` (number of bits required to store the index) */
        for (int max_index = num_sets - 1; max_index > 0; max_index >>= 1)
            this->index_len += 1;
    }

    /**
     * Invalidates the entry corresponding to the given key.
     * @return A pointer to the invalidated entry
     */
    Entry* erase(uint64_t key) {
        Entry* entry = this->find(key);
        uint64_t index = key & ((1 << this->index_len) - 1);
        uint64_t tag = key >> this->index_len;
        auto& cam = cams[index];
        int num_erased = cam.erase(tag);
        if (entry)
            entry->valid = false;
        // assert(entry ? num_erased == 1 : num_erased == 0);
        return entry;
    }


    Entry insert(uint64_t key, const T& data, uint64_t current_cycle) {
        Entry* entry = find(key);
        if (entry) {
            Entry old_entry = *entry;
            entry->data = data;
            entry->insert_time = current_cycle; 
            return old_entry;
        }
        uint64_t index = key & ((1 << index_len) - 1);
        uint64_t tag = key >> index_len;
        std::vector<Entry>& set = entries[index];
        int victim_way = -1;
        for (int i = 0; i < num_ways; i++) {
            if (!set[i].valid) {
                victim_way = i;
                break;
            }
        }
        if (victim_way == -1) {
            victim_way = select_victim(index);
        }
        Entry& victim = set[victim_way];
        Entry old_entry = victim;
        // Initialize new entry
        victim.key = key;
        victim.index = index;
        victim.tag = tag;
        victim.valid = true;
        victim.data = data;
        victim.insert_time = current_cycle;  // New entry, not sent
        auto& cam = cams[index];
        if (old_entry.valid) cam.erase(old_entry.tag);
        cam[tag] = victim_way;
        return old_entry;
    }

    virtual std::vector<Entry*> find_partial_two_offsets(uint64_t offset1, uint64_t offset2) {
        uint64_t index = offset1;
        if (index >= num_sets) return {};
        std::vector<Entry*> matches;
        for (int way = 0; way < num_ways; way++) {
            Entry* entry = &entries[index][way];
            if (entry->valid) {
                // Extract top 6 bits of 12-bit tag (offset2)
                uint64_t tag_low6 = entry->tag & ((1 << index_len) - 1);
                if (tag_low6 == offset2) {
                    matches.push_back(entry);
                }
            }
        }
        return matches;
    }

    virtual std::vector<Entry*> find_partial_one_offset(uint64_t offset1) {
        uint64_t index = offset1;
        if (index >= num_sets) return {};
        std::vector<Entry*> matches;
        for (int way = 0; way < num_ways; way++) {
            Entry* entry = &entries[index][way];
            if (entry->valid) {
                matches.push_back(entry);
            }
        }
        return matches;
    }

    Entry* find(uint64_t key) {
        uint64_t index = key & ((1 << this->index_len) - 1);
        uint64_t tag = key >> this->index_len;
        // std::cout << "Find " << index << tag << std::endl;
        auto& cam = cams[index];
        if (cam.find(tag) == cam.end()){
            // std::cout << "Return NULL 1" << std::endl;
            return nullptr;
        }
        int way = cam[tag];
        Entry& entry = this->entries[index][way];
        // assert(entry.tag == tag && entry.valid);
        if (!entry.valid){
            // std::cout << "Return NULL 2" << std::endl;
            return nullptr; 
        }
        // std::cout << "Return Entry" << std::endl;
        return &entry;
    }

    /**
     * Creates a table with the given headers and populates the rows by calling `write_data` on all
     * valid entries contained in the cache. This function makes it easy to visualize the contents
     * of a cache.
     * @return The constructed table as a std::string
     */
    std::string log(std::vector<std::string> headers) {
        std::vector<Entry> valid_entries = this->get_valid_entries();
        Table table(headers.size(), valid_entries.size() + 1);
        table.set_row(0, headers);
        for (unsigned i = 0; i < valid_entries.size(); i += 1)
            this->write_data(valid_entries[i], table, i + 1);
        return table.to_string();
    }

    int get_index_len() { return this->index_len; }

    void set_debug_level(int debug_level) { this->debug_level = debug_level; }

protected:
    /* should be overriden in children */
    virtual void write_data(Entry& entry, Table& table, int row) {}

    /**
     * @return The way of the selected victim
     */
    virtual int select_victim(uint64_t index) {
        /* random eviction policy if not overriden */
        return rand() % this->num_ways;
    }

    std::vector<Entry> get_valid_entries() {
        std::vector<Entry> valid_entries;
        for (int i = 0; i < num_sets; i += 1){
            for (int j = 0; j < num_ways; j += 1){
                if (entries[i][j].valid){
                    valid_entries.push_back(entries[i][j]);
                }
            }
        }
        return valid_entries;
    }

    int size;
    int num_ways;
    int num_sets;
    int index_len = 0; /* in bits */
    std::vector<std::vector<Entry>> entries;
    std::vector<std::unordered_map<uint64_t, int>> cams;
    int debug_level = 0;
};

template <class T>
class HybridAssocTable;

template <class T>
class LRUFuzzSetAssociativeTable : public FuzzSetAssociativeTable<T> {
    typedef FuzzSetAssociativeTable<T> Super;

public:
    
    friend class HybridAssocTable<T>;

    LRUFuzzSetAssociativeTable(int size, int num_ways, int debug_level = 0) :
        Super(size, num_ways, debug_level), lru(this->num_sets, std::vector<uint64_t>(num_ways)) {}

    void flush() {
        prefetched_groups.clear();
        for (int i = 0; i < Super::num_sets; i += 1) {
            Super::cams[i].clear();
            for (int j = 0; j < Super::num_ways; j += 1){
                Super::entries[i][j].valid = false;
                Super::entries[i][j].insert_time = 0;
            }
        }
    }

    void set_mru(uint64_t key) { *this->get_lru(key) = this->t++; }

    void set_lru(uint64_t key) { *this->get_lru(key) = 0; }

    void rp_promote(uint64_t key) { set_mru(key); }

    void rp_insert(uint64_t key) { set_mru(key); }

protected:
    /* @override */
    int select_victim(uint64_t index) {
        std::vector<uint64_t>& lru_set = this->lru[index];
        return min_element(lru_set.begin(), lru_set.end()) - lru_set.begin();
    }

    uint64_t* get_lru(uint64_t key) {
        uint64_t index = key % this->num_sets;
        uint64_t tag = key / this->num_sets;
        // assert(this->cams[index].count(tag) == 1);
        int way = this->cams[index][tag];
        return &this->lru[index][way];
    }

    std::unordered_set<uint64_t> prefetched_groups;
    std::vector<std::vector<uint64_t>> lru;
    uint64_t t = 1;
};


/**
 * @brief need test
 * 
 * @tparam T 
 */
template <class T>
class DynIndexSetAssociativeCache : public SetAssociativeCache<T> {
    typedef SetAssociativeCache<T> Super;

public:
    DynIndexSetAssociativeCache(int size, int num_ways, uint64_t dyn_index_mask, int max_dyn_index_score, int debug_level = 0) :
        dynamic_index_(size / num_ways, -1), dyn_index_mask_(dyn_index_mask), max_dyn_index_score_(max_dyn_index_score) {}

    int get_index(uint64_t key) {
        if (dynamic_index_.cam.find(key) != dynamic_index_.cam.end()) {
            return dynamic_index_.cam[key];
        }
        return -1;
    }

    int update_dyn_index(uint64_t key) {
        std::vector<int>::iterator item = min_element(dynamic_index_.score.begin(), dynamic_index_.score.end());
        *item = 1;
        int index = std::distance(dynamic_index_.score, item);
        dynamic_index_.cam[key] = index;
        return index;
    }

    typename Super::Entry* find(uint64_t key) {
        int index = get_index(key & dyn_index_mask_);
        if (index != -1) {
            uint64_t new_key = index | (key & ~(this->num_sets - 1));
            return Super::find(new_key);
        }

        return nullptr;
    }

    typename Super::Entry insert(uint64_t key, const T& data) {
        int index = get_index(key & dyn_index_mask_);
        if (index != -1) {
            uint64_t new_key = index | (key & ~(this->num_sets - 1));
            ADD(dynamic_index_.score[index], max_dyn_index_score_);
            return Super::insert(new_key, data);
        } else {
            index = update_dyn_index(key & dyn_index_mask_);
            uint64_t new_key = index | (key & ~(this->num_sets - 1));
            this->cams[index].clear();
            for (auto& e : this->entries[index]) {
                e.valid = false;
            }

            return Super::insert(new_key, data);
        }
    }

    typename Super::Entry erase(uint64_t key) {
        int index = get_index(key & dyn_index_mask_);
        if (index != -1) {
            uint64_t new_key = index | (key & ~(this->num_sets - 1));
            return Super::erase(new_key);
        }
        return nullptr;
    }

private:
    struct {
        std::vector<int> scores;
        std::unordered_map<int, int> cam;
    } dynamic_index_;

    uint64_t dyn_index_mask_;
    uint64_t max_dyn_index_score_;
};

template <class T>
class SRRIPSetAssociativeCache : public SetAssociativeCache<T> {
    typedef SetAssociativeCache<T> Super;

public:
    SRRIPSetAssociativeCache(int size, int num_ways, int debug_level = 0, int max_rrpv = 3) :
        Super(size, num_ways, debug_level), rrpv(this->num_sets, std::vector<uint64_t>(num_ways)),
        max_rrpv(max_rrpv) {}

    void rp_promote(uint64_t key) { *this->get_rrpv(key) = 0; }

    void rp_insert(uint64_t key) { *this->get_rrpv(key) = 2; }

protected:
    /* @override */
    int select_victim(uint64_t index) {
        std::vector<uint64_t>& rrpv_set = this->rrpv[index];
        for (;;) {
            for (int i = 0; i < this->num_ways; i++) {
                if (rrpv_set[i] >= max_rrpv) {
                    return i;
                }
            }
            aging(index);
        }
    }

    uint64_t* get_rrpv(uint64_t key) {
        uint64_t index = key % this->num_sets;
        uint64_t tag = key / this->num_sets;
        // assert(this->cams[index].count(tag) == 1);
        int way = this->cams[index][tag];
        return &this->rrpv[index][way];
    }

private:
    void aging(uint64_t index) {
        std::vector<uint64_t>& rrpv_set = this->rrpv[index];
        for (auto& r : rrpv_set) {
            ADD(r, max_rrpv);
        }
    }

    std::vector<std::vector<uint64_t>> rrpv;
    int max_rrpv;
};

template <class T>
class BIPSetAssociativeCache : public SetAssociativeCache<T> {
    typedef SetAssociativeCache<T> Super;

public:
    BIPSetAssociativeCache(int size, int num_ways, int debug_level = 0, double epsilon = 0.1) :
        Super(size, num_ways, debug_level), lru(this->num_sets, std::vector<uint64_t>(num_ways)),
        b_dist(epsilon) {}

    void set_mru(uint64_t key) { *this->get_lru(key) = this->t++; }

    void set_lru(uint64_t key) { *this->get_lru(key) = 0; }

    void rp_promote(uint64_t key) { set_mru(key); }

    void rp_insert(uint64_t key) { *this->get_lru(key) = b_dist(engine) ? t : t / 2; }

protected:
    /* @override */
    int select_victim(uint64_t index) {
        std::vector<uint64_t>& lru_set = this->lru[index];
        return min_element(lru_set.begin(), lru_set.end()) - lru_set.begin();
    }

    uint64_t* get_lru(uint64_t key) {
        uint64_t index = key % this->num_sets;
        uint64_t tag = key / this->num_sets;
        // assert(this->cams[index].count(tag) == 1);
        int way = this->cams[index][tag];
        return &this->lru[index][way];
    }

    std::vector<std::vector<uint64_t>> lru;
    uint64_t t = 1;

    std::default_random_engine engine;
    std::bernoulli_distribution b_dist;
};

template <class T>
class BRRIPSetAssociativeCache : public SetAssociativeCache<T> {
    typedef SetAssociativeCache<T> Super;

public:
    BRRIPSetAssociativeCache(int size, int num_ways, int debug_level = 0, int max_rrpv = 3, double epsilon = 0.1) :
        Super(size, num_ways, debug_level), rrpv(this->num_sets, std::vector<uint64_t>(num_ways)),
        max_rrpv(max_rrpv), b_dist(epsilon) {}

    void rp_promote(uint64_t key) { *this->get_rrpv(key) = 0; }

    void rp_insert(uint64_t key) { *this->get_rrpv(key) = b_dist(engine) ? 2 : 3; }

protected:
    /* @override */
    int select_victim(uint64_t index) {
        std::vector<uint64_t>& rrpv_set = this->rrpv[index];
        for (;;) {
            for (int i = 0; i < this->num_ways; i++) {
                if (rrpv_set[i] >= max_rrpv) {
                    return i;
                }
            }
            aging(index);
        }
    }

    uint64_t* get_rrpv(uint64_t key) {
        uint64_t index = key % this->num_sets;
        uint64_t tag = key / this->num_sets;
        // assert(this->cams[index].count(tag) == 1);
        int way = this->cams[index][tag];
        return &this->rrpv[index][way];
    }

private:
    void aging(uint64_t index) {
        std::vector<uint64_t>& rrpv_set = this->rrpv[index];
        for (auto& r : rrpv_set) {
            ADD(r, max_rrpv);
        }
    }

    std::vector<std::vector<uint64_t>> rrpv;
    int max_rrpv;
    std::default_random_engine engine;
    std::bernoulli_distribution b_dist;
};

template <class T>
class NMRUSetAssociativeCache : public SetAssociativeCache<T> {
    typedef SetAssociativeCache<T> Super;

public:
    NMRUSetAssociativeCache(int size, int num_ways) :
        Super(size, num_ways), mru(this->num_sets) {}

    void set_mru(uint64_t key) {
        uint64_t index = key % this->num_sets;
        uint64_t tag = key / this->num_sets;
        int way = this->cams[index][tag];
        this->mru[index] = way;
    }

protected:
    /* @override */
    int select_victim(uint64_t index) {
        int way = rand() % (this->num_ways - 1);
        if (way >= mru[index])
            way += 1;
        return way;
    }

    std::vector<int> mru;
};

template <class T>
class LRUFullyAssociativeCache : public LRUSetAssociativeCache<T> {
    typedef LRUSetAssociativeCache<T> Super;

public:
    LRUFullyAssociativeCache(int size) :
        Super(size, size) {}
};

template <class T>
class NMRUFullyAssociativeCache : public NMRUSetAssociativeCache<T> {
    typedef NMRUSetAssociativeCache<T> Super;

public:
    NMRUFullyAssociativeCache(int size) :
        Super(size, size) {}
};

template <class T>
class DirectMappedCache : public SetAssociativeCache<T> {
    typedef SetAssociativeCache<T> Super;

public:
    DirectMappedCache(int size) :
        Super(size, 1) {}
};

/** End Of Cache Framework **/

class ShiftRegister {
public:
    /* the maximum total capacity of this shift register is 64 bits */
    ShiftRegister(unsigned size = 4) :
        size(size), width(64 / size) {}

    void insert(int x);
    uint64_t get_code(unsigned le, unsigned ri);
    int get_value(int i);
    bool all_is_same_value();

private:
    unsigned size;
    unsigned width;
    uint64_t reg = 0;
};

class SaturatingCounter {
public:
    SaturatingCounter(int size = 2, int value = 0) :
        size(size), max((1 << size) - 1), cnt(value) {}

    int inc();
    int dec();
    int get_cnt();

    bool operator==(int value);
    bool operator>(SaturatingCounter& other);
    bool operator>=(SaturatingCounter& other);
    bool operator<(SaturatingCounter& other);
    bool operator<=(SaturatingCounter& other);

private:
    int size, max, cnt = 0;
};

template <class C>
class AddrMappingCache : public LRUSetAssociativeCache<std::vector<C>> {
    typedef LRUSetAssociativeCache<std::vector<C>> Super;

public:
    AddrMappingCache(int size, int num_ways, int entry_size) :
        Super(size, num_ways), entry_size(entry_size) {}

    uint64_t get_entry_group_key(uint64_t addr) {
        return addr / entry_size;
    }

    uint64_t get_entry_offset(uint64_t addr) {
        return addr % entry_size;
    }

    C*
    get_mapping_entry(uint64_t addr) {
        uint64_t key = get_entry_group_key(addr);
        uint64_t offset = get_entry_offset(addr);
        auto entry = this->find(key);
        if (entry) {
            return &entry->data[offset];
        } else {
            return nullptr;
        }
    }

protected:
    int entry_size;
};

template <class T>
inline T square(T x) { return x * x; }

/******************************************************************************/
/*                                   Pythia                                   */
/******************************************************************************/
constexpr int BITMAP_MAX_SIZE = 64;
typedef std::bitset<BITMAP_MAX_SIZE> Bitmap;

class BitmapHelper {
public:
    static uint64_t value(Bitmap bmp, uint32_t size = BITMAP_MAX_SIZE);
    static std::string to_string(Bitmap bmp, uint32_t size = BITMAP_MAX_SIZE);
    static uint32_t count_bits_set(Bitmap bmp, uint32_t size = BITMAP_MAX_SIZE);
    static uint32_t count_bits_same(Bitmap bmp1, Bitmap bmp2, uint32_t size = BITMAP_MAX_SIZE);
    static uint32_t count_bits_diff(Bitmap bmp1, Bitmap bmp2, uint32_t size = BITMAP_MAX_SIZE);
    static Bitmap rotate_left(Bitmap bmp, uint32_t amount, uint32_t size = BITMAP_MAX_SIZE);
    static Bitmap rotate_right(Bitmap bmp, uint32_t amount, uint32_t size = BITMAP_MAX_SIZE);
    static Bitmap compress(Bitmap bmp, uint32_t granularity, uint32_t size = BITMAP_MAX_SIZE);
    static Bitmap decompress(Bitmap bmp, uint32_t granularity, uint32_t size = BITMAP_MAX_SIZE);
    static Bitmap bitwise_or(Bitmap bmp1, Bitmap bmp2, uint32_t size = BITMAP_MAX_SIZE);
    static Bitmap bitwise_and(Bitmap bmp1, Bitmap bmp2, uint32_t size = BITMAP_MAX_SIZE);
};

class Prefetcher {
protected:
    std::string type;

public:
    Prefetcher(std::string _type) { type = _type; }
    Prefetcher() {}
    ~Prefetcher() {}
    std::string get_type() { return type; }
    virtual void invoke_prefetcher(uint64_t pc, uint64_t address, uint8_t cache_hit, uint8_t type, std::vector<uint64_t>& pref_addr) = 0;
    virtual void dump_stats() = 0;
    virtual void print_config() = 0;
};

std::string Binary(uint64_t x);

} // namespace custom_util

#endif