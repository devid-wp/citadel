from typing import List, Optional

def parse_and_run_if(tokens: List[str], run_command_fn) -> int:
    """
    Разбирает и выполняет конструкцию if ... then ... [else ...] fi.
    Принимает токены строки и функцию run_command_fn для выполнения вложенных команд.
    Возвращает exit_code (0 - успех, 1 - ошибка).
    """
    if not tokens or tokens[0] != "if":
        return 1

    try:
        # Находим индексы ключевых слов
        if_idx = 0
        then_idx = tokens.index("then")
        
        # else необязателен, поэтому ищем аккуратно
        else_idx = tokens.index("else") if "else" in tokens else -1
        fi_idx = tokens.index("fi")
    except ValueError:
        print("citadel: syntax error: missing 'then' or 'fi'")
        return 1

    if then_idx > fi_idx or (else_idx != -1 and then_idx > else_idx) or (else_idx != -1 and else_idx > fi_idx):
        print("citadel: syntax error: invalid order of if-then-else-fi tokens")
        return 1

    # 1. Выделяем и запускаем условие (всё, что между 'if' и 'then')
    condition_tokens = tokens[if_idx + 1:then_idx]
    # Запускаем команду условия через основную функцию шелла
    # Если это была проверка [[ 1 -gt 0 ]], то run_command_fn вернет 0 (True)
    condition_res = run_command_fn(condition_tokens)
    
    # В мире шелла: exit code 0 означает успех (True)
    is_true = (condition_res == 0)

    # 2. Определяем, какой блок команд выполнять
    if is_true:
        # Выполняем блок 'then' (между then и else/fi)
        end_block_idx = else_idx if else_idx != -1 else fi_idx
        body_tokens = tokens[then_idx + 1:end_block_idx]
        return run_command_fn(body_tokens)
    elif else_idx != -1:
        # Выполняем блок 'else' (между else и fi)
        body_tokens = tokens[else_idx + 1:fi_idx]
        return run_command_fn(body_tokens)
        
    return 0