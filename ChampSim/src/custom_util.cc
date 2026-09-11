#include "custom_util.h"

#include <cmath>
#include <functional>

int custom_util::transfer(int origin) {
    return std::abs(origin) * origin;
}

uint64_t custom_util::get_hash(uint64_t key) {
    // Robert Jenkins' 32 bit mix function
    key += (key << 12);
    key ^= (key >> 22);
    key += (key << 4);
    key ^= (key >> 9);
    key += (key << 10);
    key ^= (key >> 2);
    key += (key << 7);
    key ^= (key >> 12);

    // Knuth's multiplicative method
    key = (key >> 3) * 2654435761;

    return key;
}

int custom_util::count_bits(uint64_t a) {
    int res = 0;
    for (int i = 0; i < 64; i++)
        if ((a >> i) & 1)
            res++;
    return res;
}

uint64_t
custom_util::pattern_to_int(const std::vector<bool>& pattern) {
    uint64_t result = 0;
    for (auto v : pattern) {
        result <<= 1;
        result |= int(v);
    }
    return result;
}

std::vector<bool>
custom_util::pattern_convert2(const std::vector<int>& x) {
    std::vector<bool> pattern;
    for (int i = 0; i < x.size(); i++) {
        pattern.push_back(x[i] != 0);
    }
    return pattern;
}

std::vector<bool>
custom_util::pattern_convert2(const std::vector<uint32_t>& x) {
    std::vector<bool> pattern;
    for (int i = 0; i < x.size(); i++) {
        pattern.push_back(x[i] != 0);
    }
    return pattern;
}

std::vector<int>
custom_util::pattern_convert(const std::vector<bool>& x) {
    std::vector<int> pattern(x.size(), 0);
    for (int i = 0; i < x.size(); i++) {
        pattern[i] = (x[i] ? 1 : 0);
    }
    return pattern;
}

int custom_util::count_bits(const std::vector<bool>& x) {
    int count = 0;
    for (auto b : x) {
        count += b;
    }
    return count;
}

double
custom_util::jaccard_similarity(std::vector<bool> pattern1, std::vector<bool> pattern2) {
    int a = pattern_to_int(pattern1), b = pattern_to_int(pattern2);
    return double(count_bits(a & b)) / double(count_bits(a | b));
}

std::vector<bool> custom_util::pattern_int2bool(std::vector<int> pattern) {
    std::vector<bool> pattern_bool(64, false);
    for (int i = 0; i < 64; i++)
        pattern_bool[i] = (pattern[i] ? true : false);
    return pattern_bool;
}

double
custom_util::jaccard_similarity(std::vector<bool> pattern1, std::vector<int> pattern2) {
    int l = 0, j = 0;
    for (int i = 0; i < pattern1.size(); i++) {
        l += pattern1[i] ? pattern2[i] : 0;
        j += int(pattern1[i]) > pattern2[i] ? int(pattern1[i]) : pattern2[i];
    }
    return double(l) / j;
}

int custom_util::pattern_distance(uint64_t p1, uint64_t p2) {
    return count_bits(p1 ^ p2);
}

uint64_t
custom_util::hash_index(uint64_t key, int index_len) {
    if (index_len == 0)
        return key;
    for (uint64_t tag = (key >> index_len); tag > 0; tag >>= index_len)
        key ^= tag & ((1 << index_len) - 1);
    return key;
}

uint64_t custom_util::my_hash_index(uint64_t key, int index_len, int discard_lsb_len) {
    key >>= discard_lsb_len;
    // key &= ((1ULL << 32) - 1);
    // key = custom_util::HashZoo::jenkins32(key);
    key &= ((1ULL << index_len) - 1);
    return key;
}

/* helper function */
void custom_util::gen_random(char* s, const int len) {
    static const char alphanum[] =
        "0123456789"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "abcdefghijklmnopqrstuvwxyz";

    for (int i = 0; i < len; ++i) {
        s[i] = alphanum[rand() % (sizeof(alphanum) - 1)];
    }

    s[len] = 0;
}

uint32_t custom_util::folded_xor(uint64_t value, uint32_t num_folds) {
    assert(num_folds > 1);
    assert((num_folds & (num_folds - 1)) == 0); /* has to be power of 2 */
    uint32_t mask = 0;
    uint32_t bits_in_fold = 64 / num_folds;
    if (num_folds == 2) {
        mask = 0xffffffff;
    } else {
        mask = (1ul << bits_in_fold) - 1;
    }
    uint32_t folded_value = 0;
    for (uint32_t fold = 0; fold < num_folds; ++fold) {
        folded_value = folded_value ^ ((value >> (fold * bits_in_fold)) & mask);
    }
    return folded_value;
}

uint32_t custom_util::HashZoo::jenkins(uint32_t key) {
    // Robert Jenkins' 32 bit mix function
    key += (key << 12);
    key ^= (key >> 22);
    key += (key << 4);
    key ^= (key >> 9);
    key += (key << 10);
    key ^= (key >> 2);
    key += (key << 7);
    key ^= (key >> 12);
    return key;
}

uint32_t custom_util::HashZoo::knuth(uint32_t key) {
    // Knuth's multiplicative method
    key = (key >> 3) * 2654435761;
    return key;
}

uint32_t custom_util::HashZoo::murmur3(uint32_t key) {
    /* TODO: define it using murmur3's finilization steps */
    assert(false);
}

/* originally ment for 32b key */
uint32_t custom_util::HashZoo::jenkins32(uint32_t key) {
    key = (key + 0x7ed55d16) + (key << 12);
    key = (key ^ 0xc761c23c) ^ (key >> 19);
    key = (key + 0x165667b1) + (key << 5);
    key = (key + 0xd3a2646c) ^ (key << 9);
    key = (key + 0xfd7046c5) + (key << 3);
    key = (key ^ 0xb55a4f09) ^ (key >> 16);
    return key;
}

/* originally ment for 32b key */
uint32_t custom_util::HashZoo::hash32shift(uint32_t key) {
    key = ~key + (key << 15); // key = (key << 15) - key - 1;
    key = key ^ (key >> 12);
    key = key + (key << 2);
    key = key ^ (key >> 4);
    key = key * 2057; // key = (key + (key << 3)) + (key << 11);
    key = key ^ (key >> 16);
    return key;
}

/* originally ment for 32b key */
uint32_t custom_util::HashZoo::hash32shiftmult(uint32_t key) {
    int c2 = 0x27d4eb2d; // a prime or an odd constant
    key = (key ^ 61) ^ (key >> 16);
    key = key + (key << 3);
    key = key ^ (key >> 4);
    key = key * c2;
    key = key ^ (key >> 15);
    return key;
}

uint32_t custom_util::HashZoo::hash64shift(uint32_t key) {
    key = (~key) + (key << 21); // key = (key << 21) - key - 1;
    key = key ^ (key >> 24);
    key = (key + (key << 3)) + (key << 8); // key * 265
    key = key ^ (key >> 14);
    key = (key + (key << 2)) + (key << 4); // key * 21
    key = key ^ (key >> 28);
    key = key + (key << 31);
    return key;
}

uint32_t custom_util::HashZoo::hash5shift(uint32_t key) {
    key = (key ^ 61) ^ (key >> 16);
    key = key + (key << 3);
    key = key ^ (key >> 4);
    key = key * 0x27d4eb2d;
    key = key ^ (key >> 15);
    return key;
}

/* hash6shift is jenkin32 */

uint32_t custom_util::HashZoo::hash7shift(uint32_t key) {
    key -= (key << 6);
    key ^= (key >> 17);
    key -= (key << 9);
    key ^= (key << 4);
    key -= (key << 3);
    key ^= (key << 10);
    key ^= (key >> 15);
    return key;
}

/* use low bit values */
uint32_t custom_util::HashZoo::Wang6shift(uint32_t key) {
    key += ~(key << 15);
    key ^= (key >> 10);
    key += (key << 3);
    key ^= (key >> 6);
    key += ~(key << 11);
    key ^= (key >> 16);
    return key;
}

uint32_t custom_util::HashZoo::Wang5shift(uint32_t key) {
    key = (key + 0x479ab41d) + (key << 8);
    key = (key ^ 0xe4aa10ce) ^ (key >> 5);
    key = (key + 0x9942f0a6) - (key << 14);
    key = (key ^ 0x5aedd67d) ^ (key >> 3);
    key = (key + 0x17bea992) + (key << 7);
    return key;
}

uint32_t custom_util::HashZoo::Wang4shift(uint32_t key) {
    key = (key ^ 0xdeadbeef) + (key << 4);
    key = key ^ (key >> 10);
    key = key + (key << 7);
    key = key ^ (key >> 13);
    return key;
}

uint32_t custom_util::HashZoo::Wang3shift(uint32_t key) {
    key = key ^ (key >> 4);
    key = (key ^ 0xdeadbeef) + (key << 5);
    key = key ^ (key >> 11);
    return key;
}

uint32_t custom_util::HashZoo::three_hybrid1(uint32_t key) { return knuth(hash64shift(jenkins32(key))); }
uint32_t custom_util::HashZoo::three_hybrid2(uint32_t key) { return jenkins32(Wang5shift(hash5shift(key))); }
uint32_t custom_util::HashZoo::three_hybrid3(uint32_t key) { return jenkins(hash32shiftmult(Wang3shift(key))); }
uint32_t custom_util::HashZoo::three_hybrid4(uint32_t key) { return Wang6shift(hash32shift(Wang5shift(key))); }
uint32_t custom_util::HashZoo::three_hybrid5(uint32_t key) { return hash64shift(hash32shift(knuth(key))); }
uint32_t custom_util::HashZoo::three_hybrid6(uint32_t key) { return hash5shift(jenkins(Wang6shift(key))); }
uint32_t custom_util::HashZoo::three_hybrid7(uint32_t key) { return Wang4shift(jenkins32(hash7shift(key))); }
uint32_t custom_util::HashZoo::three_hybrid8(uint32_t key) { return Wang3shift(Wang6shift(hash64shift(key))); }
uint32_t custom_util::HashZoo::three_hybrid9(uint32_t key) { return hash32shift(Wang3shift(jenkins(key))); }
uint32_t custom_util::HashZoo::three_hybrid10(uint32_t key) { return hash32shiftmult(Wang4shift(hash32shiftmult(key))); }
uint32_t custom_util::HashZoo::three_hybrid11(uint32_t key) { return hash7shift(hash5shift(Wang4shift(key))); }
uint32_t custom_util::HashZoo::three_hybrid12(uint32_t key) { return Wang5shift(jenkins32(hash32shift(key))); }

uint32_t custom_util::HashZoo::four_hybrid1(uint32_t key) { return Wang6shift(Wang5shift(Wang3shift(Wang4shift(key)))); }
uint32_t custom_util::HashZoo::four_hybrid2(uint32_t key) { return hash32shiftmult(jenkins(Wang5shift(Wang6shift(key)))); }
uint32_t custom_util::HashZoo::four_hybrid3(uint32_t key) { return hash64shift(hash7shift(jenkins32(hash32shift(key)))); }
uint32_t custom_util::HashZoo::four_hybrid4(uint32_t key) { return knuth(knuth(hash32shiftmult(hash5shift(key)))); }
uint32_t custom_util::HashZoo::four_hybrid5(uint32_t key) { return jenkins32(Wang4shift(hash64shift(hash32shiftmult(key)))); }
uint32_t custom_util::HashZoo::four_hybrid6(uint32_t key) { return jenkins(hash32shift(Wang4shift(Wang3shift(key)))); }
uint32_t custom_util::HashZoo::four_hybrid7(uint32_t key) { return hash32shift(hash64shift(hash5shift(hash64shift(key)))); }
uint32_t custom_util::HashZoo::four_hybrid8(uint32_t key) { return hash7shift(hash5shift(hash32shiftmult(Wang6shift(key)))); }
uint32_t custom_util::HashZoo::four_hybrid9(uint32_t key) { return hash32shiftmult(Wang6shift(jenkins32(knuth(key)))); }
uint32_t custom_util::HashZoo::four_hybrid10(uint32_t key) { return Wang3shift(jenkins32(knuth(jenkins(key)))); }
uint32_t custom_util::HashZoo::four_hybrid11(uint32_t key) { return hash5shift(hash32shiftmult(hash32shift(jenkins32(key)))); }
uint32_t custom_util::HashZoo::four_hybrid12(uint32_t key) { return Wang4shift(Wang3shift(jenkins(hash7shift(key)))); }

uint32_t custom_util::HashZoo::getHash(uint32_t selector, uint32_t key) {
    switch (selector) {
    case 1: return key;
    case 2: return jenkins(key);
    case 3: return knuth(key);
    // case 4:     return murmur3(key);
    case 5: return jenkins32(key);
    case 6: return hash32shift(key);
    case 7: return hash32shiftmult(key);
    case 8: return hash64shift(key);
    case 9: return hash5shift(key);
    case 10: return hash7shift(key);
    case 11: return Wang6shift(key);
    case 12: return Wang5shift(key);
    case 13: return Wang4shift(key);
    case 14: return Wang3shift(key);

    /* three hybrid */
    case 101: return three_hybrid1(key);
    case 102: return three_hybrid2(key);
    case 103: return three_hybrid3(key);
    case 104: return three_hybrid4(key);
    case 105: return three_hybrid5(key);
    case 106: return three_hybrid6(key);
    case 107: return three_hybrid7(key);
    case 108: return three_hybrid8(key);
    case 109: return three_hybrid9(key);
    case 110: return three_hybrid10(key);
    case 111: return three_hybrid11(key);
    case 112: return three_hybrid12(key);

    /* four hybrid */
    case 1001: return four_hybrid1(key);
    case 1002: return four_hybrid2(key);
    case 1003: return four_hybrid3(key);
    case 1004: return four_hybrid4(key);
    case 1005: return four_hybrid5(key);
    case 1006: return four_hybrid6(key);
    case 1007: return four_hybrid7(key);
    case 1008: return four_hybrid8(key);
    case 1009: return four_hybrid9(key);
    case 1010: return four_hybrid10(key);
    case 1011: return four_hybrid11(key);
    case 1012: return four_hybrid12(key);

    default: assert(false);
    }
}

std::vector<bool>
custom_util::pattern_degrade(const std::vector<bool>& x, int level) {
    std::vector<bool> res(x.size() / level, false);
    for (int i = 0; i < x.size(); i++) {
        res[i / level] = res[i / level] || x[i];
    }
    return res;
}

void custom_util::Table::set_row(int row, const std::vector<std::string>& data, int start_col) {
    // assert(data.size() + start_col == this->width);
    for (unsigned col = start_col; col < this->width; col += 1)
        this->set_cell(row, col, data[col]);
}

void custom_util::Table::set_col(int col, const std::vector<std::string>& data, int start_row) {
    // assert(data.size() + start_row == this->height);
    for (unsigned row = start_row; row < this->height; row += 1)
        this->set_cell(row, col, data[row]);
}

void custom_util::Table::set_cell(int row, int col, std::string data) {
    // assert(0 <= row && row < (int)this->height);
    // assert(0 <= col && col < (int)this->width);
    this->cells[row][col] = data;
}

void custom_util::Table::set_cell(int row, int col, double data) {
    std::ostringstream oss;
    oss << std::setw(11) << std::fixed << std::setprecision(8) << data;
    this->set_cell(row, col, oss.str());
}

void custom_util::Table::set_cell(int row, int col, int64_t data) {
    std::ostringstream oss;
    oss << std::setw(11) << std::left << data;
    this->set_cell(row, col, oss.str());
}

void custom_util::Table::set_cell(int row, int col, int data) { this->set_cell(row, col, (int64_t)data); }

void custom_util::Table::set_cell(int row, int col, uint64_t data) {
    std::ostringstream oss;
    oss << "0x" << std::setfill('0') << std::setw(16) << std::hex << data;
    this->set_cell(row, col, oss.str());
}

/**
     * @return The entire table as a std::string
     */
std::string custom_util::Table::to_string() {
    std::vector<int> widths;
    for (unsigned i = 0; i < this->width; i += 1) {
        int max_width = 0;
        for (unsigned j = 0; j < this->height; j += 1)
            max_width = std::max(max_width, (int)this->cells[j][i].size());
        widths.push_back(max_width + 2);
    }
    std::string out;
    out += Table::top_line(widths);
    out += this->data_row(0, widths);
    for (unsigned i = 1; i < this->height; i += 1) {
        out += Table::mid_line(widths);
        out += this->data_row(i, widths);
    }
    out += Table::bot_line(widths);
    return out;
}

std::string custom_util::Table::data_row(int row, const std::vector<int>& widths) {
    std::string out;
    for (unsigned i = 0; i < this->width; i += 1) {
        std::string data = this->cells[row][i];
        data.resize(widths[i] - 2, ' ');
        out += " | " + data;
    }
    out += " |\n";
    return out;
}

std::string custom_util::Table::top_line(const std::vector<int>& widths) { return Table::line(widths, "┌", "┬", "┐"); }

std::string custom_util::Table::mid_line(const std::vector<int>& widths) { return Table::line(widths, "├", "┼", "┤"); }

std::string custom_util::Table::bot_line(const std::vector<int>& widths) { return Table::line(widths, "└", "┴", "┘"); }

std::string custom_util::Table::line(const std::vector<int>& widths, std::string left, std::string mid, std::string right) {
    std::string out = " " + left;
    for (unsigned i = 0; i < widths.size(); i += 1) {
        int w = widths[i];
        for (int j = 0; j < w; j += 1)
            out += "─";
        if (i != widths.size() - 1)
            out += mid;
        else
            out += right;
        ;
    }
    return out + "\n";
}

void custom_util::ShiftRegister::insert(int x) {
    x &= (1 << this->width) - 1;
    this->reg = (this->reg << this->width) | x;
}

/**
 * @return Returns raw buffer data in range [le, ri).
 * Note that more recent data have a smaller index.
 */
uint64_t custom_util::ShiftRegister::get_code(unsigned le, unsigned ri) {
    assert(0 <= le && le < this->size);
    assert(le < ri && ri <= this->size);
    uint64_t mask = (1ull << (this->width * (ri - le))) - 1ull;
    return (this->reg >> (le * this->width)) & mask;
}

/**
 * @return Returns integer value of data at specified index.
 */
int custom_util::ShiftRegister::get_value(int i) {
    int x = this->get_code(i, i + 1);
    /* sign extend */
    int d = 32 - this->width;
    return (x << d) >> d;
}

bool custom_util::ShiftRegister::all_is_same_value() {
    for (size_t i = 0; i < size - 1; i++) {
        if (get_value(i) != get_value(i + 1))
            return false;
    }
    return true;
}

int custom_util::SaturatingCounter::inc() {
    this->cnt += 1;
    if (this->cnt > this->max)
        this->cnt = this->max;
    return this->cnt;
}

int custom_util::SaturatingCounter::dec() {
    this->cnt -= 1;
    if (this->cnt < 0)
        this->cnt = 0;
    return this->cnt;
}

int custom_util::SaturatingCounter::get_cnt() { return this->cnt; }

bool custom_util::SaturatingCounter::operator==(int value) { return cnt == value; }

bool custom_util::SaturatingCounter::operator>(SaturatingCounter& other) { return cnt > other.cnt; }

bool custom_util::SaturatingCounter::operator>=(SaturatingCounter& other) { return cnt >= other.cnt; }

bool custom_util::SaturatingCounter::operator<(SaturatingCounter& other) { return cnt < other.cnt; }

bool custom_util::SaturatingCounter::operator<=(SaturatingCounter& other) { return cnt <= other.cnt; }

/******************************************************************************/
/*                                   Pythia                                   */
/******************************************************************************/
std::string custom_util::BitmapHelper::to_string(custom_util::Bitmap bmp, uint32_t size) {
    // return bmp.to_string<char,std::string::traits_type,std::string::allocator_type>();
    std::stringstream ss;
    for (int32_t bit = size - 1; bit >= 0; --bit) {
        ss << bmp[bit];
    }
    return ss.str();
}

uint32_t custom_util::BitmapHelper::count_bits_set(custom_util::Bitmap bmp, uint32_t size) {
    // return static_cast<uint32_t>(bmp.count());
    uint32_t count = 0;
    for (uint32_t index = 0; index < size; ++index) {
        if (bmp[index]) count++;
    }
    return count;
}

uint32_t custom_util::BitmapHelper::count_bits_same(custom_util::Bitmap bmp1, custom_util::Bitmap bmp2, uint32_t size) {
    uint32_t count_same = 0;
    for (uint32_t index = 0; index < size; ++index) {
        if (bmp1[index] && bmp1[index] == bmp2[index]) {
            count_same++;
        }
    }
    return count_same;
}

uint32_t custom_util::BitmapHelper::count_bits_diff(custom_util::Bitmap bmp1, custom_util::Bitmap bmp2, uint32_t size) {
    uint32_t count_diff = 0;
    for (uint32_t index = 0; index < size; ++index) {
        if (bmp1[index] && !bmp2[index]) {
            count_diff++;
        }
    }
    return count_diff;
}

uint64_t custom_util::BitmapHelper::value(custom_util::Bitmap bmp, uint32_t size) {
    return bmp.to_ullong();
}

custom_util::Bitmap custom_util::BitmapHelper::rotate_left(custom_util::Bitmap bmp, uint32_t amount, uint32_t size) {
    custom_util::Bitmap result;
    for (uint32_t index = 0; index < (size - amount); ++index) {
        result[index + amount] = bmp[index];
    }
    for (uint32_t index = 0; index < amount; ++index) {
        result[index] = bmp[index + size - amount];
    }
    return result;
}

custom_util::Bitmap custom_util::BitmapHelper::rotate_right(custom_util::Bitmap bmp, uint32_t amount, uint32_t size) {
    custom_util::Bitmap result;
    for (uint32_t index = 0; index < size - amount; ++index) {
        result[index] = bmp[index + amount];
    }
    for (uint32_t index = 0; index < amount; ++index) {
        result[size - amount + index] = bmp[index];
    }
    return result;
}

custom_util::Bitmap custom_util::BitmapHelper::compress(custom_util::Bitmap bmp, uint32_t granularity, uint32_t size) {
    assert(size % granularity == 0);
    uint32_t index = 0;
    custom_util::Bitmap result;
    uint32_t ptr = 0;

    while (index < size) {
        bool res = false;
        uint32_t gran = 0;
        for (gran = 0; gran < granularity; ++gran) {
            assert(index + gran < size);
            res = res | bmp[index + gran];
        }
        result[ptr] = res;
        ptr++;
        index = index + gran;
    }
    return result;
}

custom_util::Bitmap custom_util::BitmapHelper::decompress(custom_util::Bitmap bmp, uint32_t granularity, uint32_t size) {
    custom_util::Bitmap result;
    result.reset();
    assert(size * granularity <= BITMAP_MAX_SIZE);
    for (uint32_t index = 0; index < size; ++index) {
        if (bmp[index]) {
            uint32_t ptr = index * granularity;
            for (uint32_t count = 0; count < granularity; ++count) {
                result[ptr + count] = true;
            }
        }
    }
    return result;
}

custom_util::Bitmap custom_util::BitmapHelper::bitwise_or(custom_util::Bitmap bmp1, custom_util::Bitmap bmp2, uint32_t size) {
    custom_util::Bitmap result;
    for (uint32_t index = 0; index < size; ++index) {
        if (bmp1[index] || bmp2[index]) {
            result[index] = true;
        }
    }
    return result;
}

custom_util::Bitmap custom_util::BitmapHelper::bitwise_and(custom_util::Bitmap bmp1, custom_util::Bitmap bmp2, uint32_t size) {
    custom_util::Bitmap result;
    for (uint32_t index = 0; index < size; ++index) {
        if (bmp1[index] && bmp2[index]) {
            result[index] = true;
        }
    }
    return result;
}

std::string custom_util::Binary(uint64_t x) {
    std::string s = "";
    while (x) {
        if (x % 2 == 0)
            s = '0' + s;
        else
            s = '1' + s;
        x /= 2;
    }
    return s;
}