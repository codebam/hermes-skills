# Is a client XWayland or native Wayland? And what "doesn't focus" means

## Why this matters

The same visual complaint — "the window launched but doesn't look focused" — has
DIFFERENT root causes depending on whether the client is an X11 window (through
Xwayland) or a native Wayland window. Before touching any focus code, establish
which protocol the window actually speaks. Guessing wrong sends you down the
xwayland path for a Wayland bug (or vice versa).

Concrete trap: **pinentry-gnome3 is a native Wayland window**, not an X11 one,
even though setup guides and the user's own shorthand ("pinentry-gtk") make it
sound like an X client. It maps as `gcr-prompter` with `GDK_BACKEND=wayland`.

## How to tell which protocol a window uses (fast, from the live session)

1. **Which binary is the client really?** `nix run nixpkgs#<pkg>` / check
   `/run/current-system/sw/bin`. e.g. the graphical pinentry on this host is
   `pkgs.pinentry-gnome3`, not `pinentry-gtk` (which isn't even installed).
2. **Check the client process env** (`cat /proc/<pid>/environ`):
   - `GDK_BACKEND=wayland` + `WAYLAND_DISPLAY=wayland-N` + a single open socket
     whose inode matches the wayland socket → native Wayland.
   - `DISPLAY=:N` only, or a socket matching `/tmp/.X11-unix/X0` → XWayland.
   - The live Viewport session exports `DISPLAY=:0 WAYLAND_DISPLAY=wayland-1
     GDK_BACKEND=wayland` to everything it spawns, so GTK clients default to
     Wayland.
3. **Query the compositor**: `viewport msg -t view.query` and look at the view's
   `app_id`. Wayland GTK → `gcr-prompter`; an X client → its WM_CLASS. A window
   with `app_id` like `XEyes` (`xeyes`) is X11.
4. **Cross-check with a known-X11 probe**: launch `xeyes` (definitely X11) — if
   it lands as one protocol and your suspect lands differently, that difference
   is the signal.

## "Keyboard focus works but the window is greyed / no focus border"

Two separate things carry "focus", and only one is visible:

- **Keyboard focus** — decides where keystrokes go (`keyboard.set_focus` in
  smithay). If you can TYPE into the window, keyboard focus IS set.
- **Activated state** — the xdg-toplevel `Activated` state that makes a toolkit
  (GTK etc.) draw its titlebar/text as focused. It only reaches the client via a
  configure. This is what the user means by "the window is greyed / native
  border doesn't focus."

So "I can type into it but it looks unfocused" ⇒ keyboard focus is delivered but
the `Activated` configure is not reaching the client. On this compositor,
activation is applied in `notify_focus` → `activate_view` → `window.set_activated`
+ `send_pending_configures`. A click fixes it live because by the time you click,
the window IS mapped into the Space and the click path maps + activates together.

### Root cause — CONFIRMED launch-ordering race (pinentry session)

`activate_view` iterates `self.space.elements()` and only calls
`set_activated(true)` on the focused window if it is ALREADY in the Space. On
launch the shell sends `view.focus` synchronously from `addView` (`focusIt()`),
but the `view.layout` that maps the window into the `Space` goes out only later,
on an animation frame (`pumpGeometry`/`requestAnimationFrame` in geometry.js).
So the compositor processes `view.focus` FIRST → `activate_view` runs → the new
window is not yet in the Space → the loop never reaches it → `Activated` is
never set. When `view.layout` later maps it in, nothing re-applies activation →
keyboard focus works but the client renders greyed until clicked.

### The FIX (validated: `cargo test -p viewport` passes, clippy/fmt clean)

`activate_view` must set the `Activated` state on the focused window even when it
isn't mapped into the Space yet. The pending state then rides out in the
configure that `view_layout` sends when it maps the window. In
`crates/viewport/src/state.rs` `activate_view` (roughly):

```rust
let focused = self.views.get(id).map(|view| view.window.clone());
let mut in_space = false;
for window in self.space.elements() {
    let active = focused.as_ref() == Some(window);
    window.set_activated(active);
    if active { in_space = true; }
}
// A window focused before it is mapped (launch: view.focus before the
// view.layout that maps it into the Space) is not in the space yet, so the
// loop above never reaches it and its client is never told it is activated.
// Set it directly; the pending configure carries it out on first layout.
if !in_space {
    if let Some(window) = focused {
        window.set_activated(true);
    }
}
self.send_pending_configures();
```

This is protocol-agnostic — it also covers XWayland windows that hit the same
race, so a "fix-xwayland-focus"-named branch can legitimately carry a fix that
lives in the Wayland activation path.

### Sign-off rule for this class of fix

Watch the compositor's own focus grant independent of the client's appearance:
`viewport msg -t subscribe view.added view.focused view.removed`. If
`view.focused {id}` IS emitted for the launched window, focus was granted
compositor-side — the remaining grey is purely the `Activated`-not-reached
client issue above (i.e. the `activate_view`/Space timing), not a binding or
keyboard-focus problem. Don't burn time on binding matchers or xwayland handling
once `view.focused` confirms the grant.

## Reusable live-debugging probes

- Watch protocol-level focus traffic from the compositor:
  `viewport msg -t subscribe view.added view.focused view.removed`
  (background it with `terminal(background=true)`, then `process(action='poll')`).
  It replays current `view.added` state on connect, then streams live
  `view.focused` — so a freshly-focused new window shows as
  `add → focused {id}`. This tells you whether the compositor GRANTED focus,
  independent of whether the client looks focused.
- `WAYLAND_DEBUG=1 <client>` captures the client's own Wayland traffic
  (configure events / states). Pitfall: **pinentry-gnome3 is a thin DBus proxy**
  that delegates the actual window to a separate `gcr-prompter` process, so
  `WAYLAND_DEBUG=1 pinentry` produces an empty log — you must target the process
  that owns the window.
- **pinentry quits after ~10s of inactivity** regardless of GETPIN still being
  pending — it will vanish mid-investigation. Re-launch when it does; don't
  chase a corpse. `ps aux | grep -i pinentry|gcr` and `viewport msg -t view.query
  | grep gcr` to confirm it's still up.

## Diagnosis-order rule

Do the protocol check FIRST (env + view.query app_id + xeyes cross-check), THEN
reason about which focus path applies. Do not assume an xwayland bug from a
GTK-looking client, and don't reach for xwayland code until you've confirmed the
window is actually an X11 surface.
