---
name: viewport-compositor
description: Develop and ship the Viewport Wayland compositor.
version: 1.0.0
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [viewport, wayland, compositor, smithay, nixos, rust, shell]
---

# Viewport compositor development

The user owns and actively develops **Viewport**, a Wayland compositor whose
shell is a web page. This skill covers the codebase's architecture, how to add
a config option end-to-end, and the build → test → bump-flake → cache pipeline.

## Identity traps (get these right first)

- The running compositor is **`viewport-cef`**, which IS the Smithay rewrite
  (a Rust compositor + CEF-rendered web shell). Do not confuse it with the old
  C `codebam/viewport` repo. The live NixOS host uses `viewport-smithay`.
- Repo root on this machine: **`~/Documents/git/Viewport`** (remote
  `github:codebam/viewport-smithay`). This is where source edits happen, NOT
  a `/nix/store/...-source` path (those are read-only build inputs).
- NixOS home config generating `~/.config/viewport/config.json`:
  `/persistent/etc/nixos/home/viewport.nix` (uses `builtins.toJSON`).

## Config architecture — how an option flows (add one end-to-end)

1. **`crates/viewport/src/config.rs`** — the config `File` struct + per-block
   structs. Everything is `Option`, `#[serde(default)]` on every struct, and a
   missing key must leave the value untouched (config is a *patch* over
   defaults). Add a block struct + a field on `File`.
2. **`crates/viewport/src/state.rs`** — `Config::default` build site (~line
   955) and `apply_config(file)` (~line 5051). Copy the field from the `File`
   onto `self.config`. Only what the file contains is applied.
3. **`crates/viewport-ipc/src/event.rs`** — the IPC `Config` event struct
   shipped to the shell: `#[serde(default, skip_serializing_if = "Option::is_none")]`
   for optional members. **Every `Config { ... }` literal in tests must gain
   the new field** (`gaps: None`, etc.) or nothing compiles.
4. **shell JS** (`data/shell/`) — the shell is the layout engine. A
   `config` message arrives in `commands.js`'s `viewport` listener; call a new
   `applyX(message.x)` there. `windows.js` has `applyTheme` (writes CSS custom
   props) — mirror it for other value kinds.
5. Docs & example: `data/config.example.json` (add a `_key: [...]` help block
   + default), `docs/configuration.md`, and add parse tests in `config.rs`.

Config is read **once at startup** (`main.rs` → `state.apply_config`). The
shell `reload` keybinding (`Mod4+Shift+c`) re-sends the *cached* `Config` and
reloads the page only — it does **NOT** re-read the config file. Config
changes require a compositor restart.

**Extra bar widgets — `bar_widgets`.** The bar is extensible via a
`bar_widgets` list (disk mounts, volume via `wpctl`, mic via `wpctl` on the
SOURCE node, weather via open-meteo)
that ADDS to the shipped modules without touching the default bar/`index.html`.
It is a config + status-sampled-data class spanning all seven touch points
(config.rs, status.rs, event.rs, state.rs ×2, bar.js, commands.js); the full
recipe and the shell-harness DOM-stub pitfall live in
`references/bar-widgets.md`. Rule: the compositor only samples/`wpctl`-spawns
what a widget actually asks for. **Pitfall — modern `wpctl` folds mute INTO
the Volume line (`Volume: 0.60 [MUTED]`), not a separate `Muted:` line**;
`parse_sink` must take the leading number and read `[MUTED]` or the widget
blanks the moment you mute it. See `references/bar-widgets.md`.

**Full bar override — `bar_items` (PREFER THIS for the bar's right side).**
When the user wants to reposition widgets (e.g. put a widget between modules,
or to the left of network) or drop a module, do NOT hardcode a shell hack like
inserting an element before `.net`. This session the user rejected exactly that
insertion hack three times in favor of an explicit config-driven override: add a
`bar_items` list where each entry is a bare string (built-in module: mode, net,
disk, cpu, load, memory, clock) OR a widget object (same shape as bar_widgets);
present (even empty) it REPLACES the whole right side in the given order and
supersedes `bar_widgets`. Same seven touch points as bar_widgets plus an
untagged `BarItemConfig`/`BarItem` enum; when it wins, the status sampler is
configured from ITS widgets. **Pitfall — first-build "clear shipped modules":**
in `syncBarRight`, capture `const firstBuild = output.barItemsEls === undefined`
BEFORE binding `output.barItemsEls = []`; binding first makes the guard always
false, the index.html default modules stay, and the clock appears TWICE (the
classic symptom). Test that `.bar-right` children length == barItems length.

**Widgets are interactive — `shell.exec`.** Widgets are DOM on the shell page, so
a pointer over them already reaches the DOM; `wireWidget` (bar.js, once per
element, reads `el._widget`) sends a `shell.exec` IPC request the compositor runs
via `crate::input::spawn` (same path as a keybinding `exec`). Per kind: `volume`
wheel=`wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+/-` (deltaY<0=up), right-click=
`wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle`; `mic` does the same on
`@DEFAULT_AUDIO_SOURCE@`; `disk` click=`xdg-open <path>` (default file manager);
`weather` click=`xdg-open` a maps URL for the location; a module string sends
nothing. When adding any new IPC Request, wire all three places (request.rs +
lib.rs is_known_type + msg.rs Type row and TYPES.len bump) and keep it OUT of the
C-parity 23-row table test. Full recipe in `references/bar-widgets.md`.

**Instant feedback — `status.refresh`.** The bar's numbers re-sample on a 2s
`status.update` tick. An audio widget that drives the sink through `wpctl`
(scroll volume, right-click mute) then sends a `status.refresh` IPC request so
the change appears at once — without it the display lags up to two seconds,
which makes an interaction that WORKED look like one that did not (this is the
real cause of "right-click mute doesn't seem to work", not a broken
`contextmenu` handler). It's a unit request, wired like any new IPC request and
kept OUT of the C-parity 23-row table; `apply.rs` answers it with
`state.status_tick()`. The shell sends `refreshStatus()` right after the
`shell.exec` command in `wireWidget`.

## Keybindings (chords & mouse buttons)

Keybindings live in **`crates/viewport/src/binding.rs`** (model + parser +
matchers + `defaults()`) and fire in **`crates/viewport/src/input.rs`**:
keyboard chords via `match_binding` in the `KeyboardKey` handler, mouse buttons
via `match_button` in the `PointerButton` handler. `state.rs` `apply_config`
(~line 5433) rebuilds `self.bindings` from `binds` (replaces defaults) and
`binds_override` (layers over them), then `guarantee_an_exit`.

- A `Binding` is a `modifiers` + **either** a `keysym` **or** a
  `button: Option<u32>` (libinput button code) — never both. A button binding
  has `keysym: 0`.
- **Mouse buttons parse by name** (in `button_from_name`, case-insensitive):
  `Mouse1`–`Mouse5`, `BTN_LEFT`/`BTN_RIGHT`/`BTN_MIDDLE`/`BTN_SIDE`/`BTN_EXTRA`,
  `XButton1`/`XButton2` (and `left`/`right`/`middle`). `Mouse4`=BTN_SIDE=0x113,
  `Mouse5`=BTN_EXTRA=0x114. Example:
  `"Mod4+Mouse4": "shell workspace.next"`.
- `match_button` compares modifiers (from the keyboard's held state — a mouse
  binding can require Mod4), mode, and the button code. The button path in
  `PointerButton` runs *before* the Mod4+drag-start line and consumes the click
  (never forwarded to the window under the pointer). Fires on press only.
- `match_binding` (keys) and `match_button` (buttons) are separate: a key
  binding never matches a button and vice-versa — the `Binding.button` field
  is `None` for a chord.
- **Pitfall — verify a shell verb exists before using it in docs/examples.**
  `handleShellCommand()` (commands.js) defines the only `shell ...` verbs; the
  defaults and example config must reference ones that actually exist. This
  session's example originally used `workspace.next`/`workspace.prev`, which
  did NOT exist — only `workspace.switch N` and `workspace.back`. Fix by
  implementing the command in the shell, not by dropping the example: added
  `stepWorkspace(name, delta)` (outputs.js, wraps 1..WORKSPACES=9) and wired
  `workspace.next`/`workspace.prev` in commands.js.

## The gaps, specifically

Spacing uses **CSS custom properties in `data/shell/shell.css`**, read back by
`gapPx()` (inner) / `gapOuterPx()` (outer), both defined in `scrolling.js` and
used by all layouts (tiling dividers, scrolling columns, matrix slots, solar).
The `--gap` default is `8px`; `--gap-outer` defaults to `0px`.

Three (semi) independent knobs, sway-compatible:

- **`inner`** — the gap between adjacent windows (the original `--gap`).
- **`outer`** — extra space around the edge of the output, added ON TOP of the
  inner gap, so the desktop edge is `inner + outer` while between two windows
  it stays just `inner`. Edge padding = `calc(var(--gap) + var(--gap-outer))`.
- **`smart`** — when a workspace holds exactly one window, drop the inner gap
  and keep only the outer, so a lone window does not sit far from its own edge.

**Semantics of "single window" is layout-specific.** The `smart` gap only
collapses for the *right* notion of "one window". The user's definition: in
scrolling mode a single window means **one window at 100% width** (a full-width
column), not merely "the workspace has one leaf". Don't guess from a raw leaf
count (`leavesOf(...).length === 1`) across all layouts — verify against the
layout's actual notion of a lone/full window before assuming `smart` fires.
Smart gaps work in tiling but can be missed in scrolling if the detection is
too coarse; test each layout mode explicitly.

Shell mechanics: a `smart-single` class collapses the CSS `.windows` padding to
the outer gap alone, toggled in `geometry.js` render so CSS matches the JS
`edgeGapPx(workspace)` math. Layouts that subtract the border box from their
area (matrix, scrolling, solar) must subtract the *combined* edge gap via
`edgeGapPx()`, not `gapPx()`. Ordering in `applyGaps` (windows.js): set
`--gap`, `--gap-outer`, and `gapsSmart` — applied after the theme so the
explicit option wins. Absent fields leave the prior/default value standing.

Set it via config `{ "gaps": { "inner": N, "outer": N, "smart": bool } }`
(first-class) or the theme keys `gap` / `gap-outer` (lengths). IPC Config
carries a `Gaps { inner, outer, smart }` struct (not `Option<i32>`); the shell's
`applyGaps` writes the custom properties after the theme so the explicit option
wins. `state.rs` only forwards fields the file actually names.

## IPC / `viewport msg` — runtime config IS possible now

The control-socket CLI (`crates/viewport/src/msg.rs`) forwards the requests in
`crates/viewport-ipc/src/request.rs`. **`config.gaps` was added and IS a real
runtime setter** (each field optional, merged into existing values, not
replaced):

```sh
viewport msg -t config.gaps --inner 8 --outer 0 --smart false
```

It updates the compositor's `Config` and re-announces via `notify_config()`
→ `Event::Config`, so the shell re-reads the custom properties immediately —
no restart, no file edit. Negative gaps are rejected. (Most other config is
still startup-only; `config.gaps` is the one runtime config knob.)

**When adding a new IPC Request, three places must all agree or a test fails:**
1. `crates/viewport-ipc/src/request.rs` — add the `#[serde(rename = "...")]`
   enum variant (+ unit tests that parse it).
2. `crates/viewport-ipc/src/lib.rs` — `is_known_type()` list MUST gain the new
   type string or `parse()` reports "unknown IPC message type" (the
   `every_type_offered...` msg.rs test catches this).
3. `crates/viewport/src/msg.rs` — add a `Type { name, fields, hint }` row; the
   `the_offered_types_are_the_whole_request_set` test asserts `TYPES.len()`
   and must be bumped.
Do NOT add it to the C-parity dispatch table test in request.rs (that table
asserts an exact 23-row count matching the C build; shell.command and
config.gaps are deliberately excluded).

## X11 windows and per-window state (overview scale, clip, opacity)

`frame_for` (crates/viewport/src/state.rs) resolves each window's `View` record
to build its `WindowFrame` (scale, clip, opacity, floating frame, overlay ids).
The lookup MUST go through the window's *surface*, not its toplevel:

```rust
use smithay::wayland::seat::WaylandFocus as _;
let view = window.wl_surface().as_deref()
    .and_then(|surface| self.views.find_by_surface(surface));
```

Do NOT resolve via `window.toplevel()`: that is `None` for X11 windows, so an
XWayland window silently drops ALL per-window state — `scale` falls back to 1.0
(overview thumbnails render full-size instead of shrinking to their cell),
plus no `clip` (windows overflow on a scrolled strip) and no `opacity` (no
fade-in). `Window::wl_surface()` returns the x11 surface's wl_surface, which is
exactly what `find_by_surface` matches on (views.rs `surface()` returns
`x11.wl_surface()` for X11). This is the whole design: X11 windows reach the
shell as ordinary views, so they must resolve their view like native ones — a
view lookup that routes through `toplevel()` is an X11-exclusion bug, not a
special case.

`wl_surface()` lives on the `WaylandFocus` trait (import it locally with
`use smithay::wayland::seat::WaylandFocus as _;`) and returns
`Option<Cow<WlSurface>>`, hence the `.as_deref()`. Signal other X11-excluded
sites to grep for: a `window.toplevel()` or `toplevel().wl_surface()` chain in
code that should treat X11 windows as first-class; prefer `window.wl_surface()`
+ `as_deref()` there too.

**Closing a window (`Bound::Close`) is the same trap — symptom: `Mod4+Shift+q`
kills native windows but does nothing to XWayland ones (steam, xeyes).** The
close handler resolves the focused window via `view.window.toplevel()` and
calls `toplevel.send_close()` — silently a no-op for X11 because `toplevel()`
is `None`. Fix: fall back to the X11 surface's own `close()`
(`X11Surface::close()` → `Result<(), ConnectionError>`; sends a polite
`WM_DELETE_WINDOW` when the client supports it, otherwise destroys the window):

```rust
let Some(view) = self.views.get(self.focused) else { return; };
if let Some(toplevel) = view.window.toplevel() {
    toplevel.send_close();
} else if let Some(x11) = view.window.x11_surface() {
    if let Err(e) = x11.close() {
        tracing::error!("could not close the focused X11 window: {e}");
    }
}
```

Same class as the view-lookup bug above: any per-window action routed only
through `toplevel()` is X11-excluded by construction. When a keyboard chord
"works for native windows but not XWayland", suspect a `toplevel()` gate in the
*action's* handler (not the binding matcher — that is window-agnostic).

**Before assuming an X11 bug, prove the window is actually X11.** A client that
looks like an X11 app (e.g. pinentry — `pinentry-gnome3`, a "GTK" pinentry) is
usually NATIVE WAYLAND on this host, because the live session exports
`GDK_BACKEND=wayland`. The symptom "the window launched but doesn't look
focused / is greyed" has DIFFERENT causes per protocol, so diagnosing the wrong
one wastes the whole session. Two focus concepts are independent: **keyboard
focus** (where keys go — if you can type into it, keyboard focus IS set) vs the
**activated state** (the xdg-toplevel `Activated` state that makes a toolkit
draw focus; only reaches the client on a configure). "I can type into it but
it's greyed / no focus border" ⇒ keyboard focus delivered but `Activated` never
reaching the client — on this compositor that traces to `notify_focus` →
`activate_view` iterating `space.elements()` before the window is mapped.
Fastest protocol check: read the client's `/proc/<pid>/environ` for
`GDK_BACKEND`/`WAYLAND_DISPLAY`, and `viewport msg -t view.query` for its
`app_id` (a Wayland GTK client shows `gcr-prompter`; `xeyes`/`XEyes` is X11).
**Confirmed root cause & the `activate_view` fix** (set `Activated` on the focused
window even when it isn't mapped into the `Space` yet — the shell sends
`view.focus` before `view.layout` maps it on launch): see
`references/x11-vs-wayland-focus.md`.

## Click focus, and the clipped-column hit-test footgun

**Where a click is actually handled.** Clicking a window goes through the
COMPOSITOR's `PointerButton` handler, NOT the shell's DOM `mousedown` on the
window element. Windows are real Wayland surfaces composited ABOVE the shell
page, so a pointer over a window never reaches the page (`surface_under` is
`Some`) — the compositor focuses directly and notifies the shell via
`view.focused`. The shell's `el.addEventListener('mousedown')` (windows.js,
sends `view.focus`) only fires for a pointer over the shell page itself: the
background, a drawn frame not covered by a surface, a bar widget. To trace
"clicking X did Y", walk the compositor path — `window_under`/`element_under`
→ `activate_view` → `notify_focus` → `Event::ViewFocused` → shell's
`view.focused` handler. Don't hunt in the shell's mousedown; the cause lives in
the hit-test.

**THE one — a scrolled-off column still hit-tests, and steals the click.** The
scrolling strip moves columns rather than hiding them, so a column scrolled off
the LEFT edge of one monitor keeps its full rectangle, and that rectangle lands
on the monitor beside it. Nothing is drawn there (`view.layout` carries a
`clip`, the renderer crops to it) but the window stays mapped in the `Space` at
full size — and `Space::element_under` hit-tests by the mapped rect alone.
Result: with the second monitor scrolled a few columns along, clicking a window
on the FIRST monitor focuses an invisible (clipped) column of the second, and
that strip scrolls back to it — the classic misdiagnosis "clicking the window
on DP-1 moves the stack instead of focusing it". **Input must be bounded by the
same clip that bounds drawing.** Use `self.window_under(pos)` (state.rs), which
skips `clipped_out(window, pos)` windows — never raw `space.element_under` — in
every pointer hit-test (click focus, the Mod4-drag start, notification click).
Drawing and input have to agree: what isn't on the screen can't be clicked.
(Landed as commit `7cd3f2c` "input: don't click a window that is clipped off
the screen".)

**Debugging heuristic — "clicking moves the strip" is almost never a shell
scroll bug.** `scrollOffsets` is keyed per workspace and `renderStrip` only
scrolls to bring the focused column into view: clicking an already-visible
column changes nothing, and leaving a workspace keeps its strip's position.
If the shell checks out clean under the harness, suspect the compositor
hit-test routing a click to a clipped/off-screen window via `element_under`.
Grep for `element_under(` in click paths when this symptom appears.

### Reproducing scroll-on-focus in the shell harness
Two outputs (`output.layout` with DP-1 + DP-3). Give the second output enough
windows that its strip actually overflows: **6 columns at default `1/3` width
overflow a 1904px area; 3 do NOT — a 3-window strip never scrolls, so "deep
focus" is impossible there.** Force widths with
`ws(n).children.forEach(c=>c.width=1/3)`, emit `view.focused` for the last
column (sets a nonzero `scrollOffsets` for that workspace), then emit
`view.focused` for a visible window on the other output and assert both
`scrollOffsets.get(ws)` are unchanged and `activeOutput` switched. Also set
each `output.el.__rect` — the stub's default rect is `{left:0}` for *every*
element, so `adjacentOutput`/`output.focus 'right'` can't tell the monitors
apart; place DP-3 at `left:1920` first. (Send `output.focus` via
`shell.command` to move the shell's active output when placing windows on the
second output; `output.active` IPC is compositor-side only and the shell
ignores it.)

### Worktree staleness — verify before you diagnose
A worktree can sit several commits behind `main` while main already contains
the fix. Before reading a code path, check `git log --oneline HEAD..main` and
`git merge-base HEAD main`; `git -C ~/Documents/git/Viewport worktree list`
shows whether the worktree even still exists. Diagnosing a stale worktree made
a whole session "re-find" a bug that was already fixed upstream and running on
the live desktop (`git merge-base --is-ancestor <fix> HEAD` + grep the
`.viewport-wrapped` ELF is the fast way to prove a fix is present).

## Notifications — per-output, drawn over the source window's output

The compositor claims `org.freedesktop.Notifications` on D-Bus
(`crates/viewport/src/notification.rs`) and forwards each one to the shell via
`Event::NotificationAdd` (a `Notification { id, app_name, icon, summary, body,
urgency, timeout, actions }` struct in viewport-ipc). The shell draws them —
they are ordinary DOM, styled by shell.css, not another program's windows.

**Key architectural rule: a notification lives in the corner of the output of
the window it came from — NOT in a single global page-fixed strip.** The
original implementation had one global `<div id="notifications">` that was
`position: fixed` at the top-right of the whole page, so a message from an app
on the left monitor always popped in the top-right of the *entire* desktop (the
corner of whichever output happened to win the global position). Fixing this
properly is a multi-file shell change:

- **Move the container into each output.** Remove the global `#notifications`
  div from `index.html`; add `<div class="notifications"></div>` inside the
  `desktop-template` (per output). Each output record in `syncOutputs`
  (outputs.js) captures `notificationsEl: el.querySelector('.notifications')`.
- **CSS per output, not page-fixed:** `.notifications { position: absolute;
  top: calc(var(--bar) + var(--gap)); right: var(--gap); }` — absolute within
  the output's `.desktop` (which is itself positioned at the output's layout
  x,y), not `position: fixed` to the page.
- **Resolve the target output from the source window** (`notificationOutputName`
  in session.js): the notification's `app_name` matches open windows by
  `view.app_id`; return `hostOfWorkspace(workspaceOf(id))` for the first
  matching on-screen window. An app with **no window** (daemon, headless
  notifier) has no output to claim → fall back to `activeOutputName()`.
- **Report one overlay rect PER OUTPUT** (`reportNotificationRect`): iterate
  `outputs`, and for each emit `setOverlay('notifications:' + name, el)` only
  when that output's container has children. A single global rect would draw
  every notification over one screen. The element is still a live DOM child
  while it animates away, so "container has children" already covers the exit
  tween — do NOT reintroduce a global `notificationsLeaving` counter (the
  session stripped it from motion.js for exactly this reason).

This is the same per-output overlay idiom as the floating bar:
`setOverlay('bar:' + name, ...)` in geometry.js. Any new "draw this piece of
the shell in front of windows" feature that must appear on a *specific* output
should follow this pattern: per-output container element + per-output overlay
name — never a single fixed element.

Shell test coverage (`tests/shell.test.js`): the harness builds a
`.notifications` element per desktop, and a two-monitor test asserts a
notification follows its window to the correct output and that an app with no
window falls back to the active output.

## Build & test

```bash
cd ~/Documents/git/Viewport
nix develop .#rust            # minimal env: rust, pkg-config, libudev, node
cargo test -p viewport-ipc    # pure, fast; catches Config literal breakage
cargo test -p viewport        # full compositor tests (~225)
npm run test                  # shell JS tests (tiling, scrolling, matrix)
nix flake check               # whole-flake eval (may need `--no-build`)
```

- `#rust` is the lightweight devShell; the default/wpe shells pull WebKit.
- To run just a config test: `cargo test -p viewport config::` (gaps parse
  test lives there).
- The shell test harness stubs the DOM; `getComputedStyle` is absent so
  `gapPx()` falls back to 8.
- **The shell test harness runs the concatenated shell JS in its own scope**, so
  a top-level `let` inside the shell (e.g. `gapsSmart`) is NOT reachable from
  the test file — assert on observable DOM/style state, not internals.
- `sheet.custom(...)` / `sheet.value(...)` (tests/css.js) read inline
  declaration values too, so a config test that sets `--gap`/`--gap-outer`
  leaves them mutated for later assertions that expect the default. Reset the
  custom properties (emit a gaps reset) at the end of the test block.
- **The test harness `El` DOM stub has `querySelector` but NO `querySelectorAll`
  and does not parse `:scope > .x`.** Shell code that re-queries the DOM with
  `querySelectorAll` throws inside `renderBarChrome` (runs on every render) and
  fails the whole suite in all three modes. Track dynamic elements on the
  output/record object instead (an array reused positionally, like
  `syncButtons`). See `references/bar-widgets.md`.
- **The pre-commit hook runs `fmt`, `clippy`, and the full test suite and
  REFUSES the commit on any failure.** Run `cargo fmt` first or it aborts on a
  formatting diff.

## Debugging against the user's LIVE session

The user runs a real compositor on the NixOS host and will happily restart it
into a given layout mode to test a fix. Use the live session to confirm what is
actually running and its runtime state — far faster than reproducing the whole
DOM:

```bash
readlink -f /run/current-system/sw/bin/viewport   # which store rev is actually running
# If it's a rev you built this session, the live compositor HAS your change.
viewport msg -t view.query                         # runtime config + every mapped window
```

- `view.query` returns the **runtime `Config`** (so you can confirm a config
  option like `"gaps":{"inner":15,"outer":null,"smart":true}` actually reached
  the shell) plus one `view.added` per window with its width/height/app_id —
  enough to reason about a visual bug (e.g. "one window at 100% width").
- The running binary being a rev you built means your edits are in effect;
  being the old rev explains "it doesn't work yet" before you blame logic.
- There is **no way to eval JS in the live shell via IPC** (no remote-debugging
  console surface) — verify live *state* through `viewport msg`, and verify
  *logic* through the JS test harness. Don't burn time trying to attach a
  console to the running CEF shell.
- If a `viewport msg` invocation reports "unknown IPC message type…", you are
  talking to an old binary without that request, not proving the request is
  bad — `view.query`'s config shows the runtime rev's feature set.
- **The installed `bin/viewport` is a ~3 KB wrapper script, NOT the compositor.**
  The real Rust ELF is `bin/.viewport-wrapped` (tens of MB) next to it. To check
  whether a store rev has a feature, grep/`strings` the `.viewport-wrapped` ELF —
  grepping `bin/viewport` (or the `/run/current-system/sw` symlink to it) only
  sees the bootstrap and misleadingly reports 0 (a full false "the running
  compositor lacks X" for a feature that IS present). Fastest true check: resolve
  the live process — `readlink -f /proc/$(pgrep -f '\.viewport-wrapped'|head -1)/exe`.
- **Two package outputs — know where a feature's strings live.** `viewport-cef` is
  the compositor AND carries the actual shell at `share/viewport/shell/*.js`
  (loaded via `--url`, not embedded in the ELF). `viewport-shell-cef` is ONLY the
  Chromium/CEF runtime (`libcef.so`, `chrome-sandbox`, paks) — it ships no user
  JS. So:
  - grep `.viewport-wrapped`  -> Rust/compositor-side strings (e.g. `bar_widgets`)
  - grep `share/viewport/shell/` (whole subtree) -> JS-side strings
    (`applyBarWidgets`, `open-meteo`, `geocoding-api`)
  - The literal `bar_widgets` appears in **`commands.js`**, NOT `bar.js` — grepping
    bar.js alone for the config key returns 0 and falsely reads as "old build".
    Always grep the whole `data/shell` / `share/viewport/shell/` subtree.

The JS harness cannot reach top-level `let` bindings in the shell (e.g.
`gapsSmart`), so to inspect a live internal like `singleWindowOn`/
`edgeGapPx` you cannot just read it from a test. If you need to probe one,
verify via observable DOM/style assertions in the harness instead, or reason
from the tree (`globalThis.__shell.workspaces` is exposed).

## Shipping to the NixOS host

```bash
git add -A && git commit && git push origin main    # from ~/Documents/git/Viewport
cd /persistent/etc/nixos
nix flake update viewport-smithay        # NOTE: not `nix flake lock --update-input`
nix build .#nixosConfigurations.nixos-desktop.config.programs.viewport.package
nix flake check --no-build .             # verify eval + lint
```

- `nix flake update <input>` replaces the deprecated
  `nix flake lock --update-input <input>`; the latter errors out on modern nix.
- Building the `programs.viewport.package` derivation **substitutes/caches the
  new compositor binary** so the operator's `nixos-rebuild switch` is fast and
  the change "won't break" — this is the real not-breaking check, not just eval.
- **Activation is operator-only** (no sudo; switch/rebuild/gc blocked). You do
  build + verify, then hand the operator the switch command.
- Format Nix with `nixfmt` and keep `statix check` / `deadnix` clean.

### Config-only change (e.g. a new `bar_widgets` entry) — verify end-to-end

A widget/pure-config change needs NO Rust rebuild; the feature binary is already
running. But confirm each link so you can tell the user "it's live" honestly:

1. `programs.viewport.package` is wired in
   `desktop/configuration/environment.nix` :=
   `inputs.viewport-smithay.packages.<system>.default` (→ `.cef`). That is what
   a `nix build .#nixosConfigurations.nixos-desktop.config.programs.viewport.package`
   builds/substitutes.
2. The user-facing config is generated by home-manager from
   `home/viewport.nix` (`builtins.toJSON`). Validate the produced JSON without a
   switch:
   `nix eval --raw .#nixosConfigurations.nixos-desktop.config.home-manager.users.codebam.xdg.configFile."viewport/config.json".text`
   (quote the key — it contains `/`). If it errors "attribute already defined",
   there's a duplicate `bar_widgets` key in the file — `search_files` the tree.
3. Confirm the feature binary actually ships (grep `.viewport-wrapped` + the
   shell subtree, per the pitfall above) and is what's running.
4. Confirm the config is loaded at runtime: `viewport msg -t view.query` — the
   reply's `config` carries `bar_widgets`. Config is read at startup, so if the
   running compositor predates the home-manager regen it needs a restart.
5. For a `disk` widget, the mount must be real (`df -h /path`). For `weather`,
   verify open-meteo actually resolves the location before claiming it works:
   `https://geocoding-api.open-meteo.com/v1/search?name=<location>&count=1`
   (and forecast `current=temperature_2m,weather_code` at the returned lat/lon).

## deadnix / lint pitfalls

- deadnix dislikes **both** an unused `{ pkgs, ... }` pattern AND an empty
  `{ ... }:`. If a module needs no args, write it as a plain attrset
  (`opt = { ... };`) instead of a function — both lambda forms can trip lint.
- The flake lint check can fail on pre-existing deadnix/statix issues in files
  you never touched; fix those in a *separate* commit, not the feature one.
