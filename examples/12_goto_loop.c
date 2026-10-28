int drain(int n) {
again:
    n--;
    if (n > 0)
        goto again;
    return n;
}
