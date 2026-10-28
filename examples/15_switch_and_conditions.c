#include <stdio.h>

int main(void) {
    int expression, a, b, i;
    scanf("%d %d %d", &expression, &a, &b);

    switch (expression) {
        case 1:
            for (i = 0; i < 5 && i < 3; i++) {
                if (i % 2 == 0) {
                    printf("True block\n");
                } else {
                    printf("False block\n");
                }
            }
            break;
        case 2:
            if (a > 0 || b > 0) {
                printf("True block\n");
            } else {
                printf("False block\n");
            }
            break;
        default:
            printf("Block 1\n");
    }
    return 0;
}
