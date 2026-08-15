# Release cutting workflow — 0.1.6 session notes

Session: cut release 0.1.6 of Viewport, a Wayland compositor with nine AUR
packages (three engines x three forms). The release was delegated to Claude
Code for the version bump + changelog + git tag + GitHub release, then the
AUR artifacts were built, uploaded, and pushed from the Hermes session.

## The Cargo.lock gotcha (the #1 lesson)

The release commit bumped `version = "0.1.5"` to `"0.1.6"` in the workspace
`Cargo.toml` but left `Cargo.lock` unchanged (still recording 0.1.5 for all
seven workspace crates). The PKGBUILD's `prepare()` step runs
`cargo fetch --locked --target "$(rustc -vV | sed -n 's/host: //p')"`, and
`--locked` rejects a lockfile that doesn't match `Cargo.toml`:

```
error: cannot update the lock file /pkg/src/viewport/Cargo.lock because --locked was passed to prevent this
help: to generate the lock file without accessing the network, remove the --locked flag and use --offline instead.
==> ERROR: A failure occurred in prepare().
```

All three parallel builds failed at this step. The fix: run `cargo fetch`
on the host to regenerate `Cargo.lock`, `git add Cargo.lock`, amend the
release commit, move the tag (`git tag -d v0.1.6 && git tag -a v0.1.6`),
and force-push both the branch and the tag. Then restart the builds.

On NixOS, `cargo` is not on PATH — run it via `nix run nixpkgs#cargo -- fetch`.

## Build in containers: the mechanics

- `packaging/build-in-container.sh <package>` uses podman (or docker) with
  a cached `localhost/viewport-builder` image based on `archlinux:latest`.
- The image has `makepkg` patched to run as root (sed on `/usr/bin/makepkg`
  replacing `(( EUID == 0 ))` with `(( 0 ))`), because rootless podman has
  one UID and no /etc/subuid range for an unprivileged build user.
- Dependencies are installed inside the container with `pacman -Syu --needed`
  (not `makepkg --syncdeps`) to avoid sudo/audit issues and to skip
  unavailable packages rather than failing.
- `makepkg --nodeps --noconfirm --clean` builds the package.
- Output: `packaging/out/<package>/*.pkg.tar.zst` (both the main package and
  a `-debug` package; only upload the non-debug one).

## Upload to GitHub release

```
gh release upload v0.1.6 <artifact> --clobber
```

Verify with `gh release view v0.1.6 --json assets`.

## Update -bin checksums

After building, compute sha256sums and update both `PKGBUILD` and `.SRCINFO`:

```
sha256sum packaging/out/viewport-wpe/viewport-wpe-0.1.6-1-x86_64.pkg.tar.zst
# → 4cd5d46c6b22bd1999b41298ce493812e6b24eb7444cb881fc0afb5e3fcc3d97
```

Update the `sha256sums_x86_64=('<hash>')` line in the -bin PKGBUILD and the
`sha256sums_x86_64 = <hash>` line in the .SRCINFO. Commit as a follow-up.

## Push to AUR: the mechanics

Each AUR package is its own git repo at `ssh://aur@aur.archlinux.org/<name>.git`.
The push is: clone, copy PKGBUILD + .SRCINFO in, commit, push.

### Empty repos (first push)

Repos registered on the AUR but never pushed to clone as empty repos.
`git commit` on an empty repo creates a commit on an unborn branch — `HEAD`
points nowhere. `git push origin master` fails:
```
error: src refspec master does not match any
```

Fix: `git checkout -b master` BEFORE `git add` so the commit lands on a
named branch. Then `git push origin master` works.

### Existing repos (subsequent pushes)

Just clone, copy, commit, push — the branch already exists.

### AUR SSH access

`ssh aur@aur.archlinux.org` works if the SSH key is registered. Test with
`ssh aur@aur.archlinux.org list-repos` to see which package repos exist.
`ssh -o BatchMode=yes aur@aur.archlinux.org help` for available commands.

### AUR indexing delay

The AUR RPC API (`https://aur.archlinux.org/rpc/v5/info?arg[]=<name>`)
takes a few minutes to reflect newly-pushed or updated packages. Do not
poll the API immediately after push and conclude the push failed — clone
the repo back and check `pkgver` in the PKGBUILD instead.

## Delegating to Claude Code: the verification lesson

The version bump + changelog + tag + GitHub release was delegated to Claude
Code via print mode (`claude -p '...' --max-turns 40 --dangerously-skip-permissions`).
Claude Code reported success, and the git tag, push, and GitHub release were
all verified as correct. However, it did NOT update `Cargo.lock` — the
explicit instruction said "Do not touch Cargo.lock (cargo will handle it)".
This was a mistake in the delegation brief: `cargo fetch --locked` in the
PKGBUILD's `prepare()` step needs the lockfile to match `Cargo.toml` at the
tagged commit, and `cargo` only updates the lockfile when run on the same
machine, not inside the container during `makepkg`.

Lesson for future delegations: when the task involves a version bump that
will be built with `--locked`, include "run `cargo fetch` and commit the
updated `Cargo.lock`" as an explicit step in the delegation brief.
