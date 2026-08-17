# Release cutting workflow — 0.1.7 session notes

Second run of the release pipeline (0.1.6 was the first). Confirmed the
0.1.6 mechanics end-to-end and pinned down the concrete command surface that
the 0.1.6 notes only described in prose.

## Delegating the release cut to Claude Code (print mode)

Write the brief to a file first, then run in print mode with JSON output:

```bash
claude -p "$(cat /tmp/release-brief-017.md)" \
  --allowedTools 'Read,Edit,Write,Bash,Bash(git *)' \
  --max-turns 45 --dangerously-skip-permissions \
  --output-format json 2>/tmp/claude-stderr.log > /tmp/claude-017.json
```

0.1.7 run: 14 turns, ~$0.73, subtype success. The brief must state:

- "Do NOT build or upload AUR packages or GitHub release assets — that
  happens afterwards, separately." The delegation ends at: tag pushed +
  GitHub release created (0 assets).
- The Cargo.lock step EXPLICITLY: "run `nix run nixpkgs#cargo -- fetch` to
  regenerate Cargo.lock so it matches Cargo.toml". The 0.1.6 failure was an
  ambiguous brief that let Claude skip the lockfile.
- "Leave -bin sha256sums_x86_64 as-is" — they are updated in a follow-up
  commit after the artifacts are built and uploaded.
- The reference commit to copy: "model on `git show cfaa03a`" (the previous
  release commit).

Verify independently afterwards — never trust the self-report. Checked:
`git log -1`, `git describe --tags`, `git ls-remote --tags origin`,
`gh release view --json assets`, `bash -n` on all nine PKGBUILDs, grep of
the bump surface for leftovers.

## The version-bump surface (27 files in the release commit)

0.1.6 → 0.1.7 was touched in:

- Cargo.toml (workspace) + crates/viewport-shell-cef/Cargo.toml +
  crates/viewport-shell-servo/Cargo.toml
- Cargo.lock (all workspace crates)
- docs/viewport.1 (.TH line)
- package.json + package-lock.json
- flake.nix (two `version = "0.1.7";` occurrences)
- 3 source PKGBUILDs (pkgver=, _tag=v0.1.7, provides=) + .SRCINFOs
- 3 -bin PKGBUILDs (pkgver=, provides=, source_x86_64= URL; sha256sums
  deliberately stale) + .SRCINFOs
- 3 -git PKGBUILDs (pkgver=, provides=) + .SRCINFOs

-git pkgver form: `git describe --long --tags --abbrev=7 | sed 's/^v//;s/\([^-]*-g\)/r\1/;s/-/./g'`
→ `0.1.6.r3.g4f93524`. Counts from the PREVIOUS tag by design (see the
SKILL.md pitfall "The -git pkgver lags one release by design").

`packaging/aur/README.md`'s `0.1.5.r1.gf5fe7d2` is a format example, not the
tree version — leave it (both release commits did).

## Two-commit release pattern

1. `release: 0.1.7` — all bumps + regenerated Cargo.lock + CHANGELOG (move
   [Unreleased] content into `## [0.1.7] - <date>`, fresh empty Unreleased,
   update compare links) + tag + `gh release create` (0 assets).
2. `release: 0.1.7 — update -bin checksums` — after builds + upload; 6 files
   (3 PKGBUILDs + 3 .SRCINFOs), one sha256sum each.

## Build + upload (done in the Hermes session, not delegated)

- Three parallel `./packaging/build-in-container.sh {wpe,webkitgtk,chromium}`
  runs are safe — each writes to its own out/ subdir. ~3-7 min each.
- The Cargo.lock fix held: no `--locked` failure in any of the three builds.
- Upload: `gh release upload v0.1.7 <3 artifacts> --clobber`, verify with
  `gh release view v0.1.7 --json assets -q '.assets[] | .name'`.
- `sha256sum` the three non-debug artifacts → patch the 6 -bin files.

## AUR push

Re-runnable as `scripts/push-aur-packages.sh <version> <repo-dir>` (clones
to a temp dir, copies PKGBUILD + .SRCINFO, commits with an explicit
user.name/email because AUR clones carry no git identity, handles
registered-but-never-pushed repos, pushes master, prints pkgver per repo).

Verification: fresh `git clone` of a few repos back and grep pkgver — that
is ground truth. The AUR RPC API lags minutes after a push; never conclude
failure from it (see 0.1.6 notes).

## Time budget

Whole pipeline (delegation + 3 builds + upload + checksums + 9 AUR pushes +
verification): under an hour.
