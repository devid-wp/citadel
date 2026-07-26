import os
import sys
import subprocess
import io
import shlex  # Этот модуль умеет правильно разбивать строки, сохраняя кавычки!
from core.shell_utils import run_command as citadel_legacy_executor

def builtin_cd(args):
    if not args:
        path = os.path.expanduser("~")
    else:
        path = args[0]
    try:
        os.chdir(path)
        return 0
    except Exception as e:
        print(f"Citadel: cd: {e}", file=sys.stderr)
        return 1

def builtin_echo(args):
    print(" ".join(args))
    return 0

def builtin_exit(args):
    return -1

# ВАЖНО: Словарь должен быть строго ВЫШЕ функций, которые его используют!
CORE_BUILTINS = {
    "cd": builtin_cd,
    "echo": builtin_echo,
    "exit": builtin_exit,
}

def run_external_command(cmd_name, args, stdin=sys.stdin, stdout=sys.stdout):
    full_command = [cmd_name] + args
    env_context = os.environ.copy()
    env_context["CITADEL_SHELL"] = "3.0"
    env_context["PWD"] = os.getcwd()
    
    try:
        result = subprocess.run(
            full_command, 
            stdin=stdin, 
            stdout=stdout, 
            stderr=sys.stderr,
            env=env_context,
            text=True
        )
        return result.returncode
    except FileNotFoundError:
        print(f"Citadel: command not found: {cmd_name}", file=sys.stderr)
        return 127
    except KeyboardInterrupt:
        print("\n[ Citadel: Process interrupted ]")
        return 130
    except Exception as e:
        print(f"Citadel: error: {e}", file=sys.stderr)
        return 1

def run_piped_commands(pipe_commands):
    env_context = os.environ.copy()
    env_context["CITADEL_SHELL"] = "3.0"
    env_context["PWD"] = os.getcwd()
    last_stdout = None

    try:
        for i, cmd_parts in enumerate(pipe_commands):
            if not cmd_parts:
                continue

            cmd_name = cmd_parts[0]
            cmd_args = cmd_parts[1:]
            is_last = (i == len(pipe_commands) - 1)

            # 1. Если команда встроенная (echo, cd)
            if cmd_name in CORE_BUILTINS:
                old_stdout = sys.stdout
                sys.stdout = capture_output = io.StringIO()
                
                CORE_BUILTINS[cmd_name](cmd_args)
                
                sys.stdout = old_stdout
                builtin_result = capture_output.getvalue()

                if is_last:
                    print(builtin_result, end="")
                else:
                    last_stdout = builtin_result
                continue

            # 2. Если команда внешняя (findstr, grep)
            if i == 0:
                current_stdin = sys.stdin
                p_stdin_data = None
            else:
                if isinstance(last_stdout, str):
                    current_stdin = subprocess.PIPE  # Будем вливать через communicate
                    p_stdin_data = last_stdout
                else:
                    current_stdin = last_stdout.stdout
                    p_stdin_data = None

            current_stdout = sys.stdout if is_last else subprocess.PIPE

            p = subprocess.Popen(
                cmd_parts,
                stdin=current_stdin,
                stdout=current_stdout,
                stderr=sys.stderr,
                env=env_context,
                text=True
            )

            # Вот тут магия: если на вход идет строка от встроенной команды, 
            # используем communicate(), чтобы принудительно протолкнуть её и завершить процесс
            if p_stdin_data is not None:
                out, _ = p.communicate(input=p_stdin_data)
                if is_last and out:
                    print(out, end="")
                last_stdout = out
            else:
                last_stdout = p

        if isinstance(last_stdout, subprocess.Popen):
            return last_stdout.wait()
        return 0

    except FileNotFoundError:
        print(f"Citadel: Pipeline error (binary not found)", file=sys.stderr)
        return 127
    except Exception as e:
        print(f"Citadel: Pipe error: {e}", file=sys.stderr)
        return 1

def run_command(user_input):
    raw_input = user_input.strip()
    if not raw_input:
        return 0

    # Если есть пайп, бьем через shlex.split, чтобы не ломать строки внутри кавычек
    if "|" in raw_input:
        pipe_parts = [shlex.split(cmd.strip()) for cmd in raw_input.split("|") if cmd.strip()]
        return run_piped_commands(pipe_parts)

    # Для обычных одиночных команд тоже юзаем shlex.split
    try:
        parts = shlex.split(raw_input)
    except ValueError:
        parts = raw_input.split() # Фолбэк на случай незакрытых кавычек
        
    if not parts:
        return 0
        
    cmd_name = parts[0]
    cmd_args = parts[1:]
    
    if cmd_name in CORE_BUILTINS:
        return CORE_BUILTINS[cmd_name](cmd_args)
        
    try:
        KNOWN_CITADEL_CMDS = {
            "help", "clear", "fetch", "center", "pkg", "netscan", "ip", 
            "sysmon", "ps", "kill", "df", "files", "notes", "crypto", 
            "passgen", "weather", "geo", "log", "alias", "lock", "launcher", 
            "recovery", "history", "ls"
        }
        if cmd_name in KNOWN_CITADEL_CMDS:
            return citadel_legacy_executor(user_input)
    except Exception:
        pass
        
    return run_external_command(cmd_name, cmd_args)