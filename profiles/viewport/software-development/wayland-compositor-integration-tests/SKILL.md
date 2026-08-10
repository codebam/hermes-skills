---
name: wayland-compositor-integration-tests
description: Add/run Wayland integration tests (Viewport harness).
version: 1.0.0
author: hermes
license: MIT
metadata:
  hermes:
    tags: [wayland, compositor, integration-testing, viewport, smithay]
    related_skills: [wayland-xwayland-input-debugging, xwayland-input-debugging, test-driven-development]
---

# Wayland compositor integration tests (Viewport)

## When to Use
- Adding or extending an over-the-wire integration test in the Viewport compositor
  (`scripts/integration.sh`, `tests/*.test.sh`, `tests/*-client.c`).
- Covering a hand-written protocol (Smithay implements none behind it) — foreign-toplevel
  management, ext-workspace, output-management, or any future one.
- Running the `nix develop -c cargo build -p viewport` / `scripts/integration.sh` suite.

The Viewport compositor (`.worktrees/integration-tests`, branch `wt/integration-tests`)
has a parity-test suite that drives the real compositor over a real Wayland socket.
These are the tests that matter for hand-written protocol dispatch — Smithay implements
none behind them, so they carry the highest regression risk. Adding coverage for one is a
recurring class of work; this skill is the map.

## The harness (VERIFIED — read fully, lines cited)

- `scripts/integration.sh` (117 lines) is the runner. `set -euo pipefail`. Takes the
  compositor binary as `$1`. Compiles C clients with a bash `generate()` helper that runs
  `wayland-scanner client-header` + `wayland-scanner private-code`, then a `cc` loop.
  Dispatches each test with `run <name> <cmd...>` which prints `=== <name>` / pass/FAIL and
  ORs a `failed` flag (never stops at first failure).
- Two kinds of tests:
  1. **C probe clients** in `tests/*-client.c` — bind globals, speak the protocol, exit 0/2.
     Compiled by `integration.sh`; the runner passes their paths to the `.test.sh` scripts.
  2. **`.test.sh` scripts** that START their own compositor with `--headless` (e.g.
     `tests/output-order.test.sh`, `tests/lock.test.sh`), read `WAYLAND_DISPLAY` back out of
     the log, and orchestrate clients + a python control-socket driver (`platform=AF_UNIX`).
- Each `.test.sh` sets `unset WAYLAND_DISPLAY`, `export XDG_RUNTIME_DIR`, starts
  `"$VIEWPORT" --headless`, waits for the socket line in the log, spawns clients, checks
  exit codes, and cleans up the compositor by PID (never by name — the dev session is often
  another viewport).
- Protocol XML sources: staging/unstable protocols come from `pkg-config --variable=pkgdatadir
  wayland-protocols` (ext-workspace-v1, ext-foreign-toplevel-list, etc.). **wlr** protocols are NOT
  in upstream wayland-protocols — they ship in the `wayland-protocols-wlr` crate and must be
  **vendored into `protocols/`** (as `wlr-layer-shell-unstable-v1.xml` already is). See
  `references/protocol-research.md` for exact XML provenance and version matching.

## Build & run (VERIFIED)

- System `cargo`/`rustc`/`cc` exist but `wayland-scanner` and `pkg-config` do not — they come
  from the flake dev shell. Build with:
  `nix develop -c cargo build -p viewport` → `target/debug/viewport` (works, ~1.5 min cold).
  Tooling (`wayland-scanner`, `pkg-config`, `cc`) is on PATH inside `nix develop -c`.
- Run the whole suite: `nix develop -c scripts/integration.sh target/debug/viewport`.
- First command in any terminal inside the worktree:
  `export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0='*'`
  (repo owned by `hermes`, you run as `codebam` in the `hermes` group; writes work, git needs
  the safe.directory override).

## How to add coverage for a hand-written protocol

1. **Read the server-side impl** to find the *observable behavior* a client can assert on,
   not just "the request didn't crash". Look for an event the compositor sends back.
2. **Match the client XML version to the server.** Server bindings come from Smithay's
   `wayland-protocols-wlr` / `wayland-protocols` reexports (check `Cargo.lock`). The client
   header you generate must marshal the same wire opcodes. Confirm the `<interface version=`
   in the XML equals the `const VERSION` in the Rust global. Generate the header first and
   read it before writing the C (API names differ from protocol name, e.g. foreign-toplevel
   states are `_STATE_ACTIVATED=2`, `_STATE_FULLSCREEN=3`).
3. **Vendor wlr XMLs** into `protocols/` (copy from the `wayland-protocols-wlr-<ver>` cargo
   registry dir — same version the server pins, so the wire matches).
4. Write a `tests/<name>-client.c` (see `tests/paint-client.c` / `tests/lock-client.c` for
   the listener/registry style) and/or a `tests/<name>.test.sh`, then add a `run <name>`
   line to `scripts/integration.sh`. The existing 5 tests must keep passing.
5. **Verify over the real socket** and paste the `=== <name>: pass` runs.

## Pitfalls

- **ext-workspace-v1 publishes nothing until the shell reports its list.** The manager is
  created with an empty `WorkspaceState`; groups/handles only appear after the compositor
  receives `workspace.list` over the control socket (handled in `apply.rs`, calls
  `workspace_state.set::<ViewportState>`). So that test must drive the control socket first
  (like `output-order.test.sh` does), then bind the manager and expect `workspace_group` +
  `workspace` events.
- **foreign-toplevel lists only *mapped* windows.** `foreign_management_state.add` fires in
  `handlers/compositor.rs` only when the surface commits a **buffer** (`view.mapped = true`,
  line ~293). A client that just creates an xdg_toplevel without attaching a buffer never
  gets a `toplevel` handle. Attach a minimal shm buffer.
  - `activate` only acts when `view.mapped` (so it works once mapped); `close` → `send_close()`
    → the client's `xdg_toplevel.close` fires (clean observable); `set_fullscreen` forwards to
    the shell as `window.fullscreen.set` (no observable in headless — fire-and-forget).
- **output-management** (`zwlr_output_manager_v1` v4): bind → heads/modes + `done(serial)`.
  `create_configuration(serial)` → `enable_head(head)` → `set_mode(mode)` → `apply()`. Apply
  returns `succeeded()` only if `serial` is current AND every named head exists. Must reuse a
  mode the head advertised (a custom/unknown mode is refused when a real DRM udev exists).
  A config that only `enable_head`s the currently-enabled head succeeds (still_on non-empty,
  no mode change), so `apply` AND `test` variants both work headlessly.
- **libwayland rejects NULL object args at marshal, even when the XML says `allow-null="true"`.**
  `zwlr_foreign_toplevel_handle_v1_activate(handle, NULL)` dies client-side with
  `error marshalling arguments for activate (signature o): null value passed for arg 0` and
  the request is silently DROPPED — later requests in the batch still reach the wire, which
  makes the failure easy to misread (test "lists fine, close never answers"). Fix: bind a real
  `wl_seat` (and a real `wl_output` for `set_fullscreen`) in `handle_global` and pass it; the
  server-side impl ignores the object anyway (single-seat compositor).
- **foreign-toplevel `closed` requires the window's client to actually go away.** `close()` →
  `send_close()` only sets the window client's `xdg_toplevel.close`. The `closed` event on the
  manager handle fires only when the compositor runs `toplevel_destroyed()`
  (xdg_shell.rs:~117-140 → `foreign_management_state.remove(id)`), i.e. on surface destroy or
  client disconnect. A single client cannot both request close and observe its own `closed` —
  use a cooperating window client (paint-client exits on close) and let the manager client wait
  for the event with a deadline.
- **A client-side `set_fullscreen` never echoes a `state` event — do not assert the FULLSCREEN
  toggle.** The shell's `window.fullscreen.set` handler (data/shell/commands.js) deliberately
  does not echo fullscreen back when the request came from a client ("without echoing the state
  back and starting a loop"); it only records `fullscreens` and relayouts. A test asserting the
  handle's `state` event toggles FULLSCREEN after `set_fullscreen` fails deterministically.
  Assert the request is accepted, and that `close`→`closed` works — that is the observable act.
- **New `.test.sh` files must be `chmod +x`** or integration.sh reports `Permission denied`
  (existing tests are 0755; a file written from scratch is 0644). chmod, then re-run.
- **C clients using `clock_gettime`/`CLOCK_MONOTONIC` need `#include <time.h>`** — easy to omit
  when copying the lock-client/paint-client pattern; it's a hard compile error under
  `-std=c11 -Wall -Wextra`, and the build stops at the first failing client.
- **ext-workspace round-trip proof lives on the CONTROL socket, not the Wayland socket.**
  Client `activate`+`commit` → `workspace_asked` → `notify(Event::WorkspaceRequest)` →
  broadcast as `{"type":"workspace.request","action":"activate","id":"1"}`. The output name in
  `workspace.list` must be a real one — discover it with `output.query` → `output.layout`
  (`HEADLESS-1` headless). Listen on the socket with a deadline; the compositor keeps
  publishing other events, so scan lines for the target event rather than waiting for silence.

## Support files
- `references/protocol-research.md` — deep research on the three hand-written protocols
  (foreign-toplevel, ext-workspace, output-management): server observables with file:line,
  XML provenance/versions, exact client C API names. Verified; the test files themselves are
  still TODO — see that file for the "do next" plan.
- `references/writing-over-the-wire-tests.md` — turnkey recipes for the three test types
  (client+script structure, deadline-dispatch loop, control-socket round trip) plus the exact
  failure transcripts from the first full-suite run and their fixes.
