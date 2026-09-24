#!/usr/bin/env bash
# Cron-safe prologue for a Hermes pre-run collector script.
#
# WHY THIS EXISTS
# Hermes cron executes `script=` with the *gateway process* environment, not the
# PATH of your interactive shell. On NixOS that PATH is a /nix/store-only list:
# no /run/current-system/sw/bin and no /etc/profiles/per-user/<user>/bin. So
# zstd, jq, awk, find and sed all resolve perfectly by hand and read as
# "command not found" the moment the job fires. A collector that passed every
# interactive test died on its first scheduled run with:
#
#   dsh-task-scan: missing dependency: zstd
#
# Prepend the standard locations before any dependency check. _add_path is
# idempotent and skips directories that do not exist, so the same prologue is
# safe on Linux, macOS, and non-Nix systems.
set -uo pipefail

_add_path() { case ":$PATH:" in *":$1:"*) ;; *) [ -d "$1" ] && PATH="$1:$PATH" ;; esac; }
# NixOS / nix profiles (where Hermes scripts usually live)
_add_path /run/current-system/sw/bin          # zstd, gawk, findutils, coreutils
_add_path /run/wrappers/bin
_add_path "$HOME/.nix-profile/bin"
_add_path "$HOME/.local/state/nix/profile/bin"
_add_path "/etc/profiles/per-user/${USER:-$(id -un 2>/dev/null || echo unknown)}/bin"  # jq, node
# conventional locations elsewhere
_add_path /usr/local/bin
_add_path /usr/bin
_add_path /bin
_add_path /opt/homebrew/bin
export PATH

# Assert every dependency up front, and echo the PATH that was actually used —
# the next person to debug this needs to see why a tool was invisible.
_missing=""
for dep in zstd jq awk find; do
  command -v "$dep" >/dev/null 2>&1 || _missing="$_missing $dep"
done
if [ -n "$_missing" ]; then
  echo "collector: missing dependencies:$_missing"
  echo "collector: PATH=$PATH"
  exit 1
fi

# ---------------------------------------------------------------------------
# ...collector body: read the source, bound it, print the digest payload...
#
# Conventions that make the payload usable by the job's prompt (see the
# umbrella SKILL.md, Phase 2):
#   - print a header line (when it ran, window, how many sources)
#   - emit TSV via jq @tsv, one row per line
#   - format times with gawk strftime (local), never jq (UTC)
#   - cap per kind and per source; two-tier detail vs stub under byte budgets
#   - print a closing legend explaining what each section means
#   - exit 0 with a human sentence when the source is empty
# ---------------------------------------------------------------------------
