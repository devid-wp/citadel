import pytest
from core.shell_flow import parse_and_run_if
from main_handlers import cmd_true, cmd_false

def test_if_then_branch():
    # Симулируем функцию выполнения команд шелла
    # Если нам передали "true-cmd", возвращаем 0, если "false-cmd" — возвращаем 1
    def mock_run(tokens):
        if "true-cmd" in tokens or "success" in tokens:
            return 0
        return 1

    # Тестируем ветку then (условие успешно)
    tokens_true = ["if", "true-cmd", "then", "success", "fi"]
    assert parse_and_run_if(tokens_true, mock_run) == 0

    # Тестируем ветку else (условие провалено)
    tokens_false = ["if", "false-cmd", "then", "success", "else", "fail-branch", "fi"]
    assert parse_and_run_if(tokens_false, mock_run) == 1

def test_if_syntax_errors():
    def mock_run(tokens): return 0
    
    # Пропущен 'then'
    assert parse_and_run_if(["if", "cond", "fi"], mock_run) == 1
    # Пропущен 'fi'
    assert parse_and_run_if(["if", "cond", "then", "cmd"], mock_run) == 1


    def test_true_false_builtins():
        from main_handlers import cmd_true, cmd_false
    assert cmd_true([]) == 0
    assert cmd_false([]) == 1

def test_condition_inversion():
    from core.shell_arith import eval_test_condition
    # Обычная строка пустая -> True, с инверсией должно быть False
    assert eval_test_condition("-z ''") is True
    assert eval_test_condition("! -z ''") is False
    
    # Сравнение чисел с инверсией
    assert eval_test_condition("5 -gt 10") is False
    assert eval_test_condition("! 5 -gt 10") is True