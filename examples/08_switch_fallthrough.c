int classify(int x) {
    int r = 0;
    switch (x) {
    case 1:
        r = 1;            /* falls through into case 2 */
    case 2:
        r += 2;
        break;
    case 3:
    case 4:
        r = 4;
        break;
    default:
        r = 9;
    }
    return r;
}
