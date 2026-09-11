#ifndef GHB_H
#define GHB_H

#include<deque>
#include<utility>
#include<list>
#include<stdint.h>
#include<algorithm>
#include<assert.h>

#include"cache.h"

namespace ghb
{

constexpr int IT_SIZE = 256;
constexpr int GHB_SIZE = 256;

constexpr int STRIDE_MATCH_NUM = 2;

class IT {
  // Index Table
  // A table indexed by PC, stores a pointer to a GHB entry
public:
  IT(){}
  using size_t = std::size_t;
  using iterator = std::deque<std::pair<uint64_t, int>>::iterator;
  using const_iterator = std::deque<std::pair<uint64_t, int>>::const_iterator;
  using reverse_iterator = std::reverse_iterator<iterator>;
  using const_reverse_iterator = std::reverse_iterator<const_iterator>;

  iterator begin() noexcept { return _index_table.begin(); }
  iterator end() noexcept { return _index_table.end(); }
  const_iterator cbegin() const noexcept { return _index_table.cbegin(); }
  const_iterator cend() const noexcept { return _index_table.cend(); }
  reverse_iterator rbegin() noexcept { return _index_table.rbegin(); }
  reverse_iterator rend() noexcept { return _index_table.rend(); }
  const_reverse_iterator crbegin() const noexcept { return _index_table.crbegin(); }
  const_reverse_iterator crend() const noexcept { return _index_table.crend(); }

  size_t occupancy() const noexcept { return _index_table.size(); }
  bool full() const noexcept {return occupancy() == IT_SIZE;}
  bool empty() const noexcept { return occupancy() == 0; }
  void clear() { _index_table.clear(); }

  int evict(){ if(!full()) return 0; else { _pop_front(); return 1; }}
  iterator insert(uint64_t pc){
    if (full()) evict(); // IT needs replacement, evict, pop_front
    _push_back(pc, -1); 
    return end()-1;
  }
  iterator find(uint64_t pc){ return std::find_if(begin(), end(), [pc](std::pair<uint64_t, int> x) { return x.first == pc; }); }

private:
  std::deque<std::pair<uint64_t, int>> _index_table;
  void _push_back(const std::pair<uint64_t, int> item){ _index_table.push_back(item); }
  void _push_back(uint64_t first, int second){ _index_table.push_back(std::make_pair(first, second)); }
  void _pop_front() { _index_table.pop_front(); }
};

class GHB {
    // Global History Buffer
    // A circular queue that stores the observed addresses
    // Each entry stores a prev_ptr
public:
  GHB(){}
  using size_t = std::size_t;
  using iterator = std::deque<std::pair<uint64_t, int64_t>>::iterator;
  using const_iterator = std::deque<std::pair<uint64_t, int64_t>>::const_iterator;
  using reverse_iterator = std::reverse_iterator<iterator>;
  using const_reverse_iterator = std::reverse_iterator<const_iterator>;

  iterator begin() noexcept { return _global_history_buffer.begin(); }
  iterator end() noexcept { return _global_history_buffer.end(); }
  const_iterator cbegin() const noexcept { return _global_history_buffer.cbegin(); }
  const_iterator cend() const noexcept { return _global_history_buffer.cend(); }
  reverse_iterator rbegin() noexcept { return _global_history_buffer.rbegin(); }
  reverse_iterator rend() noexcept { return _global_history_buffer.rend(); }
  const_reverse_iterator crbegin() const noexcept { return _global_history_buffer.crbegin(); }
  const_reverse_iterator crend() const noexcept { return _global_history_buffer.crend(); }

  size_t occupancy() const noexcept { return _global_history_buffer.size(); }
  bool full() const noexcept {return occupancy() == GHB_SIZE;}
  bool empty() const noexcept { return occupancy() == 0; }
  void clear() { _global_history_buffer.clear(); }
  std::pair<uint64_t, int64_t>& at(int64_t idx) { if(idx < occupancy()) return _global_history_buffer.at(idx); else assert(0); } 

  int evict(IT& index_table){
    if (!full()) return 0;
    else {
      _pop_front();
      for (auto it = begin(); it != end(); it++) (*it).second = (*it).second > 0 ? (*it).second - 1 : -1;
      for (auto it = index_table.begin(); it != index_table.end(); it++) (*it).second = (*it).second > 0 ? (*it).second - 1 : -1;
      return 1;
    }
  }

  iterator insert(uint64_t addr, int prev_idx, IT& index_table, IT::iterator it_IT){
    // std::cout << "GHB insert called, addr: " << addr << ", prev_idx: " << prev_idx << std::endl;
    if (full()) {
      evict(index_table); // GHB needs replacement, evict, pop_front
      prev_idx = (prev_idx == -1 ? prev_idx : prev_idx - 1);
    }
    _push_back(addr, prev_idx);
    it_IT->second = occupancy()-1; // point to the last entry in GHB
    return end()-1;
  }
  
  /*
    if no patterns then return 0;
    else return stride;
  */
  int get_patterns(){
    uint64_t prev_addr=0, current_addr=0; 
    int current_idx = 0, prev_idx=0, i = 0;
    std::list<int64_t> strides;
    int64_t ret = 0;

    current_idx = occupancy()-1;
    current_addr = at(current_idx).first;

    for(;i < STRIDE_MATCH_NUM && at(current_idx).second != -1;i++){
        prev_idx = at(current_idx).second;
        prev_addr = at(prev_idx).first;
        if(current_addr > prev_addr)
            strides.push_back(current_addr - prev_addr);
        else strides.push_back(-1 * (prev_addr - current_addr));
        
        current_addr = prev_addr;
        current_idx = prev_idx;
    }
    if (strides.front() == 0 || strides.size() < STRIDE_MATCH_NUM) return 0;

    auto it = strides.begin();
    for(; it != strides.end(); it++){
      if(*it != strides.front()){
        ret = 0;
        break;
      }
    }
    // auto it = find_if_not(strides.begin(), strides.end(), [strides](auto x) { return x == strides.front(); });
    if (it == strides.end()) {
      ret = strides.front();
      // std::cout << ret << std::endl;
      // for (auto it = begin(); it != end(); it++){
      //   std::cout << it->first << ", " << it->second << std::endl;
      // }
    }
    return ret;
  }
  
private:
  std::deque<std::pair<uint64_t, int64_t>> _global_history_buffer;
  void _push_back(const std::pair<uint64_t, int64_t> item) { _global_history_buffer.push_back(item); }
  void _push_back(uint64_t first, int64_t second){ _global_history_buffer.push_back(std::make_pair(first, second)); }
  void _pop_front(){ _global_history_buffer.pop_front(); }
};
} // namespace ghb

#endif