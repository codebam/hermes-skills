#!/usr/bin/env bash
# Validate fail2ban + nftables changes in a BUILT (not activated) NixOS system.
# Usage: validate-built-fail2ban.sh <system-toplevel-store-path> [logfile]
#   logfile: lines to run through fail2ban-regex (attack lines must match).
#   The nft step needs root -> uses run0.
set -u
SYS=${1:?usage: $0 <system-toplevel-store-path> [logfile]}
LOG=${2:-}
FAIL=0
ok()  { printf 'PASS: %s\n' "$1"; }
bad() { printf 'FAIL: %s\n' "$1"; FAIL=1; }
[ -d "$SYS" ] || { echo "not a store path: $SYS"; exit 2; }

printf '== fail2ban config test (real server, built config)\n'
if "$SYS/sw/bin/fail2ban-server" -c "$SYS/etc/fail2ban" -t >/dev/null 2>&1; then ok "fail2ban-server -t"; else bad "fail2ban-server -t"; fi

if [ -n "$LOG" ]; then
  printf '== filter matching against %s\n' "$LOG"
  for f in "$SYS"/etc/fail2ban/filter.d/*.conf; do
    [ -f "$f" ] || continue
    "$SYS/sw/bin/fail2ban-regex" "$LOG" "$f" 2>&1 | grep -E '^Lines:' | sed "s|^|  $(basename "$f"): |"
  done
fi

printf '== nftables ruleset parses and is loadable\n'
RULES=$(grep -oE '/nix/store/[a-z0-9]+-nftables-rules' "$SYS/etc/systemd/system/nftables.service" | head -1)
[ -n "$RULES" ] || RULES=$(find "$SYS" -maxdepth 1 -name '*-nftables-rules' | head -1)
if [ -n "$RULES" ] && timeout 30 run0 nft -c -f "$RULES" >/dev/null 2>&1; then
  ok "nft -c parses $RULES"
else
  bad "nft -c parse (rules=$RULES)"
fi

echo
if [ "$FAIL" -eq 0 ]; then echo "ALL PASS"; else echo "FAILURES PRESENT"; exit 1; fi