import pytest
from core.shell_arith import eval_arithmetic, eval_test_condition
import os

def test_math_evaluation():
    assert eval_arithmetic("1 + 2") == 3
    assert eval_arithmetic("10 - 4 * 2") == 2
    assert eval_arithmetic("(5 + 5) * 2") == 20
    assert eval_arithmetic("10 % 3") == 1

def test_math_with_variables():
    vars_store = {"X": 10, "Y": 5}
    assert eval_arithmetic("X + Y", vars_store) == 15
    assert eval_arithmetic("X * 2 - Y", vars_store) == 15
    assert eval_arithmetic("UNKNOWN_VAR + 5", vars_store) == 5

def test_file_conditions(tmp_path):
    # Создаем временный файл и папку для тестов
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello")
    test_dir = tmp_path / "mydir"
    test_dir.mkdir()

    assert eval_test_condition(f"-f {test_file}") is True
    assert eval_test_condition(f"-d {test_dir}") is True
    assert eval_test_condition("-f nonexistent.txt") is False

def test_string_conditions():
    assert eval_test_condition("-z ''") is True
    assert eval_test_condition("-n 'hello'") is True
    assert eval_test_condition("abc == abc") is True
    assert eval_test_condition("abc != def") is True

def test_numeric_comparison():
    assert eval_test_condition("10 -gt 5") is True
    assert eval_test_condition("3 -le 3") is True
    assert eval_test_condition("5 -ne 5") is False