# Extra bar widgets (`bar_widgets`) — end-to-end recipe

The bar ships with fixed modules (clock, cpu, memory, load, root disk, net).
`bar_widgets` ADDS to that set without touching the default bar / modules —
`index.html` is unchanged. Widgets are dynamic `<span class="module widget">`
elements appended into `.bar-right` only when configured. Kinds: `disk`
(per-mount free space), `volume` (default sink volume+mute), `mic` (default
SOURCE/microphone volume+mute — a `volume` twin reading `@DEFAULT_AUDIO_SOURCE@`),
`weather` (open-meteo, fetched by the SHELL not the compositor).

**Full override — `bar_items`.** `bar_widgets` can only append after the
built-in modules; to move a widget into the middle of the modules, or drop a
built-in, use `bar_items` instead. It REPLACES the whole right side with an
explicit ordered list: each entry is a bare string naming a built-in module
(`mode`, `net`, `disk`, `cpu`, `load`, `memory`, `clock`) OR an object widget
(identical to a `bar_widgets` entry). Present (even empty) it supersedes
`bar_widgets` outright and wins; absent means the default modules + bar_widgets.
Config: untagged `BarItemConfig::Module(String)/Widget(BarWidgetConfig)`; IPC
`BarItem` (untagged) paralleling it; status sampler drives mounts/volume from
whichever widget list is actually drawn. Shell: `barItems` global, `applyBarItems`,
`syncBarRight` (append-based, first build clears the shipped modules), shared
module/widget text render; `renderBarModules` guards against missing modules
(an override may drop the clock/mode).

**Pitfall — the first-build "clear shipped modules" guard.** `syncBarRight`
must test `output.barItemsEls === undefined` and clear `.bar-right`'s children
(which hold the index.html default modules) BEFORE binding the fresh
`output.barItemsEls = []` tracking array. If you bind the array first, the
`=== undefined` guard always reads `false` (the bound array exists), the clear
never fires, and the default modules stay in `.bar-right` while the override
appends its own — the classic symptom is **the clock/date appearing twice**
(both the shipped `.bar-right` clock and the override's clock). Capture
`const firstBuild = output.barItemsEls === undefined;` first, then bind. Test
that `container.querySelector('.bar-right').children.length === barItems.length`
so a stray shipped module is caught; the shipped set is 7 (mode, net, disk,
cpu, load, memory, clock).

```jsonc
{ "bar_items": [
    "net",
    { "type": "disk", "path": "/home" },
    "clock",
    { "type": "weather", "location": "Pickering, ON, Canada" }
] }
```

```jsonc
{ "bar_widgets": [
  { "type": "disk", "path": "/home" },
  { "type": "volume" },
  { "type": "weather", "location": "New York" }
] }
```

## The two data paths

- **Disk + volume** are sampled by the COMPOSITOR (the page cannot read
  statvfs or ask PipeWire), pushed in the 2s `status.update` sample.
- **Weather** is fetched by the SHELL from open-meteo (no key, CORS `*`,
  file://-friendly). Not a compositor concern at all.

## Rust side, all seven touch points

1. `config.rs` — tagged enum `BarWidgetConfig` (`#[serde(tag="type",
   rename_all="lowercase")]`: `Disk{path}`, `Weather{location}`, `Volume`,
   `Mic`) + `File.bar_widgets: Vec<BarWidgetConfig>` (defaults empty). Parse
   tests.
2. `status.rs` — `Sample` gains `mounts: Vec<MountUsage>`, `volume:
   Option<f64>`, `muted: Option<bool>`, plus `mic_volume: Option<f64>`,
   `mic_muted: Option<bool>` (drops the `Copy` derive — that's fine).
   `Status::configure(mounts, want_volume, want_mic)` stores what to sample;
   `sample()` stats each configured path and, per wanted audio node, runs
   `wpctl get-volume <node>` ONCE per tick (one spawn answers both volume and
   mute of that node). `audio_state(node)` is the parameterized query
   (`@DEFAULT_AUDIO_SINK@` for volume, `@DEFAULT_AUDIO_SOURCE@` for mic).
3. `event.rs` — `StatusUpdate` gains `mounts: Vec<MountUsage>` (with
   `#[serde(default, skip_serializing_if="Vec::is_empty")]`), `volume: f64`
   (-1 = unknown, mirroring cpu/memory), `muted: bool`, plus `mic_volume:
   f64` / `mic_muted: bool`. `Config` gains `bar_widgets: Option<Vec<BarWidget>>`
   (duplicate tagged enum — the ipc crate must NOT depend on the viewport
   crate, so no `from_config` there; map inline in state.rs). **Every
   `Config { ... }` test literal must gain the field.** Adding a widget kind
   means adding the enum variant in BOTH `config::BarWidgetConfig` and the
   duplicate `event::BarWidget`, and UI it in the two `apply_config` map sites
   (bar_widgets AND bar_items).
4. `state.rs` — `Config::default` literal + `apply_config` (set
   `self.config.bar_widgets`, then `self.status.configure(...)` collecting
   the disk paths / sink / source presence — only for widgets actually drawn,
   honoring bar_items supersession) + `status_tick` (map `sample.mounts` into
   the IPC event, `volume.unwrap_or(-1.0)`, `muted.unwrap_or(false)`,
   `mic_volume.unwrap_or(-1.0)`, `mic_muted.unwrap_or(false)`).

## Pitfall — modern `wpctl` folds mute INTO the Volume line

`wpctl get-volume @DEFAULT_AUDIO_SINK@` does **not** print a separate
`Muted: yes/no` line on current wpctl. When muted it appends a marker to the
volume line itself:

```
$ wpctl get-volume @DEFAULT_AUDIO_SINK@     # muted
Volume: 0.60 [MUTED]
```

This is why a volume widget went BLANK the moment you right-clicked to mute:
`"0.60 [MUTED]".trim().parse::<f64>()` fails → compositor sent `volume: -1`
→ the shell's `if (s.volume >= 0)` guard left the text empty (the widget
"hid"). Fix in `parse_sink`: take the leading number via
`rest.split_whitespace().next()` (discards the `[MUTED]` annotation) and set
`muted = Some(true)` when the line contains `[MUTED]`/`[`. Keep the legacy
`Muted: yes/no` branch for old wpctl. A muted node still reports a real
volume; only the glyph changes. Verify the live format with
`wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle && wpctl get-volume @DEFAULT_AUDIO_SINK@`.

## Perf discipline (this is the house rule)

When NO widgets are configured, the compositor must not pay for them:
`Status::default()` wants neither mounts nor volume, and `wpctl` is only
spawned / mounts only statted when the config asks. A bar with no widgets
stats nothing extra and spawns no subprocess.

## Shell side

- `commands.js` config case: add `applyBarWidgets(message.bar_widgets);`.
- `bar.js`: `applyBarWidgets` (stores list, `renderBars()` + `refreshWeather()`);
  `syncBarWidgets(output)` builds/keeps one element per widget positionally;
  `renderBarWidgets(output)` sets guarded textContent; `renderBarChrome` calls
  `syncBarWidgets`, `renderBarModules` calls `renderBarWidgets`.
- Weather: `refreshWeather()` on config + a 15min interval; geocode via
  `https://geocoding-api.open-meteo.com/v1/search?name=...`, forecast via
  `https://api.open-meteo.com/v1/forecast?latitude=..&longitude=..&current=temperature_2m,weather_code`.
  Cache per lowercased location; mark slot in-flight/failed so the 2s sample
  never starts a duplicate fetch. Map WMO `weather_code` to a short glyph.

## Key pitfall: the shell test-harness DOM stub

`tests/shell.test.js`'s `El` class has `querySelector` (bare `.class`/tag only)
but **NO `querySelectorAll`, and does not parse `:scope > .x`**. Any shell code
that calls `container.querySelectorAll(...)` throws inside `renderBarChrome`
(which runs on every render) and breaks the ENTIRE suite in all three modes —
not just your new test. Do NOT re-query the DOM for widget elements; track them
on the output/record object (e.g. `output.widgetsEls` array, reused
positionally like `syncButtons`, with `filter(Boolean)` compaction). Only use
`document.createElement`, `append`, `dataset`, `.title` — the El stub supports
those (dataset/title are plain mutable props).

To drive a widget test: `emit({type:'config', layout:mode, bar_widgets:[...] })`
AFTER an output exists, then `emit({type:'status.update', ..., mounts:[...],
volume:0.45, muted:false})`, then read `__shell.outputs.get('DP-1').widgetsEls`
textContent. Avoid a `weather` widget in tests (it triggers a real network
fetch from the harness); disk+volume are pure and safe.

## Deploying a widget to the live NixOS host (config-only)

The user's bar entry is set in `/persistent/etc/nixos/home/viewport.nix` under
`xdg.configFile."viewport/config.json".text = builtins.toJSON { ... bar_widgets = [
{ type = "disk"; path = "/games"; } { type = "weather"; location = "Pickering, ON, Canada"; } ]; }`.
A widget needs NO Rust rebuild — the running build already carries it if the flake
is at the feature commit. See SKILL.md "Shipping to the NixOS host → Config-only
change" for the full verify chain: eval the generated JSON, confirm the running
`.viewport-wrapped` ELF + `share/viewport/shell/` subtree carry the strings, and
read the live config back with `viewport msg -t view.query`. For `weather`,
always confirm open-meteo geocodes the `location` string (works for
"City, ON, Canada" → Pickering, Ontario) and returns `current=...` before telling
the user it's live.

**Widgets are interactive — `shell.exec`.** Widgets are DOM on the shell page, so
a pointer over them reaches the DOM already; each widget binds input and sends a
`shell.exec` IPC request the compositor runs via the shared `/bin/sh` spawn a
keybinding's `exec` uses (`crate::input::spawn`). New request wiring (all three
places must agree):
1. `crates/viewport-ipc/src/request.rs` — `ShellExec { command: String }` variant
   (+ parse test, NOT in the C-parity 23-row table, like shell.command).
2. `crates/viewport-ipc/src/lib.rs` — add `"shell.exec"` to `is_known_type`.
3. `crates/viewport/src/msg.rs` — add a `Type` row + bump the
   `the_offered_types_are_the_whole_request_set` TYPES.len (currently 34).
4. `crates/viewport/src/apply.rs` — `Request::ShellExec { command } => crate::input::spawn(&command)`.

Shell behaviour (bar.js `wireWidget`, called once per element at build; handlers
read `el._widget`, set by the sync pass): `volume` and `mic` both wheel=5% steps
and right-click/contextmenu=toggle mute, differing only in which `wpctl` node:
`volume` → `@DEFAULT_AUDIO_SINK@` (`wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+/-`,
deltaY<0 is up; `wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle`), `mic` →
`@DEFAULT_AUDIO_SOURCE@` (set-volume/set-mute on the source instead). `disk`
click=`xdg-open <path>`; `weather` click=`xdg-open` a maps URL for the location.
A module element (bare string in bar_items) has `_widget=null` and sends
nothing. `send()` (state.js)
is where messages leave; the shell test harness captures them in a global `sent`
array via the `webkit.messageHandlers.viewport.postMessage` stub — drive a
listener with `el.listeners.wheel.forEach(fn => fn({preventDefault(){},deltaY}))`
and assert on `sent.filter(m=>m.type==='shell.exec')`. The two audio widgets
render identically in `renderBarWidgets` (glyph + percent) but read different
sample halves: mic uses `mic_volume`/`mic_muted` and the mic glyphs
`volume` uses `volume`/`muted` and `󰕾`/`󰝟`.

## Instant feedback — `status.refresh`

The bar re-samples once per 2s `status.update` tick, so an audio widget that
drives the sink through `wpctl` (wheel=set-volume, contextmenu=set-mute) is
otherwise up to two seconds stale. "Right-click mute doesn't seem to work" is
usually THIS — the mute fired but nothing changed on screen yet, not a broken
`contextmenu` handler (that event fires reliably in CEF). Fix: after the
`shell.exec` command, `wireWidget` sends a `status.refresh` unit request the
compositor answers with `state.status_tick()` (apply.rs), pushing a fresh
sample immediately. Both `volume` and `mic` do `cmd(...); refreshStatus();`
in their wheel and contextmenu handlers. Because the shell test harness is
synchronous, send it synchronously right after the command (no `setTimeout`)
so a test can assert `sent.some(m => m.type === 'status.refresh')` in the same
tick — assert on the message, not on the re-sampled value.

Wiring a unit request (same 3-places rule as shell.exec, NOT in the C-parity
23-row table): `request.rs` adds the unit variant (+ parse test), `lib.rs`
`is_known_type` gains the string, `msg.rs` gains a `Type` row and
`TYPES.len` bumps (currently 35). **Compile gotcha on the parse test**: inside
the request.rs `tests` module, `parse()` returns the **unwrapped `Request`**,
not a `Result` — write `matches!(parse(r#"{"type":"status.refresh"}"#),
Request::StatusRefresh)`, NOT `Ok(Request::StatusRefresh)`. Then
`crates/viewport/src/apply.rs` maps `Request::StatusRefresh => state.status_tick()`.
