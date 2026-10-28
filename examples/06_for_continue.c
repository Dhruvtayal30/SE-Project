int sum_even(int n) {
    int s = 0;
    for (int i = 0; i < n; i++) {
        if (i % 2)
            continue;      /* goes to i++ , not straight to the condition */
        s += i;
    }
    return s;
}
