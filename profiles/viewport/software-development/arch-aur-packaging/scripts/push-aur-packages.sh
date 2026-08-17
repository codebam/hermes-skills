#!/usr/bin/env bash
# Push AUR packages after a Viewport release: copy PKGBUILD + .SRCINFO from
# the tree into fresh clones, commit, push, print pkgver per repo.
#
#   scripts/push-aur-packages.sh <version> [repo-dir]
#
# e.g. scripts/push-aur-packages.sh 0.1.7 /var/lib/hermes/workspace/Viewport
#
# Pushes the six versioned packages (cut from the release tag) and the three
# -git packages (whose pkgver markers were bumped in the release commit).
# Run after the release commit is pushed; needs SSH access to
# aur@aur.archlinux.org. Verification: fresh-clone back a few repos and grep
# pkgver — the AUR RPC API lags minutes, a clone does not.
set -euo pipefail

ver=${1:?usage: push-aur-packages.sh <version> [repo-dir]}
repo=${2:-$PWD}

# Repo owned by another user on this host (NixOS shared worktree).
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0='*'
work=$(mktemp -d /tmp/aur-push-XXXXXX)
trap 'rm -rf "$work"' EXIT

pkgs=(viewport-wpe viewport-wpe-bin viewport-webkitgtk viewport-webkitgtk-bin
      viewport-chromium viewport-chromium-bin viewport-wpe-git
      viewport-webkitgtk-git viewport-chromium-git)

for p in "${pkgs[@]}"; do
    echo "=== $p ==="
    git clone -q "ssh://aur@aur.archlinux.org/$p.git" "$work/$p"
    cp "$repo/packaging/aur/$p/PKGBUILD" "$work/$p/PKGBUILD"
    cp "$repo/packaging/aur/$p/.SRCINFO" "$work/$p/.SRCINFO"
    git -C "$work/$p" add -A
    # AUR clones carry no git identity; set it per-commit.
    git -C "$work/$p" -c user.name="Sean Behan" -c user.email="codebam@riseup.net" \
        commit -q -m "release: $ver" || true
    # Repos registered but never pushed clone as empty (no branches). Name
    # the branch BEFORE pushing or `push origin master` fails with
    # "src refspec master does not match any".
    if ! git -C "$work/$p" rev-parse --verify HEAD >/dev/null 2>&1; then
        git -C "$work/$p" checkout -q -b master
    fi
    git -C "$work/$p" push -q origin master
    echo "  pushed: $(git -C "$work/$p" log -1 --oneline)  pkgver=$(grep -m1 '^pkgver' "$work/$p/PKGBUILD" | cut -d= -f2)"
done
echo "ALL DONE"
