/*
 * Native diffusion kernel for FieldSystem.
 *
 * This is the first compiled hot-path target for the runtime.
 *
 * Design:
 * - grid_in and grid_out are flat arrays of size width * height
 * - active_in contains flat cell indices currently considered active
 * - active_out is filled with the next set of active indices
 * - return value is the number of valid entries written to active_out
 *
 * Notes:
 * - Uses double precision for correctness matching with Python
 * - Conserves mass by distributing from each active cell to its 4-neighbors
 * - Only processes active cells plus their neighbors
 * - Uses a byte mark buffer internally to avoid duplicate active_out entries
 */

#include <stdlib.h>
#include <string.h>
#include <math.h>

#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif

static void add_candidate(
    int idx,
    unsigned char *candidate_marks,
    int *candidate_list,
    int *candidate_count
) {
    if (!candidate_marks[idx]) {
        candidate_marks[idx] = 1;
        candidate_list[*candidate_count] = idx;
        (*candidate_count)++;
    }
}

EXPORT int field_diffuse_step(
    const double *grid_in,
    double *grid_out,
    int width,
    int height,
    double diffuse_rate,
    double dt,
    double epsilon,
    const int *active_in,
    int active_count,
    int *active_out,
    int active_out_capacity
) {
    int cell_count = width * height;
    int i;

    /* Start from a copy of the input grid */
    memcpy(grid_out, grid_in, sizeof(double) * cell_count);

    if (active_count <= 0) {
        return 0;
    }

    double factor = diffuse_rate * dt;

    /*
     * Candidate set = active cells + their neighbors.
     * We avoid duplicate candidates with a mark array.
     */
    unsigned char *candidate_marks = (unsigned char *)calloc((size_t)cell_count, sizeof(unsigned char));
    if (!candidate_marks) {
        return -1;
    }

    int max_candidates = cell_count;
    int *candidate_list = (int *)malloc(sizeof(int) * (size_t)max_candidates);
    if (!candidate_list) {
        free(candidate_marks);
        return -1;
    }

    int candidate_count = 0;

    for (i = 0; i < active_count; i++) {
        int idx = active_in[i];
        if (idx < 0 || idx >= cell_count) {
            continue;
        }

        add_candidate(idx, candidate_marks, candidate_list, &candidate_count);

        int x = idx % width;
        int y = idx / width;

        if (x > 0) {
            add_candidate(idx - 1, candidate_marks, candidate_list, &candidate_count);
        }
        if (x < width - 1) {
            add_candidate(idx + 1, candidate_marks, candidate_list, &candidate_count);
        }
        if (y > 0) {
            add_candidate(idx - width, candidate_marks, candidate_list, &candidate_count);
        }
        if (y < height - 1) {
            add_candidate(idx + width, candidate_marks, candidate_list, &candidate_count);
        }
    }

    /*
     * Diffusion step:
     * read from grid_in, write to grid_out
     */
    for (i = 0; i < candidate_count; i++) {
        int idx = candidate_list[i];
        double val = grid_in[idx];

        if (fabs(val) <= epsilon) {
            continue;
        }

        int x = idx % width;
        int y = idx / width;
        int neighbor_count = 0;

        if (x > 0) neighbor_count++;
        if (x < width - 1) neighbor_count++;
        if (y > 0) neighbor_count++;
        if (y < height - 1) neighbor_count++;

        if (neighbor_count == 0) {
            continue;
        }

        double share = val * factor;
        double outflow = share * (double)neighbor_count;

        grid_out[idx] -= outflow;

        if (x > 0) {
            grid_out[idx - 1] += share;
        }
        if (x < width - 1) {
            grid_out[idx + 1] += share;
        }
        if (y > 0) {
            grid_out[idx - width] += share;
        }
        if (y < height - 1) {
            grid_out[idx + width] += share;
        }
    }

    /*
     * Build next active set from candidate cells whose updated value is significant.
     */
    int out_count = 0;
    for (i = 0; i < candidate_count; i++) {
        int idx = candidate_list[i];
        if (fabs(grid_out[idx]) > epsilon) {
            if (out_count < active_out_capacity) {
                active_out[out_count] = idx;
                out_count++;
            } else {
                /*
                 * Capacity too small. Signal failure with -2.
                 * Caller should retry with a larger buffer.
                 */
                free(candidate_marks);
                free(candidate_list);
                return -2;
            }
        }
    }

    free(candidate_marks);
    free(candidate_list);
    return out_count;
}
