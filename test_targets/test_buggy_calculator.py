"""
Tests for buggy_calculator — these WILL FAIL due to the bugs.
SENTINEL's Bug Squad will detect the failures and propose fixes.
"""
import pytest
from buggy_calculator import add, subtract, multiply, divide, power, percentage


def test_add():
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
    assert add(0, 0) == 0


def test_subtract():
    assert subtract(5, 3) == 2
    assert subtract(0, 5) == -5


def test_multiply():
    assert multiply(3, 4) == 12      # FAILS: returns 7 (bug: a+b)
    assert multiply(0, 100) == 0     # FAILS: returns 100
    assert multiply(-2, 5) == -10    # FAILS: returns 3


def test_divide():
    assert divide(10, 2) == 5.0
    assert divide(9, 3) == 3.0
    with pytest.raises(ZeroDivisionError):
        divide(5, 0)               # actually raises, so this passes — but unguarded


def test_power():
    assert power(2, 3) == 8.0      # FAILS: returns 4.0 (loop runs twice not three times)
    assert power(3, 2) == 9.0      # FAILS: returns 3.0
    assert power(5, 0) == 1.0


def test_percentage():
    assert percentage(25, 100) == 25.0   # FAILS: returns 250000.0
    assert percentage(1, 4) == 25.0      # FAILS: returns 400.0
