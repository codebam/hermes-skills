---
name: xwayland-input-debugging
description: Debug X11 or native client input under a Wayland compositor.
version: 1.0.0
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [wayland, xwayland, x11, input, pointer, debugging, compositor]
---

# Debugging client input under a Wayland compositor (XWayland)

Use when an app's input (mouse, keyboard, capture/mouselook) is broken inside a
Wayland compositor session — typically an **X11 game or app running through
XWayland**, or a native Wayland client whose pointer handling is off. Covers the
classic symptom: menu/pointer works, in-game mouselook (relative motion) is dead.

This is a *diagnostic* workflow. It reliably tells you which layer of the stack is
broken (compositor -> XWayland -> X server -> client) and which specific delivery
path is failing. You may still hand off to a maintainer/triage once you've pinned
the layer; the narrowing is the deliverable.

## How input actually flows (X11 client)

```
mouse -> compositor (libinput)
   -> wl_pointer.motion (ABSOLUTE)  : drives the normal cursor; what menus/buttons use
   -> zwp_relative_pointer          : drives mouselook; what a captured game uses
        -> XWayland -> XI2 raw motion on the "xwayland-relative-pointer" device
             -> GLFW/Minecraft read XI_RawMotion (selected on the ROOT, XIAllMasterDevices)
   -> wp_pointer_constraints (lock | confine) : the compositor's name for "cursor captured"
```

- **Menu works, in-game dead** = the relative path (`zwp_relative_pointer` -> relative
  device -> XI raw) is at fault, or the lock broke the client's warp fallback.
- **Clicks work but no look** = absolute+button delivery fine; relative/constraint
  interaction is the problem.
- XWayland (>=24, i.e. `xwayland-24.x`) emulates `XGrabPointer` for a hidden-cursor
  grab by converting it into a `zwp_pointer_constraints` object:
  - visible cursor + grab `confine_to` -> `confine` (cursor keeps moving, clamped)
  - hidden cursor -> `lock` via `xwl_seat_maybe_lock_on_hidden_cursor` (cursor pinned)
- With a **lock**, the compositor sends only relative motion (no absolute). GLFW's
  warp fallback (when `rawMouseMotion` is false) REQUIRES absolute recentring — so a
  lock can freeze a warp-fallback game's camera while clicks still work.

## Diagnosis steps

1. **Confirm the client's transport.** `echo $DISPLAY`, `ps` for Xwayland. If it has
   `DISPLAY=:N` it's X11-via-XWayland; `WAYLAND_DISPLAY` = native Wayland.
2. **Enumerate the X input devices** (`xinput list`, e.g. `nix run nixpkgs#xinput`):
   you must see `xwayland-pointer` and `xwayland-relative-pointer` slaves under the
   master. The relative device (sourceid of raw events) is the mouselook feed.
3. **Capture live events** with `xinput test-xi2 --root` and diff menu vs game:
   does the absolute cursor move in-game (=> not locked), do raw deltas flow?
4. **Probe exactly as the client does** (do NOT guess). GLFW 3.4 selects
   `XI_RawMotion` on the **root** window, `XIAllMasterDevices` — NOT on its own
   window. Use `scripts/xiprobe.c`.
5. **Probe the grab state**: does anything hold `XGrabPointer`
   (`AlreadyGrabbed`)? Use `scripts/grabprobe.c`. Re-run while the app is actively
   capturing.
6. **Name the delivery path** from the probes:
   - raw events on the relative device with real nonzero deltas = transport works ->
     the break is at/inside the client's GLFW path (rawMouseMotion / disabledCursorWindow
     / XISelectEvents actually failing).
   - raw events absent while cursor pinned = lock path, and relative is not reaching XWayland.
7. **Confirm against upstream source**:
   - XWayland: path is `hw/xwayland/xwayland-input.c` (NOT `xwayland/pointer.c`),
     in the `xorg/xserver` repo, tag `xwayland-24.1.13` (a separate tag series).
     Key fns: `xwl_seat_maybe_lock_on_hidden_cursor`, `relative_pointer_handle_relative_motion`,
     `dispatch_relative_motion` (POINTER_RAWONLY on the relative device), `xwl_pointer_warp_emulator_*`.
   - GLFW: `src/x11_window.c` — `disableCursor`, `enableRawMouseMotion` (selects on
     the root), the `processEvent` XI_RawMotion block (`disabledCursorWindow &&
     rawMouseMotion && evtype==XI_RawMotion`, reads `re->raw_values`).
8. **Read the client SDK's consumption code** as above; the gates are what gates.

## Pitfalls

- **Coordinate live captures with the user explicitly.** When a live test needs the
  user to interact (enter the game, wiggle the mouse for N seconds), TELL them exactly
  what to do and WHEN, and **do not start measuring until they confirm ("ready")**.
  Never assume their timing aligns with your capture window — this session burned two
  captures because the user wasn't in-game. (User correction.)
- Raw events reaching the *root* are necessary but not sufficient — verify they reach
  the *client's* selection. GLFW selects on root, so a window-only selection probe
  firing nothing is a red herring; factor in what the client actually selects.
- Synthesized motion (warps, XTEST) can masquerade as user motion in raw captures:
  check the device id and the delta magnitudes, not just the event count.
- Distinguish **lock vs confine** by whether the absolute cursor keeps moving
  (confine) or is pinned (lock). The design intent is documented in the compositor's
  `docs/debugging.md` "Pointer capture" section.
- **Building C probes on NixOS**: the store header paths differ per dev-output; see
  `references/nix-c-probe-build.md` for a working incantation.
- If you've pinned the layer to inside the client and cannot introspect it from
  outside, **write a findings file for triage** rather than spinning: a neutral
  `findings.md` with symptom, verified facts, layer narrowing, ranked hypotheses,
  and a cheap decisive experiment. (User preference: prefers a findings.md handoff
  over endless probing.)

## Support files

- `scripts/xiprobe.c` — XI2 raw+motion capture mirroring GLFW's selection; the
  authoritative "did deltas reach the X server" check.
- `scripts/grabprobe.c` — X pointer-grab state probe (`GRAB_FREE` vs `ALREADY_GRABBED`).
- `references/xwayland-input-path.md` — the protocol/data-flow details + the 2026
  Minecraft-on-Viewport case study (narrowing, real captures, candidate hypotheses).
- `references/nix-c-probe-build.md` — compiling a C probe against NixOS store X11 headers.