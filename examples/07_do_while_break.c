int countdown(int n) {
    do {
        n--;
        if (n == 3)
            break;
    } while (n > 0);
    return n;
}
