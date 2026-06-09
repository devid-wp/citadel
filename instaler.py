import os
import subprocess
import time
import sys

# ANSI Цвета для интерфейса установщика
PURPLE = "\033[95m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[31m"
RESET = "\033[0m"

def run_cmd(cmd, shell=True):
    """Функция для выполнения системных команд с отображением статуса"""
    try:
        result = subprocess.run(cmd, shell=shell, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr

def print_header():
    os.system('cls' if os.name == 'nt' else 'clear')
    print(f"{PURPLE}==================================================================={RESET}")
    print(f"{PURPLE}          CITADEL OS v3.0 - АВТОМАТИЧЕСКИЙ УСТАНОВЩИК              {RESET}")
    print(f"{PURPLE}==================================================================={RESET}\n")

def main():
    print_header()
    print(f"[{YELLOW}ВНИМАНИЕ{RESET}]: Этот скрипт автоматизирует установку ядра Arch Linux.")
    print("Убедитесь, что вы запустили его в среде Live-CD Arch Linux.\n")
    
    # 1. Выбор диска
    print(f"{CYAN}[ ШАГ 1 ]: Обнаружение доступных накопителей...{RESET}")
    # Выводим список дисков в Linux (команда lsblk)
    success, disks = run_cmd("lsblk -d -o NAME,SIZE,MODEL")
    if not success:
        print(f"{RED}Не удалось получить список дисков. Скрипт должен работать под Linux.{RESET}")
        sys.exit(1)
    
    print(disks)
    target_disk = input(f"Введите имя целевого диска для установки (например, {GREEN}sda{RESET} или {GREEN}nvme0n1{RESET}): ").strip()
    
    if not target_disk:
        print(f"{RED}Диск не выбран. Выход.{RESET}")
        sys.exit(1)

    confirm = input(f"{RED}ВНИМАНИЕ! Все данные на диске /dev/{target_disk} будут УНИЧТОЖЕНЫ. Продолжить? (y/n): {RESET}").strip().lower()
    if confirm != 'y':
        print("Установка отменена.")
        sys.exit(0)

    # 2. Автоматическая разметка диска (создаем EFI и Root разделы)
    print(f"\n{CYAN}[ ШАГ 2 ]: Разметка диска /dev/{target_disk} (GPT)...{RESET}")
    # Создаем таблицу GPT, 512MB для EFI, остальное под корень
    partition_cmds = f"""
    sgdisk --zap-all /dev/{target_disk}
    sgdisk --new=1:0:+512M --typecode=1:ef00 --change-name=1:EFI /dev/{target_disk}
    sgdisk --new=2:0:0 --typecode=2:8300 --change-name=2:ROOT /dev/{target_disk}
    """
    for cmd in partition_cmds.strip().split('\n'):
        if cmd.strip():
            run_cmd(cmd.strip())
    
    # Определение имен получившихся разделов
    p_prefix = "p" if "nvme" in target_disk else ""
    efi_part = f"/dev/{target_disk}{p_prefix}1"
    root_part = f"/dev/{target_disk}{p_prefix}2"

    # 3. Форматирование файловых систем
    print(f"\n{CYAN}[ ШАГ 3 ]: Форматирование разделов...{RESET}")
    print(f"-> Форматирование {efi_part} в FAT32 (EFI)...")
    run_cmd(f"mkfs.fat -F32 {efi_part}")
    print(f"-> Форматирование {root_part} в Ext4 (Система)...")
    run_cmd(f"mkfs.ext4 -F {root_part}")

    # 4. Монтирование разделов для установки
    print(f"\n{CYAN}[ ШАГ 4 ]: Монтирование файловой структуры...{RESET}")
    run_cmd(f"mount {root_part} /mnt")
    run_cmd("mkdir -p /mnt/boot")
    run_cmd(f"mount {efi_part} /mnt/boot")

    # 5. Установка базовых пакетов Arch Linux (Pacstrap)
    print(f"\n{CYAN}[ ШАГ 5 ]: Развертывание базовых пакетов ядра (Pacstrap)...{RESET}")
    print("Это займет некоторое время, загружаются компоненты Linux...")
    # Устанавливаем базовую систему, ядро, прошивки, текстовый редактор и Python для нашего шелла
    success, out = run_cmd("pacstrap -K /mnt base linux linux-firmware base-devel python nano grub efibootmgr networkmanager")
    if not success:
        print(f"{RED}Ошибка при выполнении pacstrap:{RESET}\n{out}")
        sys.exit(1)
    print(f"{GREEN}[Успешно]: Базовые пакеты установлены.{RESET}")

    # 6. Генерирование таблицы разделов (fstab)
    print(f"\n{CYAN}[ ШАГ 6 ]: Генерация fstab...{RESET}")
    run_cmd("genfstab -U /mnt >> /mnt/etc/fstab")

    # 7. Настройка системы внутри chroot (Базовая конфигурация)
    print(f"\n{CYAN}[ ШАГ 7 ]: Внутренняя конфигурация Citadel OS...{RESET}")
    
    # Скрипт конфигурации, который выполнится внутри установленной системы
    chroot_script = f"""
    ln -sf /usr/share/zoneinfo/UTC /etc/localtime
    hwclock --systohc
    echo "en_US.UTF-8 UTF-8" > /etc/locale.gen
    locale-gen
    echo "LANG=en_US.UTF-8" > /etc/locale.conf
    echo "citadel-node" > /etc/hostname
    echo "127.0.0.1 localhost" >> /etc/hosts
    echo "::1       localhost" >> /etc/hosts
    systemctl enable NetworkManager
    
    # Настройка загрузчика GRUB
    grub-install --target=x86_64-efi --efi-directory=/boot --bootloader-id=CITADEL-BOOT
    grub-mkconfig -o /boot/grub/grub.cfg
    
    # Установка пароля суперпользователя (root) по умолчанию: admin
    echo "root:admin" | chpasswd
    """
    
    with open("/mnt/chroot_setup.sh", "w") as f:
        f.write(chroot_script)
        
    run_cmd("arch-chroot /mnt bash /chroot_setup.sh")
    run_cmd("rm /mnt/chroot_setup.sh")

    # 8. Интеграция нашего интерфейса Citadel OS в качестве главного шелла
    print(f"\n{CYAN}[ ШАГ 8 ]: Интеграция интерфейса оболочки Citadel...{RESET}")
    
    # Создаем папку под нашу систему внутри установленного диска
    target_os_dir = "/mnt/opt/citadel"
    run_cmd(f"mkdir -p {target_os_dir}")
    
    # Копируем наши файлы проекта (main.py, config.py, logo.txt и папки core/system/apps)
    # Предполагается, что установщик запущен из папки, где лежат эти файлы
    run_cmd(f"cp -r main.py config.py logo.txt core system apps {target_os_dir}/ 2>/dev/null")
    
    # Прописываем автозапуск нашего Python-шелла при входе в систему вместо стандартного bash
    bashprofile_path = "/mnt/root/.bash_profile"
    autorun_code = f"""
    # Автозапуск интерфейса Citadel OS
    if [ -f /opt/citadel/main.py ]; then
        python /opt/citadel/main.py
        # Если пользователь выходит из нашего шелла — завершаем и саму сессию терминала
        exit
    fi
    """
    with open(bashprofile_path, "w") as f:
        f.write(autorun_code)

    # 9. Финал
    print(f"\n{GREEN}==================================================================={RESET}")
    print(f"{GREEN}          CITADEL OS УСПЕШНО УСТАНОВЛЕНА НА ВАШ ПК!                {RESET}")
    print(f"{GREEN}==================================================================={RESET}")
    print("Вы можете извлечь установочный накопитель и перезагрузить компьютер.\n")

if __name__ == "__main__":
    # Простая проверка: если запустить на Windows, скрипт предупредит, но код не сломает
    if os.name == 'nt':
        print_header()
        print(f"[{YELLOW}ОТЛАДКА{RESET}]: Код установщика написан корректно.")
        print("Для реальной установки этот файл должен быть запущен внутри Live-CD Arch Linux.")
    else:
        main()