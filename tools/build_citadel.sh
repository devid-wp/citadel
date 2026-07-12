#!/bin/bash
# build_citadel.sh
#
# End-to-end build of Citadel OS ISO.
# Run on the Arch Linux build host from the REPO ROOT.
# Requires: sudo pacman -S archiso reflector
#
# What it does:
#   1. Wipes mkarchiso's work directory.
#   2. Syncs this branch with origin/iso-build (non-fatal if it fails).
#   3. Stages fresh releng skeleton under citadel_iso_build/.
#   4. Generates a fast mirrorlist (via reflector) and ships it into the rootfs.
#   5. Re-applies our custom overrides (iso_name, bootmodes) on top of releng.
#   6. Runs mkarchiso INSIDE citadel_iso_build/ — so it sees only the
#      profile dir, not the whole repo tree.

set -euo pipefail

# FIX #1: bail loudly if we're not in a git repo (otherwise `git reset` would
# error in a confusing way later).
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "FATAL: not a git repo. cd into the citadel repo root first." >&2
    exit 1
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"
PROFILE_DIR="$REPO_ROOT/citadel_iso_build"
WORK_DIR="/tmp/archiso-work"
OUT_DIR="/tmp/archiso-out"

# FIX #2: refuse to run as root, but allow sudo for the specific commands that
# need it. archiso docs strongly recommend NOT running mkarchiso as root —
# it does its own privilege drops internally.
if [[ $EUID -eq 0 ]]; then
    echo "FATAL: don't run build_citadel.sh as root. Run as a normal user;" >&2
    echo "       the script will sudo where it needs elevated privileges." >&2
    exit 1
fi

if [[ ! -d "$PROFILE_DIR" ]]; then
    echo "FATAL: $PROFILE_DIR not found. Did you forget to switch to iso-build?" >&2
    exit 1
fi

if [[ ! -d /usr/share/archiso/configs/releng ]]; then
    echo "FATAL: /usr/share/archiso/configs/releng missing." >&2
    echo "       Install with: sudo pacman -S archiso" >&2
    exit 1
fi

echo "=== 1. Очистка старого кэша сборщика ==="
rm -rf "$WORK_DIR" "$OUT_DIR"

echo "=== 2. Сброс локальных изменений и пулл из Git ==="
# FIX #3: if pull fails (no network, no SSH key, etc.) we warn and continue
# with whatever's on disk — `git reset --hard` is still safe because we
# track everything we care about in origin/iso-build.
git reset --hard HEAD
if ! git pull origin iso-build; then
    echo "WARN: git pull failed, continuing with current working tree." >&2
fi

echo "=== 3. Накатывание свежего системного шаблона releng ==="
# FIX #4: copy the FULL releng tree (including dotfiles, if any) and STAGE
# it inside the profile dir, not into the repo root. Also restore our
# curated files from git *after* the copy so they win.
cp -r /usr/share/archiso/configs/releng/. "$PROFILE_DIR"/
git checkout HEAD -- \
    "$PROFILE_DIR/profiledef.sh" \
    "$PROFILE_DIR/packages.x86_64" \
    "$PROFILE_DIR/pacman.conf"

echo "=== 4. Тюнинг зеркал pacman на максимальную скорость ==="
# FIX #5: reflector needs root. We sudo it, then ship the mirrorlist into
# the rootfs skeleton, NOT on top of pacman.conf (which is a section-based
# config, not a URL list — replacing it would break mkarchiso).
sudo reflector --latest 20 --protocol https --sort rate \
    --save /etc/pacman.d/mirrorlist
mkdir -p "$PROFILE_DIR/airootfs/etc/pacman.d"
cp /etc/pacman.d/mirrorlist "$PROFILE_DIR/airootfs/etc/pacman.d/mirrorlist"

echo "=== 5. Применение кастомных настроек Citadel OS ==="
# FIX #6: anchor the bootmodes sed with ^ so we only match the line
# `bootmodes=...` at start of line, not any later occurrence in comments.
sed -i 's/iso_name="archiso"/iso_name="citadelos"/' "$PROFILE_DIR/profiledef.sh"
sed -i "s|^bootmodes=.*|bootmodes=('uefi-x64.systemd-boot.esp' 'uefi-x64.systemd-boot.eltorito')|" \
    "$PROFILE_DIR/profiledef.sh"

echo "=== 6. ЗАПУСК ХАРДКОРНОЙ СБОРКИ ==="
# FIX #7: cd into the profile dir, otherwise mkarchiso will sweep the
# whole repo (apps/, core/, __pycache__/, tests/, .venv/...) into the
# airootfs overlay.
cd "$PROFILE_DIR"
mkarchiso -v -w "$WORK_DIR" -o "$OUT_DIR" .

echo
echo "=== Готово. ISO в: $OUT_DIR ==="
ls -lh "$OUT_DIR"
