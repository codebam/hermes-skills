# fail2ban 1.1 filter authoring (verified against fail2ban 1.1.0, nixpkgs 26.11)

Condensed from a live debugging session (2026-08) — the mechanism, not just
the recipe.

## failure-id requirement

`fail2ban/server/failregex.py`:

- `FAILURE_ID_GROPS = ("fid", "ip4", "ip6", "dns")`; `FAILURE_ID_PRESENTS =
  FAILURE_ID_GROPS + ("mlfid",)`. Filter construction raises
  "No failure-id group in '<regex>'" unless the failregex itself OR its
  prefRegex compiles with one of those named groups.
- `<HOST>` DOES expand to named groups ip4/ip6/dns — verified:
  `FailRegex(r'^...<HOST> ...$')._regexObj.groupindex` → `['ip4','ip6','dns']`
  and direct construction succeeds. So a raw `<HOST>` failregex is fine when
  the construction path passes prefRegex or when the CLI actually loads the
  file. The CLI failures seen were include-resolution artifacts (below).
- The SHIPPED filters satisfy the check via prefregex:
  `prefregex = ^<F-MLFID>%(__prefix_line)s</F-MLFID><F-CONTENT>.+</F-CONTENT>$`
  — the F-MLFID wrapper compiles an `mlfid` named group (acceptable in a
  prefRegex). Copy this shape for any custom filter; it also gives you the
  prefregex/failregex split for free.

## F- tag syntax (Regex._resolveHostTag)

- `<F-NAME>...</F-NAME>` → `(?P<name>...)`; self-closing `<F-NAME/>` inlines
  the mapping; names are lowercased via `mapTag2Opt`.
- Standard tags: `<HOST>` (= `<ADDR>|<DNS>` alternation carrying ip4/ip6/dns
  groups), `<ADDR>`, `<IP4>`, `<IP6>`, `<DNS>`, `<CIDR>`, `<SUBNET>`,
  `<SKIPLINES>`; custom stored tags: `<F-USER>`, `<F-MLFGAINED>`,
  `<F-MLFFORGET>`, `<F-NOFAIL>`, `<F-ID>` (= `(?P<fid>\S+)`, used only where
  there is no host), `<F-ALT_USER>`.

## prefregex / failregex split

With a `prefregex`, the prefix (including a systemd/journald-built prefix) is
consumed by the prefregex; the failregex is matched against the remaining
`<F-CONTENT>`. Stock sshd.conf structure (1.1.0):

```
[INCLUDES]
before = common.conf          # defines __prefix_line, __pam_auth etc.

[Definition]
__pref = (?:(?:error|fatal): (?:PAM: )?)?
prefregex = ^<F-MLFID>%(__prefix_line)s</F-MLFID>%(__pref)s<F-CONTENT>.+</F-CONTENT>$
cmnfailre = ^... patterns ... (mode-aware)
failregex = <cmnfailre-<mode>-...> etc.
```

Our working minimal custom filter (matches "Connection closed by
[authenticating user X | invalid user X | ] <IP> port N [preauth]"):

```
[INCLUDES]
before = common.conf

[Definition]
prefregex = ^<F-MLFID>%(__prefix_line)s</F-MLFID><F-CONTENT>.+</F-CONTENT>$
failregex = ^Connection closed by (?:authenticating user \S+ |invalid user \S+ )?<HOST> port \d+ \[preauth\]$
```

Behavior verified with fail2ban-regex: 4/4 attack lines matched; legit
"Connection closed by user X <IP> port N" (post-auth, no `[preauth]`) and
"Accepted publickey ..." correctly NOT matched.

## systemd backend line format (filtersystemd.py)

`backend = systemd` (NixOS module DEFAULT) builds each line as:

```
<HOSTNAME> <SYSLOG_IDENTIFIER-or-_COMM>[<SYSLOG_PID-or-_PID>]: <MESSAGE>
```

e.g. `nixos-desktop sshd-session[2198678]: Connection closed by
authenticating user root 92.118.39.77 port 60780 [preauth]`. `__prefix_line`
(from common.conf) consumes the leading `host ident[pid]: ` part. Scope with
per-jail `journalmatch = "_SYSTEMD_UNIT=sshd.service"` — on this NixOS host
ALL OpenSSH lines (including per-session ones that print ident
`sshd-session`) log under `_SYSTEMD_UNIT=sshd.service`; verify with
`journalctl -o verbose`. journalmatch supports `"unitA + unitB"` unions.

## NixOS module internals (fail2ban.nix, nixpkgs 26.11)

- `services.fail2ban.jails.<name>.filter`: `nullOr (either str configFormat.type)`
  — a STRING is (brokenly) ignored: `mkJailConfig` sets
  `filter = if (builtins.isString lib.filter) then lib.filter else name`
  and `lib.filter` is ALWAYS a function → filter = jail name. An attrset
  (INI `configFormat.type`) is rendered by `mkFilter` to
  `filter.d/<jail-name>.conf` and IS used. So: inline attrset + name your
  jail what you want the filter called.
- `jails.<name>.enabled` defaults true.
- DEFAULT jail: `backend = systemd`, `banaction = nftables-multiport` iff
  `networking.nftables.enable`, `banaction_allports = nftables-allports`,
  `ignoreip = 127.0.0.1/8 ::1`, plus `maxretry 3` / `bantime 10m` from the
  top-level options.
- `services.openssh.settings.LogLevel = "VERBOSE"` set with mkDefault when
  fail2ban enabled (needed for the failed-attempt lines to appear).
- Per-jail `settings` is freeform `pkgs.formats.keyValue` → jail.local INI.

## Validation path (no activation)

```bash
OUT=$(nix build .#nixosConfigurations.<host>.config.system.build.toplevel --no-link --print-out-paths)
"$OUT/sw/bin/fail2ban-server" -c "$OUT/etc/fail2ban" -t      # parses all jails+filters, real failure-id check
"$OUT/sw/bin/fail2ban-regex" log.txt "$OUT/etc/fail2ban/filter.d/sshd-scan.conf"
```

Only run fail2ban-regex against the BUILT generated filter file: a filter
file outside the package's resolvable filter dirs (e.g. /tmp) makes the CLI
silently fall back to treating the PATH as a literal regex
("Use failregex line : <path>") and then report a spurious
"No failure-id group". Includes resolve relative to the filter file's dir /
package dir, not the caller's cwd.

## nftables context (validated 2026-08)

- `networking.firewall.extraInputRules` is appended at the END of the
  generated `input-allow` chain, after allowed-port accepts → source-IP
  drops for allowed ports are dead rules.
- Working durable block: own table, `type filter hook input priority -1;
  policy accept;` + drop. Cross-chain semantics: at the same hook, drops
  from any base chain win over accepts from others.
- The generated ruleset lives at `<system>/etc/systemd/system/nftables.service`
  ExecStart → `/nix/store/<hash>-nftables-rules`; syntax-check with
  `run0 nft -c -f <that-file>`. Attention: `nixos-rebuild build` has no
  `--print-out-paths`; `nix build .#...toplevel` does.