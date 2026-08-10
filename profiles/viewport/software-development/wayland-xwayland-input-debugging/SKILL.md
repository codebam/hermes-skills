---
name: wayland-xwayland-input-debugging
description: "Debug pointer/input dead in a client under Wayland."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [wayland, xwayland, input, debugging, compositor, smithay, games, xinput2]
    related_skills: [nixos-host]
---

# Wayland / XWayland input debugging

Use when: a client under a Wayland compositor that runs X11 apps through
XWayland has input "that works in menus but not in the main view" — e.g. mouse
clicks land but the camera/pointer doesn't move once the app captures the
cursor. High signal in this profile (Viewport, a smithay compositor) where
games run via XWayland. Do not fix blind: instrument first, then locate the
layer that drops the event.

## Why the symptom looks the way it does

- Menus/buttons work: plain `wl_pointer.motion` + absolute X11 events.
- In-game camera dead: the captured-cursor path is what feeds look.
- XWayland turns `XGrabPointer(confine_to=win)` into `zwp_pointer_constraints`
  `confine`, then — when the client also hides the cursor — **upgrades it to a
  LOCK** via its warp emulator. A locked pointer needs **relative** motion,
  which XWayland consumes from `zwp_relative_pointer_v1`, not absolute motion.
- GLFW/LWJGL (e.g. Minecraft) camera look = XI2 **raw** events
  (`XI_RawMotion`) accumulated from `re->raw_values`.

## Critical fact: GLFW selects raw motion on the ROOT, not its window

`gx11_window.c` `enableRawMouseMotion()`:
`XISelectEvents(display, _glfw.x11.root, &em, 1)` with `XI_RawMotion` and
`deviceid = XIAllMasterDevices`.

Consequence: **selecting XI raw events on the game WINDOW returns nothing** even
while the root selection gets hundreds of events/s. That is NOT a bug and NOT
evidence the game is starved. Test raw on the ROOT, exactly as GLFW does.

## Live probes (confirmed on NixOS, XWayland 24.1.13, DISPLAY :0; no sudo)

1. Inventory: `xinput list` — see `xwayland-pointer:N` (absolute/core) and
   `xwayland-relative-pointer:N` (the device carrying in-game look).
2. Watch: `xinput test-xi2 --root`
   - `EVENT type 6 (Motion)` = absolute (cursor moves). If it keeps flowing while
     the app is captured, the pointer is NOT locked.
   - `EVENT type 17 (RawMotion)` with nonzero deltas = relative path reaching the
     X server. If RawMotion flows to ROOT with real deltas, compositor→XWayland→X
     delivery is healthy; look downstream (client) next.
3. Grab probe (does anything hold the X pointer grab?): C via Xlib
   `XGrabPointer(root)` — `GrabSuccess`=free, `AlreadyGrabbed`=held. Re-run in a
   loop with timestamps to correlate with user action.
4. XI2 raw probe mirroring GLFW: subscribe `XI_RawMotion|XI_Motion` on the ROOT
   for `XIAllMasterDevices`, print `XIRawEvent->raw_values`. `source=7`
   (relative device) means the warp-emulator path fired — relative genuinely
   reached XWayland.
5. Confine vs lock: locked → absolute Motion stops (positions frozen), only
   RawMotion flows; confined/fallback → absolute motion keeps flowing (position
   advances, constrained to the window), game usually still gets relative.

Probe source (C) and the full nixpkgs compile recipe are in
`templates/xwayland-input-probes.c`.

## XWayland source pointers (stop guessing its internals)

Xwayland split from xserver and versions independently:
- Repo `xorg/xserver`, tags `xwayland-24.1.N` (not `xserver-...`).
- Input code is `hw/xwayland/xwayland-input.c` (not `pointer.c`).
- Key functions: `xwl_seat_maybe_lock_on_hidden_cursor` (confine→lock upgrade),
  `xwl_pointer_warp_emulator_handle_motion` (locked relative → POINTER_RELATIVE),
  `dispatch_relative_motion` (POINTER_RAWONLY on the relative device),
  `dispatch_absolute_motion` (uses the relative device when `has_relative`).
- Relative listener registered per-seat in `seat_handle_capabilities` and
  `maybe_init_relative_pointer_listeners_after_capabilities`.

## Compositor (smithay) side — what "correct" looks like

- Expose `relative_pointer` + `pointer_constraints` globals and implement their
  bind handlers (Viewport: `RelativePointerManagerState`,
  `PointerConstraintsState` in `state.rs`).
- On every `PointerMotion`, call `pointer.relative_motion(state, under, event)`
  BEFORE any lock early-return. Smithay routes it to the focused surface's
  client (`WpRelativePointerHandle::for_each_focused_pointer` matches by client
  id), so a locked cursor still feeds XWayland.
- Early-returning before `pointer.motion` when locked (no absolute) is fine —
  XWayland only needs the relative events there.
- To know the app is captured, check `zwp_pointer_constraints` on the surface
  under the pointer (`with_pointer_constraint` + `is_active`).

## Workflow pitfall (validated correction from a real session)

For a live/human-in-the-loop test you MUST:
1. Set up capture + probes FIRST.
2. **Tell the user the exact window and get their go-ahead** — do NOT assume
   they are mid-action while you record. ("GO enter the game and wiggle ~30s".)
   A user is typically not inside the captive mode when you begin; capturing
   early and interpreting the silence as failure is wrong.
3. Make the capture self-validating: run a state/marker sampler alongside with
   timestamps (e.g. poll the X grab every 2s) so the log tells you whether the
   user actually performed the action inside the window.

## nixpkgs C-compile recipe (no sudo; headers are in separate `.dev` outputs)

```sh
PROTO=$(ls -d /nix/store/*xorgproto*/include/X11/X.h | head -1 | sed 's|/X11/X.h||')
LDEV=$(ls -d /nix/store/*libx11-*-dev* | head -1)    # X11/Xlib.h
XIDEV=$(ls -d /nix/store/*libxi-*-dev* | head -1)    # XInput2.h
XEXT=$(ls -d /nix/store/*libxext-*-dev* | head -1)   # Xge.h
XFIX=$(ls -d /nix/store/*libxfixes-*-dev* | head -1)  # Xfixes.h
LRUN=$(ls -d /nix/store/*libx11-*/lib/libX11.so* | head -1 | sed 's|/lib/libX11.*||')
nix shell nixpkgs#gcc -c sh -c "gcc -I\$PROTO -I\$LDEV/include -I\$XIDEV/include \
  -I\$XEXT/include -I\$XFIX/include prog.c -o /tmp/prog \
  -L\$LRUN/lib -lX11 -lXi && DISPLAY=:0 /tmp/prog"
```
`.dev` outputs carry headers; `libxi` (not xorgproto) ships `XInput2.h`;
`Xge.h`/`Xfixes.h` come from libxext/libxfixes `.dev` outputs.