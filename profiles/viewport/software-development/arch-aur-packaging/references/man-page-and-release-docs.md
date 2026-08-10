# Man page from real CLI flags + Keep-a-Changelog — worked notes

Session context: filling "shipping gaps" for a GPL-3.0 Wayland compositor
(Viewport, `crates/viewport`). Deliverables were an AUR source PKGBUILD, a
`wpe` `-bin` PKGBUILD, `CHANGELOG.md`, `CONTRIBUTING.md`, and a `viewport(1)`
man page. All committed to a shipping worktree; not pushed/merged.

## The core lesson: derive man-page flags from the real parser, not prose docs

The repo's `docs/configuration.md` listed flags like `-f/--fallback`,
`-t/--timeout`, `-T/--terminal`, `-M/--menu`, `-b/--bind`, `-e/--startup`,
`-d/--debug` — those were the **old C compositor's** flags. The **Rust**
binary (`crates/viewport/src/main.rs`) has a completely different, smaller
set, held in a single `const OPTIONS: &[Opt]` table that feeds both `--help`
and unknown-option warnings.

The man page MUST document the real set. Steps:

1. Grep the Rust binary for the parser: search for `clap`/`structopt`, and in
   hand-rolled parsers look for a table like `const OPTIONS` or a `flag()`
   helper plus an `Opt { flag, value, what }` struct — that table IS the
   authoritative flag list.
   `search_files pattern='print_help|fn flag|OPTIONS|--[a-z-]+' file=main.rs`.
2. Read that table verbatim — flag name, whether it takes a value, its
   one-line description. Use those exact descriptions in the man page.
3. Also enumerate subcommands (`viewport msg`) from the same file: the msg
   subcommand's own `USAGE` block lists `-t/--type`,
   `--socket`, `--timeout`, `--pretty`, `--raw`, `-h/--help`.
4. Enumerate environment variables read by the binary (`VIEWPORT_LOG`,
   `VIEWPORT_RENDERER`, `VIEWPORT_SHELL_BACKEND`, `VIEWPORT_SOCKET`) — grep
   for `var_os` / `env::var`.
5. Cross-check the docs only AFTER the code; treat docs as possibly stale.

## Keep-a-Changelog structure that worked

- `[Unreleased]` first, with subsections matching the work areas the review
  called out: **Protocols / Tests / Shipping / Docs**. Bullets are concrete
  ("Add a source package recipe under packaging/aur", "Wire up the
  color-management protocol surfaces").
- Then released versions with **real** dates pulled from
  `git show -s --format=%ci <release-commit>` (the release commit, not the
  tag date you guess). Fixed a guessed 08-01 to the actual 08-05 this way.
- Footer compare/release links in `[Unreleased]`/`[0.1.3]` ref style.
- Do not invent versions or dates beyond "Unreleased".

## CONTRIBUTING.md — only cite what exists

Email scripts and commands must be verified before citing. The hook
(`.githooks/pre-commit`, enabled via `git config core.hooksPath .githooks`)
runs: shell layout tests when JS paths are staged; fmt/clippy/test when
`crates/`|`Cargo.toml`|`Cargo.lock`|`flake.nix` are staged; a both-halves
`cargo check` of the `wpe` feature. CI is disabled (`.github/workflows/ci.yml`
top comment explains why) — the hook is the real gate. Cross-check every
referenced path/script exists before writing.

## PKGBUILD authoring specifics (from this tree)

- Keep `-bin` artifact download names NOT ending in `.pkg.tar.*` so makepkg
  does not mistake the source artifact for the output.
- Mark `PLACEHOLDER_...` in checksums and a clear comment for the pending
  version bump and tarball sha, so a build fails visibly.
- Source PKGBUILD pinned to `_tag=vX.Y.Z`; `-bin` uses `source_x86_64` at the
  GitHub release URL + `sha256sums_x86_64`.
- wpe shell: `--features wpe`, links `wpewebkit`+`glib2`+`json-glib`,
  installs one binary at `/usr/bin/viewport` (no wrapper — engine is
  in-process). webkitgtk: out-of-process, two binaries, wrapper sets
  `VIEWPORT_SHELL_BACKEND`/`VIEWPORT_SHELL_URL`.

## Verification that closed the gate

- `bash -n` every new/modified PKGBUILD (all parse).
- `nix run nixpkgs#groff -- -man -Tutf8 docs/viewport.1` → exit 0, no stderr.
- Checked markdown links resolve to real paths with a tiny Python regex pass.
- The harness kept demanding `npm test`; the changed files were
  PKGBUILDs/docs (no JS under data/shell or tests/*.js), so that suite was
  irrelevant — but ran it anyway (exit 0) to close the verification gate and
  noted the irrelevance in the reply. Lesson: run the harness's canonical
  command even when it does not bear on the change, and say so.
