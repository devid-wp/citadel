#!/bin/bash
set -e

echo "=== 1. Cleaning old cache on disk ==="
rm -rf ./archiso-work

echo "=== 2. Resetting local changes and pulling from Git ==="
git reset --hard HEAD
git pull origin iso-build

echo "=== 3. Applying fresh releng system template ==="
cp -r /usr/share/archiso/configs/releng/* .

echo "=== 4. Tuning pacman mirrors for maximum speed ==="
reflector --latest 20 --protocol https --sort rate --save /etc/pacman.d/mirrorlist
cp /etc/pacman.d/mirrorlist pacman.conf

echo "=== 5. Applying Citadel OS customizations ==="
sed -i 's/iso_name="archiso"/iso_name="citadelos"/' profiledef.sh
sed -i "s/bootmodes=.*/bootmodes=('uefi-x64.systemd-boot.esp' 'uefi-x64.systemd-boot.eltorito')/" profiledef.sh

echo "=== 6. STARTING ISO BUILD ON DISK ==="
mkarchiso -v -w ./archiso-work -o ./archiso-out .
