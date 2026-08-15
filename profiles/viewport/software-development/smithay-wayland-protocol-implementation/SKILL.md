---
name: smithay-wayland-protocol-implementation
description: Implement a Wayland protocol global in a Smithay compositor.
version: 1.0.0
author: hermes
license: MIT
metadata:
  hermes:
    tags: [wayland, compositor, smithay, viewport, protocol]
    related_skills: [wayland-compositor-integration-tests, wayland-xwayland-input-debugging]
---

# Implementing a Wayland protocol in a Smithay compositor (Viewport)

## When to Use
- Adding a Wayland protocol global so a client sees it on the wire (Firefox/Chromium tab
  tearing, OBS capture, portal/multi-pointer seats, KDE-style decorated clients, etc.).
- The compositor must expose a global that Smithay does not provide, or that needs the repo's
  own per-object state / delegation.
- Extending existing hand-written protocols (workspace, output-management, foreign-toplevel).

This is the SERVER-side counterpart to `wayland-compositor-integration-tests`. The integration
skill covers writing over-the-wire probe clients; this one covers making the global exist and
dispatching its requests faithfully. When adding a protocol here, consider adding integration
coverage there.

## RULE #1 — CHECK SMITHAY'S OWN SOURCE FIRST (verified, saves real work)
Before hand-writing anything, grep the smithay source for the protocol name:
```
SM=/home/codebam/.cargo/git/checkouts/smithay-afa91a524fec7e0b/b6e5bf0/src
grep -rln "<name>" $SM/wayland/
```
Smithay already ships many protocols that look like they'd need hand-writing:
- **kde-server-decoration** → `smithay::wayland::shell::kde::decoration::KdeDecorationState`
  (with `KdeDecorationHandler`, `new::<D>(&dh, DefaultMode)`, `new_with_filter`). NOT hand-written.
- **xdg-decoration** → `smithay::wayland::shell::xdg::decoration::XdgDecorationState` (already
  used in the repo).
- Anything under `smithay::wayland::*` — compositor, shell, seat, selection, dmabuf, etc. is
  built in; you only add smithay-provided protocols by instantiating the state in
  `ViewportState::new` and dropping it into the struct (so the global outlives display init).

When smithay provides it: wire it like the existing `XdgDecorationState` —
1. add a `pub <name>_state: <Type>` field to `ViewportState` (held alive; mark `#[allow(dead_code)]` with a "kept alive" comment like `state.rs:670`),
2. construct it in `state.rs::ViewportState::new` (around lines 918-919 for the xdg-decoration precedent),
3. `impl <Handler> for ViewportState` in a handlers file exposing `fn <name>_state(&self)`.

## RULE #2 — WHAT SMITHAY DOES NOT IMPLEMENT (hand-write these)
Confirmed gaps this repo hand-writes: ext-workspace-v1, wlr-output-management-v1,
wlr-foreign-toplevel-management-v1 (see `crates/viewport/src/{workspace,output_management,foreign_toplevel}.rs`).
The pattern (study these three before writing a new one):

1. **`*State` struct with `new::<Self>(&dh)`** that calls
   `dh.create_global::<D, Iface, _>(VERSION, data)` (`const VERSION: u32` matches the protocol
   interface version). Returns `Self`.
2. **Dispatch impls, two house styles**:
   - NEW style (workspace.rs): dispatch on a per-object *data type* via `GlobalDispatch2`/`Dispatch2`
     (`smithay::wayland::{GlobalDispatch2, Dispatch2}`), taking `&mut D`, `DisplayHandle`, `New<_>`,
     `DataInit`. `data_init.init(resource, Data)`.
   - OLD style (output_management.rs, foreign_toplevel.rs): dispatch on the `*State` itself via
     `Dispatch`/`GlobalDispatch` (`wayland_server::{Dispatch, GlobalDispatch, DataInit, New, Resource}`).
   Match whichever the neighboring protocols use.
3. **Per-object data**: a small `Data`/`HandleData`/`HeadData` struct attached via user data,
   holding what the request maps back to (view id, output name, etc.)
4. **`#[macro_export] macro_rules! delegate_<name>`**: wraps
   `wayland_server::delegate_global_dispatch!` + `delegate_dispatch!` for each object type,
   forwarding to your `*State`. Invoke it in `crates/viewport/src/handlers/mod.rs` next to the
   other `delegate_*!(ViewportState);` lines (~787-793).
5. **Expose state**: a handler trait (`trait <Name>Handler { fn <name>_state(&mut self) -> &mut <Name>State; fn <action>(&mut self, ...) }`), implemented for `ViewportState` in `handlers/mod.rs`.
6. **Add `mod <name>;`** to `crates/viewport/src/main.rs` (alphabetical block, ~lines 9-53) and
   register `let <name>_state = crate::<name>::<Name>State::new::<Self>(&dh);` in `state.rs::new`
   (~lines 740-760 region), plus the struct field.

**Per-object data is IMMUTABLE in `request`; mutate via `Mutex` (not `Cell`/`RefCell`).**
`Dispatch::request(state, client, resource, request, data: &UserData, ...)` hands you `&UserData` —
an *immutable* reference, and wayland-server explicitly says to use interior mutability to change
it. dispatch data is also `Send + Sync`, which rules out `RefCell`/`Cell` (RefCell is not Sync).
Use `std::sync::Mutex<...>` in the data struct (`attached: Mutex<Option<XdgToplevel>>` in
`toplevel_drag.rs` is the precedent); the dispatch is single-threaded so the lock never contends.
You cannot call `resource.data_mut::<D>()` in `request` (no such method in wayland-server 0.31) —
read/write through the `&UserData` you are given.

**Request enum variant field names come from the XML `<arg name=...>`, not your guess.** e.g.
`ext_transient_seat_manager_v1::Request::Create { seat }` (XML arg is `seat`), NOT `{ id }`; the
`attach` request is `Attach { toplevel, x_offset, y_offset }`. Read the XML (`RULE #3`) for exact
field names before writing the `match`.
**Raise protocol errors on the object's own error enum via `post_error(Error::Variant, "...")`**
(needs `Resource` trait in scope) — e.g. `xdg_toplevel_drag_v1::Error::InvalidSource/ToplevelAttached/OngoingDrag`.

## RULE #3 — BINDINGS COME FROM SMITHAY REEXPORTS; verify the path exists
- staging protocols: `smithay::reexports::wayland_protocols::<ext|xdg>::<proto>::v1::server::...`
  (e.g. `ext::workspace`, `ext::transient_seat`, `xdg::toplevel_drag`).
- wlr protocols: `smithay::reexports::wayland_protocols_wlr::<proto>::v1::server::...`
  (e.g. `output_management`, `export_dmabuf`, `foreign_toplevel`).
- kde/misc: `smithay::reexports::wayland_protocols_misc::server_decoration::server::...`.
- Registry XML (source of truth for wire definition/enums):
  `/home/codebam/.cargo/registry/src/index.crates.io-*/(wayland-protocols-0.32.13|wayland-protocols-wlr-0.3.12|wayland-protocols-misc-0.3.12)`.
  Read the XML before writing dispatch — it defines exact request/event args, enums, and
  versioning. smithay reexports these crates (`reexports.rs` lines 23-27), so no `protocols/`
  vendoring is needed for staging/wlr/misc unless you're compiling a hand C client (then see the
  integration-test skill).

## RULE #4 — REQUESTS YOU CAN'T FULFILL MUST STILL RESOLVE (honest no-op)
- No `unimplemented!()`, no panics. Accept the request and do nothing with a comment explaining
  why the compositor genuinely has nothing to offer — match `foreign_toplevel.rs`'s SetMaximized/
  SetMinimized handling ("Accepted and not acted on. This compositor has no notion of...").
- Object lifecycle / versioning / enums must be spec-correct even when behavior is a no-op.
- Protocol-specified failure paths are the correct "no capability" answers, e.g.:
  - `zwlr_export_dmabuf_manager_v1.capture_output` when there's no dmabuf capture → create the
    frame object and immediately send `cancel(cancel_reason::Permanent)`.
  - `ext_transient_seat_manager_v1.create` if you can't mint a real seat → send the `denied` event
    rather than inventing a fake seat.

## Verification
- System `cargo` is on PATH but has NO matching `rustc` (flake warns at flake.nix:658-659) — you
  MUST build inside the repo's rust devshell: `nix develop .#rust -c cargo check -p viewport`
  and `nix develop .#rust -c cargo test -p viewport`. (Use the `.#rust` devshell, not the default
  `nix develop`; the user's stated way to run Rust here.)
- `cargo check -p viewport` (must pass, no new warnings you introduced).
- `cargo test -p viewport` (must not regress).
- Process worktree-git: first command in any terminal inside the worktree is
  `export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0='*'` (repo owned
  by `hermes`, you run as `codebam` in the `hermes` group; writes work, git needs the override).
- Commit to the branch; do NOT push/merge into main.
- **Check your cwd**: tools like `patch`, `write_file`, and `terminal` work relative to the
  session's cwd, not the worktree you intend to edit. After creating a worktree with
  `git worktree add .worktrees/<name> -b feat/<name>`, `cd` into it explicitly before editing.
  After the edit, verify with `git diff main --stat` from inside the worktree — if it reports no
  changes but you know you edited files, your edits went to the main worktree instead.

## Support files
- `references/session-one-four-protocols.md` — deep research from the first session: exact
  interface/enum/request inventory for xdg-toplevel-drag-v1, ext-transient-seat-v1,
  wlr-export-dmabuf-v1, and kde-server-decoration, with the smithay `KdeDecorationState` wiring,
  the `decorations` config-key precedent, and file:line anchors.
