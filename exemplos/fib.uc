{
    int n;
    int a;
    int b;
    int proximo;
    int i;
    read(n);
    print(n);
    a = 0;
    b = 1;
    i = 0;
    while (i < n) {
        proximo = a + b;
        a = b;
        b = proximo;
        i = i + 1;
    }
    print(a);
}
