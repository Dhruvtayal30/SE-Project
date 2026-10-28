int scan(int a) {
    for (int i = 0; i < a; i++) {
        for (int j = 0; j < i; j++) {
            if (j == 2)
                continue;
            if (i == 5)
                break;
        }
    }
    return a;
}
