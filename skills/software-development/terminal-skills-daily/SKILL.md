---
name: terminal-skills-daily
description: "Daily terminal-skill lesson: one verified topic per day."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [teaching, terminal, shell, readline, grep, awk, curriculum, cron]
---

# Daily terminal-skills lesson

Teaches Sean one terminal skill per day (readline/line-editing, grep/ripgrep, awk, sed,
coreutils, jq, find/xargs, processes, pipelines, shell quoting…). Driven by the Hermes cron
job **`daily terminal skills lesson`** (8:00 AM) with `terminal-lesson-context.sh` as its
pre-run script.

## When to Use

Use when:
- The cron job `daily terminal skills lesson` fires (its prompt injects this skill + the
  context script's output) — this is the normal path.
- Sean asks for a terminal lesson, says "teach me X", or asks to extend/reorder the
  curriculum, reset progress, or add a topic (then edit `curriculum.md`, don't hardcode).
- A lesson must be re-sent because the previous one repeated, hallucinated a flag, or taught
  a tool that isn't installed — fix the cause, then patch this skill or the curriculum.

Not for: one-off "how do I do X in the shell" questions — answer those directly; only fold a
topic into the curriculum when it deserves a slot.

## Files and state

| Path | Role |
|---|---|
| `~/.hermes/lessons/curriculum.md` | Topic list: `id \| area \| title \| what-you-learn`. User-editable; order = teaching order. |
| `~/.hermes/lessons/progress.tsv` | Append-only log: `date<TAB>topic-id<TAB>title`. Drives dedupe + revisit scheduling. |
| `~/.hermes/scripts/terminal-lesson-context.sh` | Emits progress + next topics + real tool inventory. Its stdout arrives in the prompt. |

## Workflow

1. Read the injected context: lesson number, whether a revisit is due, the next uncovered
   topics, and the environment inventory.
2. Pick **exactly one** topic: the next uncovered one in curriculum order, unless the context
   says a spaced-repetition revisit is due (`lesson #n % 5 == 0`) — then take an old topic from
   the revisit pool and teach a harder variant.
3. **Verify every command on this machine before writing the lesson** (see rules below).
4. Write the lesson in the format below.
5. Append the topic to `progress.tsv` (the context block prints the exact command). Without
   this append the same topic repeats tomorrow.

## Lesson format (~1200-1800 chars, Telegram markdown)

```
**Day N · <topic title>**  (<area>)
*Mental model:* one sentence — what this actually does.

What it does / how it works: 2-4 lines. No history, no "as an AI".

`$ command with real args`
`real observed output`            <- verified on this machine, trimmed for length

**Why you'll use it:** 1-2 lines tied to Sean's real work (dsh session logs, ~/Documents/git
repos, /persistent/etc/nixos, nix tooling) — not a generic textbook example.

**Try it now:** one concrete exercise he can run in the next 60 seconds, ideally on his own files.

*Next:* one-line teaser of the following day's area.
```

Keep it skimmable: one concept, not a survey. If a topic needs more, teach the core and save
the depth for a revisit slot.

## Hard rules

- **Never ship an unverified command.** Run it (`fish -c '...'`, `bash -c '...'`, `nu -c '...'`)
  and paste the real output. Never recall a flag from memory — check `--help` or the run.
- **Teach for NUSHELL — that is the shell he uses.** `nu` 0.115 is his login shell and his working
  shell; reedline, `edit_mode: emacs`. His `config.nu` sources **atuin** (Ctrl-R and up-arrow
  history search), **fzf** (Alt-C dirs, Ctrl-T files), **carapace** (completions) and **zoxide**.
  bash 5.3 is for scripts; **fish is installed but his `config.fish` is legacy** — never teach fish
  as his shell, and never infer his shell from `$SHELL` (which points at fish here and is stale).
- **Verify nu bindings from nu itself.** `nu -c 'keybindings default | to json'` is ground truth
  for the configured edit mode (228 rows, shape `{mode, modifier, code, event}`); it also proves
  whether the mode is emacs or vi. `keybindings list` is *not* the binding map — it lists the
  available keycodes/modifiers/events. `keybindings listen` is the interactive confirmation path
  and the only way to settle precedence when two sources (atuin and fzf both define `ctrl_r`)
  claim the same key.
- **Readline tips are bash-only.** `Ctrl-A`/`Ctrl-E` exist in nu too, but nu's names are reedline's
  (`MoveToLineStart`, `MoveToLineEnd`, `CutFromStart`, `KillLine`, `PasteCutBufferBefore`,
  `SwapGraphemes`, `OpenEditor`) — cite those, and label anything bash-specific as bash-only.
- **You CAN test interactive editing behaviour — drive a pty.** Don't settle for the binding table.
  This works (verified in both fish and nu):
  ```bash
  TMPHOME=$(mktemp -d /tmp/nuhome.XXXX)     # throwaway HOME: clean defaults, zero history pollution
  tmux new-session -d -s vt -x 100 -y 40 "env HOME=$TMPHOME XDG_CONFIG_HOME=$TMPHOME/.config nu"
  sleep 4
  tmux send-keys -t vt -l -- 'echo zq1 zq2'   # literal text: ALWAYS use -l AND -- (see pitfalls)
  tmux send-keys -t vt C-a                    # C-a, C-e, C-w, C-y, C-u, C-t, M-b, M-d, M-f
  tmux send-keys -t vt -l -- 'echo '; tmux send-keys -t vt Enter
  sleep 1; tmux capture-pane -t vt -p -S -400 | grep zq   # evidence from the scrollback
  tmux kill-session -t vt && rm -rf "$TMPHOME"
  ```
  Use unique marker tokens (`zq1`, `zq2`) so history hints can't contaminate a case, read the
  **scrollback** (`-S -400`) rather than the last few lines, and `sleep` between keys.
  `keybindings listen` remains the only way to see what his real terminal sends (the emulator can
  intercept keys first), so hand him that to confirm and say which claims came from a pty test.
- **Only teach tools that exist.** The context block lists installed vs missing (`sd`, `yq`,
  `delta`, `parallel`, `hyperfine`, `shellcheck`, `xxd`, `sponge`, `sqlite3` are missing here).
  For a genuinely missing tool, teach `nix shell nixpkgs#<pkg> -c <cmd>` — his AGENTS.md forbids
  `nix profile install` / `nix-env -i`.
- **No repeats.** Don't re-teach anything in `progress.tsv`, and avoid the same area two days
  running (the context lists the last five).
- Deliver the lesson only — no preamble about being a cron job, no questions. Cron runs unattended.

## Pitfalls found while building this

- **Never drive a pty against his real HOME.** The first pty experiments ran `tmux … nu` with his
  real config, which wrote 5 junk commands into `~/.config/nushell/history.txt` *and* into atuin's
  `~/.local/share/atuin/history.db`. Use a throwaway HOME as above. If you do pollute it, clean it
  exactly and say so: filter the junk lines out of `history.txt` (keep a `.bak`), and delete the
  atuin rows with `nu -c 'open <db> | query db "delete from history where command like …"'` —
  note atuin's CLI has no delete-by-command (only `prune`/`dedup`), and `.complete` only works on
  external commands, so a pipe ending in `| complete` errors *after* the delete has already run.
- **tmux literal text starting with `-` is parsed as a flag.** `tmux send-keys -t s -l '-END'`
  fails with `unknown flag -E` and silently drops the whole string, making a case look like the
  binding did nothing. Always `-l --`.
- **History hints silently corrupt key tests.** In nu, `Ctrl-E`/`Alt-F` are
  `UntilFound([HistoryHintComplete…, MoveToLineEnd])` — typing a prefix that matches an earlier
  command makes `Ctrl-E` *accept the hint* instead of moving the cursor, so the line gains tokens
  you never typed. Symptom: duplicated text like `echo CCC DDD-END-END`. Use unique tokens.
- **Check what his integrations shadow.** Two of nu's 228 defaults are overridden in his setup:
  `Ctrl-R` (reedline `SearchHistory` → atuin) and `Ctrl-T` (reedline `SwapGraphemes` → **fzf file
  picker**), plus `Alt-C` (→ fzf dirs). Observed directly: Ctrl-R paints atuin's TUI with a
  `[ GLOBAL ]` filter, Ctrl-T paints fzf's list with its `▌` pointer. Never teach a default without
  checking whether his config shadows it.
- **Do not infer his shell from `$SHELL` or from config files.** The first build of this job
  concluded "interactive = fish" because `$SHELL=/run/current-system/sw/bin/fish` and
  `~/.config/fish/config.fish` exists with atuin/fzf/starship wired up. Both are stale: he uses
  **nushell**, and fish is leftover. Use `getent passwd <user> | cut -d: -f7` for the login shell
  and, when in doubt, ask. A lesson built on the wrong shell is worse than no lesson.
- Cron runs scripts with the gateway's nix-store-only PATH (no jq/awk/find/zstd). Both
  `terminal-lesson-context.sh` and `dsh-task-scan.sh` bootstrap `/run/current-system/sw/bin`,
  `/run/wrappers/bin`, `~/.nix-profile/bin`, `~/.local/state/nix/profile/bin`, and
  `/etc/profiles/per-user/$USER/bin` — keep that block in any new collector script.
- `awk 'NR==FNR{...} !($1 in a)'` misbehaves when the **first** file is empty: FNR resets per
  file but NR doesn't, so every line of the second file satisfies `NR==FNR`. Guard with
  `[ -s file ]` or use `FILENAME==ARGV[1]` plus an explicit empty check.
- gawk's `strftime` honours the system timezone; jq's `strftime` renders **UTC**. For local
  timestamps, emit epoch seconds from jq and format in awk/`date`.

## Verify an edit

```bash
bash -n ~/.hermes/scripts/terminal-lesson-context.sh
LESSONS_DIR=/tmp/ltest bash ~/.hermes/scripts/terminal-lesson-context.sh | head -20   # copied curriculum + fake progress
env -i PATH=<gateway PATH from /proc/<pid>/environ> HOME=$HOME USER=$USER bash ~/.hermes/scripts/terminal-lesson-context.sh
```
