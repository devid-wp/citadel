import os
import re

def eval_arithmetic(expr: str, shell_vars: dict = None) -> int:
    """
    Парсит и вычисляет математические выражения типа '1 + 2 * 3' или 'X + 5'.
    Безопасная замена eval().
    """
    if shell_vars is None:
        shell_vars = {}

    # 1. Очищаем строку и подставляем значения переменных шелла, если они есть
    expr = expr.strip()
    
    # Ищем буквенные переменные (например, X, COUNT) и подставляем их значения
    def replace_var(match):
        var_name = match.group(0)
        return str(shell_vars.get(var_name, 0))
    
    expr = re.sub(r'[a-zA-Z_][a-zA-Z0-9_]*', replace_var, expr)

    # 2. Быстрый и безопасный парсинг простейших выражений через re
    # Удаляем всё, кроме цифр, пробелов и базовых операторов (+, -, *, /, %, (, ))
    if not re.match(r'^[0-9\s\+\-\*\/\%\(\)]+$', expr):
        raise ValueError(f"Citadel Arith: Invalid characters in expression: {expr}")

    try:
        # Используем compile в режиме 'eval', но с пустыми глобалами/локалами
        # Это абсолютно безопасно, так как регулярка выше отсекла любые вызовы функций
        code = compile(expr, '<string>', 'eval')
        # Проверяем, что в коде нет скрытых вызовов имен (безопасность превыше всего)
        if code.co_names:
            raise ValueError("Citadel Arith: Security violation detected.")
        
        result = eval(code, {"__builtins__": {}}, {})
        return int(result)
    except Exception as e:
        raise ValueError(f"Citadel Arith: Syntax error in math logic: {e}")


def eval_test_condition(cond: str) -> bool:
    """
    Вычисляет логические условия из [[ ... ]].
    """
    # 1. СНАЧАЛА создаем переменную tokens (переносим на самый верх)
    tokens = cond.strip().split()
    if not tokens:
        return False

    # 2. И ТОЛЬКО ТЕПЕРЬ проверяем инверсию через "!"
    if tokens and tokens[0] == "!":
        remaining_cond = " ".join(tokens[1:])
        return not eval_test_condition(remaining_cond)
    if not tokens:
        return False

    op = tokens[0]
    
    # Одноместные операторы (флаги)
    if op in ('-f', '-d', '-z', '-n') and len(tokens) >= 2:
        target = tokens[1].strip('"\'')
        if op == '-f':
            return os.path.isfile(target)
        if op == '-d':
            return os.path.isdir(target)
        if op == '-z':
            return len(target) == 0
        if op == '-n':
            return len(target) > 0

    # Двуместные операторы сравнения (строки или числа)
    if len(tokens) == 3:
        left, op, right = tokens[0].strip('"\''), tokens[1], tokens[2].strip('"\'')
        if op in ('==', '='):
            return left == right
        if op == '!=':
            return left != right
        
        # Числовые сравнения
        try:
            left_num = int(left)
            right_num = int(right)
            if op == '-eq': return left_num == right_num
            if op == '-ne': return left_num != right_num
            if op == '-lt': return left_num < right_num
            if op == '-le': return left_num <= right_num
            if op == '-gt': return left_num > right_num
            if op == '-ge': return left_num >= right_num
        except ValueError:
            pass # Если не числа, возвращаем False

    return False