#!/bin/bash
set -e

echo "=== 1. Очистка старого кэша на диске ==="
rm -rf ./archiso-work

echo "=== 2. Сброс локальных изменений и пулл из Git ==="
git reset --hard HEAD
git pull origin iso-build

echo "=== 3. Накатывание свежего системного шаблона releng ==="
cp -r /usr/share/archiso/configs/releng/* .

echo "=== 4. Тюнинг зеркал pacman на максимальную скорость ==="
reflector --latest 20 --protocol https --sort rate --save /etc/pacman.d/mirrorlist
cp /etc/pacman.d/mirrorlist pacman.conf

echo "=== 5. Применение кастомных настроек Citadel OS ==="
sed -i 's/iso_name="archiso"/iso_name="citadelos"/' profiledef.sh
sed -i "s/bootmodes=.*/bootmodes=('uefi-x64.systemd-boot.esp' 'uefi-x64.systemd-boot.eltorito')/" profiledef.sh

echo "=== 6. ЗАПУСК СБОРКИ НА ДИСКЕ ==="
mkarchiso -v -w ./archiso-work -o ./archiso-out .
