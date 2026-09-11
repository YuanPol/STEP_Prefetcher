#define STEP_PREFETCHER_DISABLE_SECOND_OFFSET 1
#define step step_l1_l2_fill_disable_second_ns
#include "../step_full_l1_l2_fill/step.cc"
#undef step
