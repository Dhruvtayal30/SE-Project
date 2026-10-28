#include <stdio.h>

static int square(int x) {
    return x * x;
}

int clamp(int v, int lo, int hi) {
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

int main(void) {
    int v = square(7);
    printf("%d\n", clamp(v, 0, 10));
    return 0;
}
