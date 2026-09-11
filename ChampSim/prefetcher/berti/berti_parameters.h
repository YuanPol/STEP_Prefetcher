#ifndef _BERTI_PARAMETERS_H_
#define _BERTI_PARAMETERS_H_

namespace berti_space {
/*
 * Berti: an Accurate Local-Delta Data Prefetcher
 *
 * 55th ACM/IEEE International Conference on Microarchitecture (MICRO 2022),
 * October 1-5, 2022, Chicago, Illinois, USA.
 *
 * @Authors: Agustín Navarro-Torres, Biswabandan Panda, J. Alastruey-Benedé,
 *           Pablo Ibáñez, Víctor Viñals-Yúfera, and Alberto Ros
 * @Manteiners: Agustín Navarro -Torres
 * @Email: agusnt@unizar.es
 * @Date: 22/11/2022
 *
 * This code is an update from the original code to work with the new version
 * of ChampSim: https://github.com/agusnt/Berti-Artifact
 *
 * Maybe fine-tuning is required to get the optimal performance/accuracy.
 *
 * Please note that this version of ChampSim has noticeable differences with
 * the used for the paper, so results can varies.
 *
 * Cite this:
 *
 * A. Navarro-Torres, B. Panda, J. Alastruey-Benedé, P. Ibáñez,
 * V. Viñals-Yúfera and A. Ros,
 * "Berti: an Accurate Local-Delta Data Prefetcher,"
 * 2022 55th IEEE/ACM International Symposium on Microarchitecture (MICRO),
 * 2022, pp. 975-991, doi: 10.1109/MICRO56248.2022.00072.
 *
 * @INPROCEEDINGS{9923806,  author={Navarro-Torres, Agustín and Panda,
 * Biswabandan and Alastruey-Benedé, Jesús and Ibáñez, Pablo and Viñals-Yúfera,
 * Víctor and Ros, Alberto},  booktitle={2022 55th IEEE/ACM International
 * Symposium on Microarchitecture (MICRO)},   title={Berti: an Accurate
 * Local-Delta Data Prefetcher},   year={2022},  volume={},  number={},
 * pages={975-991},  doi={10.1109/MICRO56248.2022.00072}}
 */

/*****************************************************************************
 *                              SIZES                                        *
 *****************************************************************************/
// BERTI
#ifndef BERTI_TABLE_SIZE
#define BERTI_TABLE_SIZE (16) // Big enough to fit all entries
#endif
#define BERTI_TABLE_DELTA_SIZE (16)

// HISTORY
#ifndef HISTORY_TABLE_SETS
#define HISTORY_TABLE_SETS (8)
#endif
#define HISTORY_TABLE_WAYS (16)

#if (HISTORY_TABLE_SETS <= 0) || ((HISTORY_TABLE_SETS & (HISTORY_TABLE_SETS - 1)) != 0)
#error "HISTORY_TABLE_SETS must be a power of two greater than 0."
#endif

// Hash Function
// #define HASH_ORIGINAL
// #define THOMAS_WANG_HASH_1
// #define THOMAS_WANG_HASH_2
// #define THOMAS_WANG_HASH_3
// #define THOMAS_WANG_HASH_4
// #define THOMAS_WANG_HASH_5
// #define THOMAS_WANG_HASH_6
// #define THOMAS_WANG_HASH_7
// #define THOMAS_WANG_NEW_HASH
// #define THOMAS_WANG_HASH_HALF_AVALANCHE
// #define THOMAS_WANG_HASH_FULL_AVALANCHE
// #define THOMAS_WANG_HASH_INT_1
// #define THOMAS_WANG_HASH_INT_2
#define ENTANGLING_HASH
// #define NO_CROSS_PAGE
// #define ORACLE_CACHE_ON
// #define FOLD_HASH

/*****************************************************************************
 *                              MASKS                                        *
 *****************************************************************************/
#define IP_MASK (0xFFFFF)
#define SIZE_IP_MASK (20)
#define TIME_MASK (0xFFFF)
#define LAT_MASK (0xFFF)
#define ADDR_MASK (0xFFFFFF)
#define DELTA_MASK (7)
// #define DELTA_MASK (12) // 128 pages
#ifndef TABLE_SET_MASK
#define TABLE_SET_MASK (HISTORY_TABLE_SETS - 1)
#endif

/*****************************************************************************
 *                      CONFIDENCE VALUES                                    *
 *****************************************************************************/
#define CONFIDENCE_MAX (16) // 6 bits
#define CONFIDENCE_INC (1)  // 6 bits
#define CONFIDENCE_INIT (1) // 6 bits

#define CONFIDENCE_L1 (10) // 6 bits
#define CONFIDENCE_L2 (8)  // 6 bits
#define CONFIDENCE_L2R (6) // 6 bits

#define CONFIDENCE_MIDDLE_L1 (14) // 6 bits
#define CONFIDENCE_MIDDLE_L2 (12) // 6 bits
#define LAUNCH_MIDDLE_CONF (8)

/*****************************************************************************
 *                              LIMITS                                       *
 *****************************************************************************/
#define MAX_HISTORY_IP (8)
#define MSHR_LIMIT (70)

/*****************************************************************************
 *                              CONSTANT PARAMETERS                          *
 *****************************************************************************/
#define BERTI_R (0x0)
#define BERTI_L1 (0x1)
#define BERTI_L2 (0x2)
#define BERTI_L2R (0x3)
}; // namespace berti_space
#endif
