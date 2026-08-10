---
name: arch-aur-packaging
description: Write Arch/AUR PKGBUILDs and their release docs.
---

# Arch / AUR packaging and release docs

Authoring PKGBUILDs and the docs that ship with a release (CHANGELOG,
CONTRIBUTING, a `*.1` man page) is a recurring class of work. This skill
covers the durable conventions and the verification step.

## Ground truth first — always

Before writing any new PKGBUILD or release doc, READ the existing material:

- The existing PKGBUILD(s) in the tree are the model — match their voice,
  dependency lists, comments, and structure. Do not invent a fresh format.
- The project's README / docs explain naming and versioning (e.g. how engines
  like `webkitgtk` vs `wpe` vs `chromium` are named, and how tags are cut,
  `vX.Y.Z`).
- `git log --oneline` of the relevant branch gives the changelog material.
- Regenerate/update any README that describes the package set so it doesn't
  drift from what now lives in the tree.

## Source package vs `-bin` package

- A **source** PKGBUILD compiles the tagged tree. Pin it to a tag
  (`_tag=vX.Y.Z`) or a release tarball — never a moving branch; an
  unreproducible package is not a package.
- A **-bin** PKGBUILD unpacks the release artifact (often itself an Arch
  `.pkg.tar.zst`) instead of compiling — saved build time for the user.
  `source_x86_64` points at the GitHub release URL; the download name should
  NOT end in `.pkg.tar.*` so makepkg doesn't mistake it for the output.
- Both install a binary of the same name, so they set `provides`/`conflicts`
  so a system takes exactly one (each engine variant conflicts with the
  others and with the C binary).
- `-bin` recipes commonly set `options=('!strip' '!debug')` because the
  artifact was already stripped upstream.
- Mirror the model package's `depends`/`optdepends`/`makedepends`, adjusting
  only for what differs (e.g. the wpe variant links `wpewebkit` + `glib2` +
  `json-glib` instead of `webkitgtk-6.0` + `gtk4`; it builds `--features wpe`
  and installs one binary at `/usr/bin/viewport` with no wrapper).

## Placeholders

When a tag/artifact does not exist yet, ship a version consistent with the
project (e.g. the current release) and MARK every placeholder loudly —
`pkgver`, `_tag`, the `sha256sums`, and in the source URL. Write
`PLACEHOLDER_...` into the checksum or an explicit comment so a build fails
visibly rather than silently installing the wrong thing. Note what the
version bump is for in a comment.

## Release docs

- **CHANGELOG.md** — Keep-a-Changelog format: `[Unreleased]` section grouping
  work areas (Protocols / Tests / Shipping / Docs), then released versions with
  real dates pulled from `git show -s --format=%ci <tag>`. Do not invent
  versions or dates beyond "Unreleased".
- **CONTRIBUTING.md** — only cite commands/scripts that actually exist in the
  tree (verify before writing: `scripts/integration.sh`, the pre-commit hook,
  the CI config). Describe build/test steps, the pre-commit/CI behaviour, and
  the code conventions the tree actually uses.
- **Man page** — MUST document the REAL flags. Derive them from the argument
  parser in source (clap/structopt/Opt tables), NOT from prose docs, which can
  describe a *different* binary (e.g. the old C compositor). See
  `references/man-page-and-release-docs.md`.
  Pitfall: a naive `grep -oE '"--[a-z-]+"' main.rs` also matches flags the binary passes to
  *subprocesses* (e.g. `systemctl --user`, `dbus-update-activation-environment --systemd`) —
  those are NOT flags of the binary itself and must NOT go in the man page. Distinguish the
  binary's own argument-parser table from args forwarded in `Command::new(...).args([...])`.

## Verification

Cheap validators, run before commit:

- `bash -n <PKGBUILD>` — all PKGBUILDs parse.
- `nroff -man` / groff — render the man page: `nix run nixpkgs#groff -- -man
  -Tutf8 file.1`. Exit 0 with no stderr = clean.
- Check every markdown link / referenced command resolves to a real file.
- If the harness wants `npm test` and the changed files are docs/PKGBUILDs
  (no JS under `data/shell`/`tests/*.js`), explain that the JS suite is
  irrelevant to them, but run it anyway to close the verification gate.

## NixOS host notes

- Every shell command in a shared worktree: export
  `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0='*'`
  (repo owned by another user).
- No sudo; run tools via `nix run nixpkgs#<pkg>`.
- Do NOT touch other worktrees or `main`; commit (git add + commit) but do not
  push/merge unless asked.

See also `references/man-page-and-release-docs.md` for worked examples of the
rule-map/OPTIONS-table extraction and Keep-a-Changelog structure.
