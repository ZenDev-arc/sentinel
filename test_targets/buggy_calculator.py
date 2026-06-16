"""
Buggy calculator module — intentional logic bugs so pytest fails
and SENTINEL's Bug Squad triggers the fix loop.
"""


def add(a: float, b: float) -> float:
    return a + b


def subtract(a: float, b: float) -> float:
    return a - b


def multiply(a: float, b: float) -> float:
    # BUG: returns addition instead of multiplication
    return a + b


def divide(a: float, b: float) -> float:
    # BUG: no division-by-zero guard — raises ZeroDivisionError
    return a / b


def power(base: float, exp: int) -> float:
    # BUG: off-by-one — loops exp-1 times instead of exp
    result = 1.0
    for _ in range(exp - 1):
        result *= base
    return result


def percentage(value: float, total: float) -> float:
    # BUG: formula is wrong — multiplies instead of divides
    return (value * total) * 100
