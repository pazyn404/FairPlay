from secrets import randbelow


def secure_random(a, b):
    return a + randbelow(b - a + 1)
