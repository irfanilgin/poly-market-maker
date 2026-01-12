import math
import random


def math_round_down(f: float, sig_digits: int) -> float:
    str_f = str(f).split(".")
    if len(str_f) > 1 and len(str_f[1]) == sig_digits:
        # don,t round values which are already the number of sig_digits
        return f
    return math.floor((f * (10**sig_digits))) / (10**sig_digits)


def math_round_up(f: float, sig_digits: int) -> float:
    str_f = str(f).split(".")
    if len(str_f) > 1 and len(str_f[1]) == sig_digits:
        # don,t round values which are already the number of sig_digits
        return f
    return math.ceil((f * (10**sig_digits))) / (10**sig_digits)


def add_randomness(price: float, lower: float, upper: float) -> float:
    return math.floor((price + random.uniform(lower, upper)) * (10**2)) / (10**2)


def randomize_default_price(price: float) -> float:
    return add_randomness(price, -0.1, 0.1)
