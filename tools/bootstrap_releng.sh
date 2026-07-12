#!/usr/bin/env bash
# bootstrap_releng.sh
#
# Bootstraps citadel_iso_build/ from the upstream archiso releng profile.
# Run this on the Arch Linux build host AFTER `git clone` / `git pull`.
#
# What it does:
#   1. Copies the entire releng skeleton into citadel_iso_build/
#      (this creates efiboot/, syslinux/, airootfs/etc/systemd/, etc.)
#   2. Restores our hand-tuned overrides from the current git HEAD:
#        - profiledef.sh    (bootmodes, image type)
#        - packages.x86_64  (Citadel + syslinux)
#        - pacman.conf      (Citadel-friendly mirrorlist refs)
#   3. Cleans up .gitkeep placeholders that we no longer need.
#   4. Stages a commit ready for `git push`.
#
# Requires: pacman -S archiso  (provides /usr/share/archiso/configs/releng)
#
# Usage:  ./tools/bootstrap_releng.sh

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
PROFILE_SRC="/usr/share/archiso/configs/releng"
PROFILE_DST="$REPO_ROOT/citadel_iso_build"

if [[ ! -d "$PROFILE_SRC" ]]; then
    echo "ERROR: $PROFILE_SRC not found." >&2
    echo "Install on this host with: sudo pacman -S archiso" >&2
    exit 1
fi

if [[ ! -d "$PROFILE_DST" ]]; then
    echo "ERROR: $PROFILE_DST not found — are you in the citadel repo root?" >&2
    exit 1
fi

echo "[*] Copying releng skeleton -> citadel_iso_build/"
# Trailing /. copies *contents* of releng into citadel_iso_build
cp -r "$PROFILE_SRC"/. "$PROFILE_DST"/

echo "[*] Restoring our custom overrides from git HEAD"
git checkout HEAD -- \
    "$PROFILE_DST/profiledef.sh" \
    "$PROFILE_DST/packages.x86_64" \
    "$PROFILE_DST/pacman.conf"

echo "[*] Removing .gitkeep placeholders superseded by real files"
find "$PROFILE_DST" -name ".gitkeep" -type f -delete

echo "[*] New top-level layout:"
ls -1 "$PROFILE_DST"

echo
echo "[*] Diff vs current branch (review before committing):"
git status --short
echo
echo "Next steps:"
echo "  git add citadel_iso_build/"
echo "  git commit -m 'build(iso): bootstrap releng skeleton with custom overrides'"
echo "  git push -u origin iso-build"
