# Protocol research — three hand-written Viewport protocols (VERIFIED from code)

Groundwork completed but the session was cut off before test files were written. Everything
below is verified by reading the code / generated headers; the "do next" plan is unverified.

Repo: `/var/lib/hermes/workspace/Viewport/.worktrees/integration-tests` (branch wt/integration-tests).

## zwlr_foreign_toplevel_management_v1
- Server: `crates/viewport/src/foreign_toplevel.rs`. Global `zwlr_foreign_toplevel_manager_v1`,
  `const VERSION: u32 = 3` (foreign_toplevel.rs:36). Dispatch by request on
  `zwlr_foreign_toplevel_handle_v1` (lines 267-318): `Activate → activate_toplevel(id)`,
  `Close → close_toplevel(id)`, `SetFullscreen → fullscreen_toplevel(id,true)`,
  `UnsetFullscreen → fullscreen_toplevel(id,false)`.
- Handler (handlers/mod.rs:249-279): `close_toplevel` → `toplevel.send_close()` → client's
  `xdg_toplevel.close` fires (observable). `activate_toplevel` only acts if `view.mapped`
  → calls `apply::focus_view` → `set_state(id,true,..)` publishes `handle.state(Activated)`.
  `fullscreen_toplevel` → notifies `window.fullscreen.set` (shell-only; no observable headless).
- IMPORTANT: `foreign_management_state.add` is called in handlers/compositor.rs:345 only when a
  surface commits a buffer (`view.mapped = true`, line 293). Client MUST attach an shm buffer.
- `rm` (`remove(id)`) sends `handle.closed` (foreign_toplevel.rs:147-152) — a second observable
  if the window is destroyed.
- Client XML (vendored now at `protocols/wlr-foreign-toplevel-management-unstable-v1.xml`):
  manager listener = { toplevel, finished }; handle listener = { title, app_id, output_enter,
  output_leave, state, done, closed, parent }.
  Requests: `zwlr_foreign_toplevel_handle_v1_activate(handle, seat /*NULL*/)`,
  `_close(handle)`, `_set_fullscreen(handle, output /*NULL*/)`, `_unset_fullscreen(handle)`.
  State enum: `ZWLR_FOREIGN_TOPLEVEL_HANDLE_V1_STATE_MAXIMIZED=0`, `_MINIMIZED=1`,
  `_ACTIVATED=2`, `_FULLSCREEN=3` (state arrives as a `struct wl_array` of native-endian u32s).
- Test plan: create + map an xdg_toplevel, wait for manager `toplevel` event (proves listed),
  `activate(NULL)` then `close()`, assert `xdg_toplevel.close` fires → exit 0. Note: a foreign
  toplevel handle can exist for an unmapped window; activation needs mapped.

## ext-workspace-v1
- Server: `crates/viewport/src/workspace.rs`. Global `ext_workspace_manager_v1`,
  `const VERSION: u32 = 1` (workspace.rs:47). Bind → `greet()` (workspace.rs:155-171) publishes
  groups + workspace handles + `done()`.
- CRITICAL: `WorkspaceState` starts empty. Groups/handles only appear after the compositor
  receives `workspace.list` over the control socket (apply.rs:199-220 → 
  `workspace_state.set::<ViewportState>`). Without that, a client sees a manager with NO groups.
- `workspace_asked` (handlers/mod.rs:1008-1044) → `notify(Event::WorkspaceRequest { action, id,
  name, output })`. Requires `commit` on the manager before requests are forwarded
  (workspace.rs:406-410). No headless shell, so the forwarded request is only observable via
  the IPC event log — verify group/workspace *presence* as the pass condition.
- Group gets `capabilities(CreateWorkspace)` + `output_enter`; handle gets capabilities
  `Activate|Deactivate|Remove|Assign`, `name`, `state`. Client sends `workspace_group` /
  `workspace` events from manager listener.
- Control-socket JSON for `workspace.list` (from viewport-ipc request.rs:154-159):
  `{"type":"workspace.list","workspaces":[{"id":"...","name":"...","output":"<output-name>",
  "active":true}]}` — `Workspace{id,name,output:Option,active,urgent,hidden}`. Output name of
  headless output unknown until probed; use `output.query` / parse, or name it "DSI-1"/headless.

## zwlr_output_management_v1
- Server: `crates/viewport/src/output_management.rs`. Global `zwlr_output_manager_v1`,
  `const VERSION: u32 = 4` (output_management.rs:42, adaptive_sync arrives at v4).
  Bind → `bind` (line 318) → `advertise` (line 128): for each head send `manager.head(head)`,
  `head.mode(mode)` objects, then `manager.done(serial)` (line 176).
- Config flow (Dispatch, lines 415-505): `create_configuration(id, serial)` →
  `enable_head { id, head }` (returns zwlr_output_configuration_head_v1) →
  on config head `set_mode { mode }` → `apply()` → `apply_output_configuration` returns bool →
  `succeeded()` / `failed()`; `cancelled()` if serial is stale.
- `apply_output_configuration` (state.rs:2136-2232): returns false if a named head is gone,
  if `still_on` ends empty (all heads disabled), or if the mode isn't one the output offers
  (only enforced when a real udev/DRM backend exists — headless allows custom). Otherwise
  applies and returns true.
- Client XML (vendored now at `protocols/wlr-output-management-unstable-v1.xml`):
  manager listener = { head, done }; head listener = { name, description, physical_size, mode,
  enabled, current_mode, position, transform, scale, finished, make, model, serial_number,
  adaptive_sync, current_scale }; config listener = { succeeded, failed, cancelled };
  config-head listener = { (empty) }.
  Requests: `zwlr_output_manager_v1_create_configuration(manager, serial)`,
  `zwlr_output_configuration_v1_enable_head(config, head)`,
  `zwlr_output_configuration_head_v1_set_mode(ch, mode)`, `zwlr_output_configuration_v1_apply(config)`.
- Test plan: bind manager v4, collect first head + a mode + the `done` serial, then
  create_configuration(serial) → enable_head(head) → set_mode(mode) → apply → expect `succeeded`.
  Use a head-advertised mode so it works on both headless and DRM.

## XML provenance & version matching (VERIFIED)
- Server wire code comes from Smithay's reexports: Cargo.lock resolves `wayland-protocols-wlr`
  0.3.12 (same for both wlr protocols) and `wayland-protocols` 0.32.13 (staging => ext-workspace).
- wlr XMLs live in the cargo registry source:
  `/home/codebam/.local/share/containers/storage/volumes/viewport-arch-cargo/_data/registry/src/
  index.crates.io-1949cf8c6b5b557f/wayland-protocols-wlr-0.3.12/wlr-protocols/unstable/`
  (`wlr-foreign-toplevel-management-unstable-v1.xml`, `wlr-output-management-unstable-v1.xml`).
  Both ALREADY COPIED to `protocols/` (uncommitted).
- ext-workspace-v1.xml comes from `pkg-config --variable=pkgdatadir wayland-protocols` →
  `.../staging/ext-workspace/ext-workspace-v1.xml` (nix store, wayland-protocols-1.49).
- Version check: foreign-toplevel manager XML = 3 (matches server), output-manager XML = 4
  (matches), ext_workspace_manager_v1 = 1 (matches). All verified.
- NOTE: vendored `protocols/wlr-layer-shell-unstable-v1.xml` is interface v4 while registry
  0.3.12 is v5 — the vendored copy is intentionally pinned to what the compositor serves. When
  vendoring a new wlr XML, copy from the same wayland-protocols-wlr revision the server pins,
  and double check the `<interface version=` if it matters.

## Nothing else
Compositor protocol implementation files (foreign_toplevel.rs, workspace.rs,
output_management.rs, state.rs) were NOT modified. Do not modify them unless a test blocker
forces a trivial, justified fix — note it explicitly if you do.
