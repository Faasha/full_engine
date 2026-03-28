/*
 * Native flat movement kernel.
 *
 * Updates:
 *   pos_x[i] += vel_x[i] * dt
 *   pos_y[i] += vel_y[i] * dt
 *
 * This is intentionally narrow:
 * - no collision
 * - no bounds
 * - no allocation
 * - no ownership changes
 *
 * It exists only to test whether the flat hot movement lane benefits from
 * a compiled kernel.
 */

#include <stddef.h>

#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif

EXPORT int movement_step(
    double *pos_x,
    double *pos_y,
    const double *vel_x,
    const double *vel_y,
    int count,
    double dt
) {
    if (!pos_x || !pos_y || !vel_x || !vel_y) {
        return -1;
    }
    if (count < 0) {
        return -2;
    }

    for (int i = 0; i < count; i++) {
        pos_x[i] += vel_x[i] * dt;
        pos_y[i] += vel_y[i] * dt;
    }

    return 0;
}
