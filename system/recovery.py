import os
import shutil
import sys
import time
import glob
import json
import atexit
import traceback
from typing import Any, Callable, List, Optional
import config
from core.interface import clear_screen, terminal_print, display_table, get_theme_color, display_progress_bar

BACKUP_DIR = "system/backups"

# Recovery snapshots (Фаза 2.5). Каждый крах / штатный выход пишет JSON
# в ~/.citadel_recovery/{timestamp}.json — pwd, последние команды, traceback.
RECOVERY_DIR = os.path.expanduser("~/.citadel_recovery")
RECOVERY_KEEP = 10  # сколько последних снапшотов хранить

# Reason-теги для имени файла и поля "reason" внутри JSON.
REASON_EXIT = "exit"             # штатный выход (exit/q/quit/EOF)
REASON_INTERRUPT = "interrupt"   # KeyboardInterrupt
REASON_CRASH = "crash"           # непойманное исключение
REASON_SIGTERM = "sigterm"       # SIGTERM (через сигнал-хук)

_VALID_REASONS = frozenset({REASON_EXIT, REASON_INTERRUPT, REASON_CRASH, REASON_SIGTERM})

def create_backup():
    """Создает резервную копию конфигурации config.py"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"config_backup_{timestamp}.py")

    try:
        shutil.copy("config.py", backup_file)
        return True, backup_file
    except Exception as e:
        return False, str(e)

def get_backups():
    """Возвращает список существующих резервных копий"""
    if not os.path.exists(BACKUP_DIR):
        return []
    files = glob.glob(os.path.join(BACKUP_DIR, "config_backup_*.py"))
    # Сортируем по времени изменения от новых к старым
    files.sort(key=os.path.getmtime, reverse=True)
    return files

def restore_backup(backup_path):
    """Восстанавливает config.py из бэкапа"""
    if not os.path.exists(backup_path):
        return False, "Файл бэкапа не найден"
    try:
        shutil.copy(backup_path, "config.py")
        return True, "Файл конфигурации восстановлен. Перезагрузите терминал для применения изменений."
    except Exception as e:
        return False, str(e)

def check_system_integrity():
    """Проверяет целостность критических файлов системы Citadel"""
    critical_files = [
        "main.py",
        "config.py",
        "core/interface.py",
        "core/auth.py",
        "core/shell_utils.py",
        "system/hardware.py",
        "system/process_mgr.py",
        "system/network.py",
        "system/package_mgr.py",
        "system/recovery.py",
        "system/geo.py",
        "system/user_config.py",
        "system/logger.py",
        "apps/crypto.py",
        "apps/passgen.py",
        "apps/file_browser.py",
        "apps/notes.py",
        "apps/launcher.py",
        "apps/weather.py",
    ]

    headers = ["Файл", "Статус", "Размер", "Рекомендация"]
    rows = []

    for filepath in critical_files:
        if not os.path.exists(filepath):
            rows.append([filepath, "ОТСУТСТВУЕТ", "0 байт", "Пересоздать / восстановить"])
        else:
            size = os.path.getsize(filepath)
            if size == 0:
                rows.append([filepath, "ПУСТОЙ / ПОВРЕЖДЕН", f"{size} байт", "Перезаписать рабочий код"])
            else:
                rows.append([filepath, "ОК", f"{size} байт", "Действие не требуется"])

    return headers, rows

def run_recovery_menu():
    """Интерактивное меню системы восстановления"""
    while True:
        clear_screen()
        theme_color = get_theme_color()
        reset = config.COLORS["RESET"]
        green = config.COLORS["GREEN"]
        red = config.COLORS["RED"]

        print(f"{theme_color}==================================================")
        print("          СИСТЕМА ВОССТАНОВЛЕНИЯ CITADEL          ")
        print(f"=================================================={reset}")
        print("\nВыберите действие:")
        print("[1] Проверить целостность файлов системы")
        print("[2] Создать резервную копию конфигурации (config.py)")
        print("[3] Восстановить конфигурацию из резервной копии")
        print("[B] Вернуться назад (Back)")

        choice = input("\nВведите пункт меню: ").strip().lower()

        if choice == '1':
            clear_screen()
            print(f"{theme_color}--- Проверка целостности компонентов системы ---{reset}\n")
            headers, rows = check_system_integrity()
            display_table(headers, rows)

            any_corrupt = any(r[1] != "ОК" for r in rows)
            if any_corrupt:
                print(f"\n{red}[ WARNING ]: Обнаружены поврежденные или отсутствующие компоненты!{reset}")
            else:
                print(f"\n{green}[ SUCCESS ]: Все критические файлы целостны.{reset}")

            input("\nНажмите Enter для продолжения...")

        elif choice == '2':
            clear_screen()
            print("Создание точки восстановления...")
            display_progress_bar(1.0, "Резервное копирование")
            success, path = create_backup()
            if success:
                print(f"{green}[ SUCCESS ]: Бэкап успешно создан: {os.path.basename(path)}{reset}")
            else:
                print(f"{red}[ ERROR ]: Ошибка создания бэкапа: {path}{reset}")
            input("\nНажмите Enter для продолжения...")

        elif choice == '3':
            clear_screen()
            backups = get_backups()
            if not backups:
                print("Резервные копии не найдены.")
                input("\nНажмите Enter для продолжения...")
                continue

            print(f"{theme_color}Доступные точки восстановления:{reset}\n")
            for idx, path in enumerate(backups, 1):
                mtime = time.ctime(os.path.getmtime(path))
                print(f"[{idx}] {os.path.basename(path)} (Создан: {mtime})")

            select = input("\nВыберите номер бэкапа для восстановления или 'b' для отмены: ").strip()
            if select.lower() == 'b':
                continue

            try:
                num = int(select)
                if 1 <= num <= len(backups):
                    target = backups[num - 1]
                    display_progress_bar(1.2, "Восстановление конфигурации")
                    success, msg = restore_backup(target)
                    if success:
                        print(f"{green}[ SUCCESS ]: {msg}{reset}")
                    else:
                        print(f"{red}[ ERROR ]: {msg}{reset}")
                else:
                    print("Неверный номер.")
            except ValueError:
                print("Некорректный ввод.")
            input("\nНажмите Enter для продолжения...")

        elif choice == 'b':
            break


# ============================================================================
# Фаза 2.5: Session snapshot (recovery)
# ============================================================================
#
# При крахе или штатном выходе сохраняем pwd + последние команды +
# traceback в ~/.citadel_recovery/{timestamp}_{reason}.json.
#
# Использование:
#
#   from system.recovery import (
#       install_recovery_hooks, snapshot_session,
#       REASON_EXIT, REASON_INTERRUPT, REASON_CRASH,
#   )
#
#   set_state = install_recovery_hooks(initial_cwd=os.getcwd(), recent_cmds=[])
#   ...
#   set_state(cwd=os.getcwd(), recent_cmds=[...])   # обновлять по ходу сессии
#   ...
#   snapshot_session(reason=REASON_CRASH, cwd=..., recent_cmds_provider=...)
#
# Контракт:
#   • install_recovery_hooks() возвращает callable (set_state) — НЕ
#     сохраняет ссылку на cwd/истории (получает их через provider на exit).
#   • snapshot_session() сама вытаскивает cwd/recent через provider'ов,
#     переданных в atexit-хуке или вызванной напрямую.
#   • Внутри snapshot_session() НЕ ловим свои исключения — если запись
#     не удалась (нет прав / диск кончился), это и так fatal recovery.

_session_state_lock_calls: List[tuple] = []  # диагностика: какие state-update'ы пришли


def _ensure_recovery_dir() -> None:
    """Создать ~/.citadel_recovery/ если не существует."""
    try:
        os.makedirs(RECOVERY_DIR, exist_ok=True)
    except OSError:
        pass


def _prune_old_snapshots(keep: int = RECOVERY_KEEP) -> None:
    """Оставить только N самых свежих снапшотов. Остальные удалить."""
    if not os.path.isdir(RECOVERY_DIR):
        return
    try:
        files = sorted(
            (os.path.join(RECOVERY_DIR, f) for f in os.listdir(RECOVERY_DIR)
             if f.startswith("recovery_") and f.endswith(".json")),
            key=os.path.getmtime,
            reverse=True,
        )
        for old in files[keep:]:
            try:
                os.unlink(old)
            except OSError:
                pass
    except OSError:
        pass


def _safe_provider(provider, default):
    """Безопасно вызвать provider; вернуть default при любом исключении."""
    if provider is None:
        return default
    try:
        result = provider()
        return result if result is not None else default
    except Exception:  # noqa: BLE001
        return default


def snapshot_session(
    reason: str,
    cwd: Optional[str] = None,
    recent_cmds: Optional[List[str]] = None,
    recent_cmds_provider: Optional[Callable[[], List[str]]] = None,
    traceback_text: Optional[str] = None,
    exc: Optional[BaseException] = None,
    extra: Optional[dict] = None,
) -> Optional[str]:
    """
    Сделать снапшот текущей сессии в ~/.citadel_recovery/.

    Args:
        reason: одна из REASON_EXIT / REASON_INTERRUPT / REASON_CRASH /
                REASON_SIGTERM. Любая другая строка — допустима, но для
                единообразия лучше использовать константы.
        cwd: текущая рабочая директория (если None — берётся os.getcwd()).
        recent_cmds: явный список последних команд (для прямого вызова).
        recent_cmds_provider: callable() -> list[str] (для atexit-хука,
                             когда список может расти в момент exit).
        traceback_text: готовый traceback (для crash-ветки).
        exc: исключение (если задано — вытащим из него __traceback__).
        extra: дополнительные поля для JSON (например, "version": "3.0").

    Returns:
        Полный путь к файлу снапшота, либо None при ошибке записи.
    """
    if reason not in _VALID_REASONS:
        # Не валим caller: всё-таки пишем, но помечаем как "other".
        reason_tag = f"other_{reason}" if reason else "other"
    else:
        reason_tag = reason

    # Если нам передали exc, попробуем вытащить traceback из него.
    if exc is not None and traceback_text is None:
        try:
            traceback_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        except Exception:  # noqa: BLE001
            traceback_text = None

    # Cwd: явный аргумент > os.getcwd() > "unknown".
    if cwd is None:
        try:
            cwd = os.getcwd()
        except OSError:
            cwd = "<unknown>"

    # recent_cmds: явный > provider > [].
    if recent_cmds is None:
        recent_cmds = _safe_provider(recent_cmds_provider, default=[])

    _ensure_recovery_dir()

    ts = time.strftime("%Y%m%d_%H%M%S")
    # Добавим микросекунды, чтобы уникально различать rapid-fire краши.
    ts_full = f"{ts}_{int((time.time() % 1) * 1000):03d}"
    filename = f"recovery_{ts_full}_{reason_tag}.json"
    path = os.path.join(RECOVERY_DIR, filename)

    payload: dict[str, Any] = {
        "schema": "citadel.recovery/v1",
        "ts": time.time(),
        "ts_human": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "reason": reason_tag,
        "cwd": cwd,
        "recent_cmds": list(recent_cmds),
        "user": getattr(config, "USER_NAME", "unknown"),
        "version": getattr(config, "VERSION", "unknown"),
    }
    if traceback_text:
        payload["traceback"] = traceback_text
    if extra:
        payload["extra"] = dict(extra)

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        _prune_old_snapshots(RECOVERY_KEEP)
        return path
    except OSError:
        return None


def install_recovery_hooks(
    initial_cwd: str,
    recent_cmds: Optional[List[str]] = None,
) -> Callable[..., None]:
    """
    Установить глобальные хуки recovery:
      • sys.excepthook — снапшот при непойманном исключении;
      • сигнал SIGTERM (если модуль signal доступен) — снапшот;
      • atexit НЕ ставим здесь (его ставит вызывающий код, чтобы передать
        свои provider'ы — например, замыкание на CMD_HISTORY).

    Возвращает set_session_state(cwd, recent_cmds) — caller зовёт его на
    каждой итерации REPL, чтобы обновлять cwd/истории для будущего
    snapshot_session(REASON_CRASH, ...).
    """
    state: dict[str, Any] = {
        "cwd": initial_cwd,
        "recent_cmds": list(recent_cmds) if recent_cmds else [],
    }

    def set_session_state(cwd: Optional[str] = None, recent_cmds: Optional[List[str]] = None) -> None:
        if cwd is not None:
            state["cwd"] = cwd
        if recent_cmds is not None:
            state["recent_cmds"] = list(recent_cmds)[-20:]

    def _excepthook(exc_type, exc_value, exc_tb):
        # Пишем traceback. Не вызываем sys.__excepthook__ — нам важно,
        # чтобы пользователь увидел traceback и в stderr (если шелл ещё жив).
        try:
            tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            # 1) Зеркалим в stderr (стандартное поведение Python).
            sys.stderr.write(tb_text)
            sys.stderr.flush()
            # 2) Делаем снапшот.
            snapshot_session(
                reason=REASON_CRASH,
                cwd=state["cwd"],
                recent_cmds=state["recent_cmds"],
                traceback_text=tb_text,
            )
        except Exception:  # noqa: BLE001
            # В хуке не должно быть НИКАКИХ непойманных исключений — иначе
            # Python зациклится на нашем же excepthook.
            try:
                sys.__excepthook__(exc_type, exc_value, exc_tb)
            except Exception:  # noqa: BLE001
                pass

    sys.excepthook = _excepthook

    # SIGTERM — best-effort. На Windows сигналы работают иначе (только
    # SIGINT, SIGBREAK, SIGTERM), и то не всегда. Не падаем, если модуль
    # signal недоступен (например, в подпроцессе).
    try:
        import signal as _signal
        def _sigterm_handler(signum, frame):  # noqa: ARG001
            snapshot_session(
                reason=REASON_SIGTERM,
                cwd=state["cwd"],
                recent_cmds=state["recent_cmds"],
            )
            # Восстановим default-поведение и пошлём сигнал себе ещё раз,
            # чтобы корректно завершиться.
            try:
                _signal.signal(_signal.SIGTERM, _signal.SIG_DFL)
                os.kill(os.getpid(), _signal.SIGTERM)
            except Exception:  # noqa: BLE001
                sys.exit(128 + signum)
        try:
            _signal.signal(_signal.SIGTERM, _sigterm_handler)
        except (ValueError, OSError, AttributeError):
            # Не в main thread / платформа не позволяет — пропускаем.
            pass
    except ImportError:
        pass

    return set_session_state


def list_recovery_snapshots() -> List[dict]:
    """
    Вернуть список снапшотов (новейшие первые) — для утилит восстановления
    и для тестов.

    Returns:
        [{path, ts, reason, cwd, recent_cmds: [...], ...}, ...]
    """
    if not os.path.isdir(RECOVERY_DIR):
        return []
    out: List[dict] = []
    try:
        for name in os.listdir(RECOVERY_DIR):
            if not (name.startswith("recovery_") and name.endswith(".json")):
                continue
            p = os.path.join(RECOVERY_DIR, name)
            try:
                with open(p, "r", encoding="utf-8") as f:
                    payload = json.load(f)
            except (OSError, json.JSONDecodeError, ValueError):
                continue
            out.append({"path": p, **payload})
    except OSError:
        return []
    # Newest first — по полю ts из payload (монотонный clock), а не по имени
    # файла: имя включает только секунды + миллисекунды от time.time()%1,
    # так что rapid-fire крахи могут иметь одинаковый ts.
    out.sort(key=lambda d: d.get("ts", 0.0), reverse=True)
    return out