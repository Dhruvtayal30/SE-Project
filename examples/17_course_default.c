#include <stdio.h>

int process(int n, int mode) {
    int total = 0;
    for (int i = 0; i < n; i++) {
        if (i % 2 == 0 && mode > 0) {
            continue;
        }
        switch (mode) {
            case 1:
                total += i;
                break;
            case 2:
                total += 2 * i;
            case 3:
                total += 3;
                break;
            default:
                total -= 1;
        }
        if (total > 100)
            break;
    }
    while (total > 50) {
        total -= 10;
    }
    return total > 0 ? total : 0;
}
