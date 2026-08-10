# Session one: the four protocols — verified research

Second session research (2026-08) for the `wt/protocol-holes` task. All paths verified by reading
the actual smithay fork source and registry XML. Implementation itself was NOT completed in this
session — this is the research map, not a claim that the code works.

## Key verdict
**kde-server-decoration must NOT be hand-written — smithay ships it.** Wire `KdeDecorationState`
like the repo already wires `XdgDecorationState`. The other three (xdg-toplevel-drag,
ext-transient-seat, wlr-export-dmabuf) are genuinely NOT in smithay → hand-write per the umbrella
skill's RULE #2/#3/#4.

## Canonical pattern files (read these first)
- `crates/viewport/src/workspace.rs` — NEW-style dispatch: `GlobalDispatch2`/`Dispatch2` on a
  per-object data type (e.g. `ManagerData`, `HandleData`, `GroupData`), `new::<Self>(&dh)`,
  `DisplayHandle`, `New<_>`, `DataInit`, `data_init.init(resource, Data)`.
- `crates/viewport/src/output_management.rs` — OLD-style dispatch: `Dispatch`/`GlobalDispatch`
  on the `OutputManagementState` itself, per-object `HeadData`/`ModeData`/`ConfigurationData`.
- `crates/viewport/src/foreign_toplevel.rs` — OLD-style + the honest-no-op convention and a
  `delegate_foreign_toplevel!` macro.
- Registration: `crates/viewport/src/state.rs` lines ~740-760 and ~898
  (`let <x>_state = crate::<x>::<X>State::new::<Self>(&dh);`).
- Delegation: `crates/viewport/src/handlers/mod.rs` lines ~787-793 (`delegate_<x>!(ViewportState);`).
- Module list: `crates/viewport/src/main.rs` lines 9-53 (alphabetical `mod` block).
- Smithay-provided protocols go through `smithay::delegate_dispatch2!(ViewportState)` at
  `handlers/mod.rs:884` — no per-protocol macro needed for those.

## Protocol binding paths (verified to exist in the generated/reexport set)
- xdg-toplevel-drag-v1: `smithay::reexports::wayland_protocols::xdg::toplevel_drag::v1::server::...`
  (staging; source `wayland-protocols-0.32.13/src/xdg.rs:145`).
- ext-transient-seat-v1: `smithay::reexports::wayland_protocols::ext::transient_seat::v1::server::...`
  (staging; `ext.rs:63`).
- wlr-export-dmabuf-v1: `smithay::reexports::wayland_protocols_wlr::export_dmabuf::v1::server::...`
  (`wayland-protocols-wlr-0.3.12/src/lib.rs:33`).
- kde-server-decoration: `smithay::reexports::wayland_protocols_misc::server_decoration::server::...`
  (`wayland-protocols-misc-0.3.12/src/lib.rs:104`); smithay impl at `wayland/shell/kde/{decoration,handlers}.rs`.

smithay reexports: `src/reexports.rs` lines 23-27 (`pub use wayland_protocols;`,
`pub use wayland_protocols_misc;`, `pub use wayland_protocols_wlr;`).

Registry XML (authoritative wire defs):
- `/home/codebam/.cargo/registry/src/index.crates.io-*/wayland-protocols-0.32.13/protocols/staging/{xdg-toplevel-drag/xdg-toplevel-drag-v1.xml, ext-transient-seat/ext-transient-seat-v1.xml}`
- `.../wayland-protocols-wlr-0.3.12/wlr-protocols/unstable/wlr-export-dmabuf-unstable-v1.xml`
- `.../wayland-protocols-misc-0.3.12/protocols/server-decoration.xml`

## 1. xdg-toplevel-drag-v1 (staging, v1) — most important (tab tearing)
- `xdg_toplevel_drag_manager_v1`: requests `destroy` (destructor),
  `get_xdg_toplevel_drag { id(new xdg_toplevel_drag_v1), data_source(wl_data_source) }`;
  enum `error::invalid_source` (data_source used for non-dnd).
- `xdg_toplevel_drag_v1`: requests `destroy` (destructor; raises `ongoing_drag` if drag not ended),
  `attach { toplevel(xdg_toplevel), x_offset(int), y_offset(int) }`; enums
  `error::toplevel_attached`, `error::ongoing_drag`. **No compositor->client events.**
- Semantics: `attach` makes the toplevel move with the cursor during the DND like
  `xdg_toplevel.move`; unmapping detaches; must be issued before `wl_data_device.start_drag`.
- Integration: repo's `xdg_toplevel.move_request` handler is currently smithay's default (no-op);
  DND is handled via `smithay::input::dnd::{DnDGrab, DndGrabHandler, WaylandDndGrabHandler}` in
  `handlers/mod.rs:71-114`. A faithful impl must observe `wl_data_source.dnd_drop_performed` /
  `cancelled` to decide the final position.

## 2. ext-transient-seat-v1 (staging, v1)
- `ext_transient_seat_manager_v1`: requests `create { seat(new ext_transient_seat_v1) }`,
  `destroy` (destructor).
- `ext_transient_seat_v1`: event `ready { global_name(uint) }`, event `denied`, request
  `destroy` (destructor, destroys associated seat).
- Semantics: a privileged client mints a new short-lived `wl_seat`. To implement really you must
  create a brand-new `wl_seat` global: `SeatState::new_wl_seat(&mut seat_state, &dh, name)` returns
  a `Seat<D>` (`wayland/seat/mod.rs:166`), advertise it (so `ready`'s global_name is its registry
  name), and tear it down on the client's `destroy`. The repo currently holds exactly one seat
  (`state.rs:924-932`) — a real transient seat needs its own pointer/keyboard/touch wiring.
- If you cannot mint a real seat: the honest answer is the `denied` event (protocol explicitly
  provides it for "creation was denied"), NOT a fake seat.

## 3. wlr-export-dmabuf-v1 (wlr, v1) — simplest
- `zwlr_export_dmabuf_manager_v1`: requests `capture_output { frame(new frame_v1),
  overlay_cursor(int), output(wl_output) }`, `destroy`.
- `zwlr_export_dmabuf_frame_v1`: events `frame{width,height,offset_x,offset_y,buffer_flags,flags,format,mod_high,mod_low,num_objects}`,
  `object{index,fd,size,offset,stride,plane_index}`, `ready{tv_sec_hi,tv_sec_lo,tv_nsec}`,
  `cancel{reason}`; enums `flags::{transient=0x1}`, `cancel_reason::{temporary=0,permanent=1,resizing=2}`;
  request `destroy` (destructor; client closes all FDs).
- With no dmabuf capture path: `capture_output` → init the frame object, immediately send
  `cancel(cancel_reason::Permanent)`. Spec-legal, matches the honesty convention.

## 4. kde-server-decoration (misc, v1) — smithay provides it
- `org_kde_kwin_server_decoration_manager`: request `create { id(new decoration), surface(wl_surface) }`;
  event `default_mode { mode }`; enum `mode::{None=0,Client=1,Server=2}`.
- `org_kde_kwin_server_decoration`: request `release` (destructor), `request_mode { mode }`;
  event `mode { mode }`; enum `mode::{None,Client,Server}`.
- **smithay impl**: `smithay::wayland::shell::kde::decoration::KdeDecorationState`
  (`SM=/home/codebam/.cargo/git/checkouts/smithay-afa91a524fec7e0b/b6e5bf0/src/wayland/shell/kde/decoration.rs`):
  `KdeDecorationHandler` trait (`fn kde_decoration_state(&self)`, `new_decoration(surface, decoration)`,
  `request_mode(surface, decoration, mode)`, `release`), `KdeDecorationState::new::<D>(&dh, DefaultMode)`
  and `new_with_filter`. Dispatch in `handlers.rs` uses `GlobalDispatch2`/`Dispatch2` on
  `KdeDecorationManagerGlobalData` / `GlobalData` / `KwinServerDecorationData` — wired through the
  existing `smithay::delegate_dispatch2!(ViewportState)`.
- Precedent to copy: the repo's `XdgDecorationState` field (`state.rs:670,918-919`) and
  `impl XdgDecorationHandler for ViewportState` (`handlers/xdg_shell.rs:252-281`) with
  `fn decoration_mode()` reading `self.server_decorations`.
- **decorations config key**: `config.rs:266` `pub decorations: Option<String>`; applied at
  `state.rs:5415-5418` — `"client"` hands the frame back (`server_decorations = false`), anything
  else keeps it server-side (default true at `state.rs:993`). Map to
  `DefaultMode::Server` / `DefaultMode::Client` accordingly so KDE/SDL/Qt-only clients don't draw
  doubled decorations.

## Verification
- `cargo check -p viewport` and `cargo test -p viewport` from the worktree root, after
  `export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0='*'`.
- Commit to the `wt/protocol-holes` branch; do not push/merge.
