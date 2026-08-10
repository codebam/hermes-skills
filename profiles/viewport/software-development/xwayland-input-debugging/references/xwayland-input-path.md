# XWayland input path — protocol detail + 2026 Minecraft-on-Viewport case study

Condensed knowledge from live-debugging an X11 game with dead mouselook under a
smithay-based Wayland compositor (Viewport) via XWayland 24.1.13.

Status note: this case was NOT resolved to a fix. The diagnostic narrowing below
is what worked; the fix hypothesis is unverified and should not be treated as
validated guidance.

## The two Wayland pointer feeds

- `wl_pointer.motion` — absolute position. Drives the normal cursor, menus, buttons.
- `zwp_relative_pointer_v1` — deltas. Drives mouselook inside a captured game.
- `wp_pointer_constraints` — the compositor-side name for "cursor captured":
  `lock` pins the cursor (only relative delivered); `confine` clamps it to a region
  (absolute still delivered, cursor keeps moving).

## XWayland end (xorg/xserver, tag `xwayland-24.1.13`)

- File path is `hw/xwayland/xwayland-input.c` (NOT `xwayland/pointer.c`).
  (The raw tag also 404s at `xwayland/pointer.c` / `xwayland/*` — the 24.1 line
  split XWayland into its own release series with tags `xwayland-24.x`.)
- XWayland subscribes to `zwp_relative_pointer` and produces XI2 raw motion on a
  dedicated slave device named `xwayland-relative-pointer`:
  `relative_pointer_handle_relative_motion` -> `dispatch_relative_motion`
  (QueuePointerEvents(..., POINTER_RAWONLY)).
- `XGrabPointer` emulation:
  - visible cursor + `confine_to` -> `xwl_seat_confine_pointer` (`zwp_confined_pointer`).
  - hidden cursor -> `xwl_seat_maybe_lock_on_hidden_cursor` upgrades it to
    `zwp_locked_pointer` via `xwl_pointer_warp_emulator` (LIFETIME_PERSISTENT).
- Mixing: when a wl frame carries both relative and absolute, `dispatch_absolute_motion`
  picks `device = relative_pointer` with `POINTER_NORAW`; pure relative frames use
  the relative device with `POINTER_RAWONLY`.

## GLFW end (src/x11_window.c, 3.4.x / LWJGL bundled)

- `enableRawMouseMotion`: `XISelectEvents(display, root, ...)` with `XI_RawMotion`,
  `XIAllMasterDevices`. **Selects on the ROOT, not the window.**
- `processEvent` consumes XI raw ONLY when:
  `_glfw.x11.disabledCursorWindow` is set AND `window->rawMouseMotion` is true AND
  evtype == XI_RawMotion; then `xpos += re->raw_values[0]; ypos += re->raw_values[1]`.
- `disableCursor` = hide cursor + grab (`captureCursor` -> XGrabPointer) + optionally
  enableRawMouseMotion. If `rawMouseMotion` is false, DISABLED falls back to a
  warp loop (XQueryPointer deltas + XWarpPointer to center) which NEEDS the cursor
  to be able to recenter.

## Key insight / why "transport works but camera dead" is possible

If the compositor honors a `zwp_locked_pointer` on an XWayland surface, it stops
delivering absolute motion (Viewport: `if locked { pointer.relative_motion(...);
pointer.frame(...); return; }`). A raw-consuming game is fine. A warp-fallback
game is not: its `XQueryPointer` never changes, so deltas are zero — while clicks
still work (buttons delivered at the pinned position) and the cursor is hidden.

So success criteria to name the layer:
- Real nonzero raw deltas reach the X server on source=relative device => compositor
  -> XWayland -> server delivery is fine; the break is in the client (rawMouseMotion
  off, or its XISelectEvents failing) or in the lock-vs-warp interaction.

## Case data (Viewport, Minecraft Java 26.2, PrismLauncher, LWJGL 3.4.1/GLFW)

- Game: X11 window id 0x400007, geometry 3846,16 1253x1408 (screen ~5120x1440).
- `xinput list`: `xwayland-pointer:55` (6), `xwayland-relative-pointer:55` (7),
  master pointer id 2, XTEST keyboard. (Old xinput CLI was removed in 22.11; use
  `nix run nixpkgs#xinput`/`nix run nixpkgs#xdotool` on NixOS.)
- In-game capture over 30s: `TOTAL raw=4900 motion=0`, e.g.
  `RAW dev=2 source=7 v0(8.00 acc/4.00 raw) v1(-2.00 acc/-1.00 raw)` — real deltas
  reaching the server. Selection on root delivered; selection on the game window
  delivered nothing (GLFW selects root, so the root result was the relevant one).
- X grab state in-game flickered `ALREADY_GRABBED`/`GRAB_FREE` (probe stole it each
  poll) — the game's `XGrabPointer` WAS active.
- Conclusion recorded: transport through XWayland works; leading (unverified)
  hypothesis is GLFW warp-fallback being blocked by the compositor's pointer LOCK
  on the XWayland surface; test = never hard-lock an XWayland pointer (treat lock
  on an X11 surface as confine, keep absolute motion) and see if the game rotates.

## Live-capture coordination (user correction, 2026-08-08)

Two captures were invalid because the user was NOT in-game during them. Rule:
for timed interactive repros, tell the user exactly what to do and when, wait for
an explicit "ready" before starting the capture, and keep the capture window wide.
The user preferred "please tell me before you want a test" over silently-timed runs.