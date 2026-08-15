---
name: viewport-compositor-features
description: Plumb Viewport features across config, IPC, CLI, and shell.
version: 1.0.0
author: hermes
license: MIT
metadata:
  hermes:
    tags: [viewport, compositor, config, ipc, cli, feature-plumbing]
    related_skills: [smithay-wayland-protocol-implementation, wayland-compositor-integration-tests]
---

# Viewport compositor feature plumbing (config + IPC + CLI + shell)

## When to Use
- Adding a new configurable feature to the Viewport compositor that should be settable from the config file (`~/.config/viewport/config.json`), the control socket (`viewport msg -t ...`), and the command line (`--flag`).
- The feature is a compositor setting (wallpaper, gaps, border, decoration mode, keyboard layout, bar mode, etc.) — not a Wayland protocol global (see `smithay-wayland-protocol-implementation` for that).
- You need the shell (the web page) to know about the setting via the `config` event.

## File inventory (all must be touched)

| File | What to do |
|------|-----------|
| `crates/viewport/src/config.rs` | Add field to `File` struct. If the field needs validation/parsing, add a helper type (see `BackgroundTerminal`). |
| `crates/viewport/src/state.rs` | (1) Add default in `ViewportState::new`'s `config: Config { ... }` block (~line 955). (2) Forward from `File` to `self.config` in `apply_config()` (~line 5205). `notify_config()` automatically forwards `self.config` as a `Config` event — only the `Config` struct needs the field. |
| `crates/viewport-ipc/src/event.rs` | Add field to the `Config` struct. Use `#[serde(default, skip_serializing_if = "Option::is_none")]` for optional fields so absence omits them (compatible with older shells). Add serialization test. |
| `crates/viewport-ipc/src/request.rs` | If the feature needs runtime IPC: add `Request` variant with `#[serde(rename = "feature.action")]`. Add at least one row to the `every_dispatch_table_entry_parses` test and increment the table-length assertion. |
| `crates/viewport/src/apply.rs` | If the feature has an IPC request: handle the variant. Update `self.config` and call `self.notify_config()` so the shell learns about the change. |
| `crates/viewport/src/main.rs` | Parse the CLI flag after `apply_config()` so the flag wins over the file. Add the flag to the `OPTIONS` table for `--help` and `warn_about_unknown_options`. |
| `crates/viewport/src/msg.rs` | Add entry to `TYPES` table (name + fields + hint). Optionally add examples to `EXAMPLES`. |
| `data/config.example.json` | Add `"_feature": [ "documentation line", ... ]` + `"feature": default_value`. |
| `data/shell/commands.js` | In the `case 'config':` handler, call `applyFeature(message.feature_field)`. |
| `data/shell/windows.js` | Add the `applyFeature(field)` function. Guard against `undefined` so absent/default fields leave things unchanged. |
| `docs/configuration.md` | Add a section documenting the feature with JSON examples and CLI equivalents. |
| `docs/ipc.md` | Update the `config` event row if it changed, and add the new request to the Shell->Compositor table. |

## Flow

```
config.example.json -> config::File -> config::load(path)
                                              |
                                    apply_config(file)     <- CLI flag overrides after this
                                              |
                                    self.config (Config)   <- what notify_config() sends as Event::Config
                                              |
                                    shell's 'config' event handler
                                              |
                                    applyFeature(message.xxx)
```

A runtime IPC request (`WallpaperSet`, `ConfigGaps`, etc.) goes:
```
viewport msg -t feature.action -> Request::FeatureAction -> apply() handler
                                                                |
                                                  self.config.xxx = value
                                                  self.notify_config()   <- same path as config reload
```

## IPC test table

The `every_dispatch_table_entry_parses` test in `request.rs` asserts a count. Each new `Request` variant gets at least one entry row. After adding entries, **increment the count assertion** — the comment explains that this count tracks "the C dispatch table" (parity table) so if your variant has no C counterpart, add a comment and bump the expected number.

## Pitfalls

- **Worktree discipline**: run `cd` explicitly into `.worktrees/<name>/` before editing. `patch` and `write_file` work on whatever the session's cwd is, and if that's the main worktree, your edits land there instead of in the feature branch. After editing, always `git diff main --stat` from inside the worktree to confirm changes are in the right place.
- **`config::File` field is `Option<T>`**: every file field is optional (see `config.rs` module comment). Absence must not reset something a flag or earlier reload set. The `apply_config` method only overwrites `self.config.X` when `file.X` is `Some(...)`.
- **`Event::Config` serialization**: use `#[serde(skip_serializing_if)]` for optional IPC event fields. Absent fields are omitted from the wire JSON, so an older shell that doesn't know about the key keeps working.
- **Config vs Request naming**: config file fields use snake_case (`background_terminal`), IPC message `type` uses dot-notation (`wallpaper.set`, `config.border`).
- **JS shell pattern**: the `apply*` function guards on `wallpaper === undefined`. The config event is also sent on IPC-to-compositor changes (`notify_config()`), so the handler must accept incremental updates gracefully.
- **notify_config reannounces everything**: it sends the whole `self.config` struct — don't add a separate message type for a single-field change.
- **Build verification**: use `nix develop .#rust -c cargo check -p viewport` and `nix develop .#rust -c cargo test -p viewport` (not `cargo` directly; `rustc` is not on PATH outside the devshell).