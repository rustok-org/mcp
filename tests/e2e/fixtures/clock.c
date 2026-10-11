/* Linux acceptance fixture only: advance CLOCK_MONOTONIC in one throwaway
 * container without touching wall time, the host, or candidate image bytes.
 * Mount this compiled library read-only and change a fixture offset file.
 * No wallet/core function is intercepted. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <time.h>

int clock_gettime(clockid_t id, struct timespec *result) {
    int (*actual)(clockid_t, struct timespec *) = dlsym(RTLD_NEXT, "clock_gettime");
    if (actual == NULL) return -1;
    int rc = actual(id, result);
    if (rc == 0 && id == CLOCK_MONOTONIC) {
        FILE *file = fopen("/run/wallet-clock/offset", "r");
        if (file != NULL) {
            int seconds = 0, digits = 0, digit = fgetc(file);
            while (digit >= '0' && digit <= '9' && digits < 4) {
                seconds = seconds * 10 + digit - '0';
                digits++;
                digit = fgetc(file);
            }
            if (digits > 0 && (digit == '\n' || digit == EOF) && seconds <= 3600)
                result->tv_sec += seconds;
            fclose(file);
        }
    }
    return rc;
}
