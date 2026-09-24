---
name: hermes-terminal-backend-plugins
description: "Use when building a Hermes terminal-backend plugin."
version: 1.0.0
platforms: [linux, macos]
---

# Hermes terminal backend plugins

Hermes runs shell commands through pluggable terminal backends. Built-ins
(`local`, `docker`, `singularity`, `modal`, `managed_modal`, `daytona`,
`vercel_sandbox`, `ssh`) live under `tools/environments/`; anything else is a
plugin. Sean's OpenSandbox backend (`/persistent/etc/nixos/home/hermes-opensandbox.nix`
+ `home/opensandbox-exec.nix`) is a worked example of everything below.

## Mechanics

- A backend plugin is a DIRECTORY plugin: `plugin.yaml` with `kind: backend`
  plus `__init__.py` defining `register(ctx)` →
  `ctx.register_terminal_environment_provider(provider())`. The ctx method is
  generated from a registration table in `hermes_cli/plugins.py` (~line 1048).
- USER-installed backend plugins load only when listed in `plugins.enabled`
  (config.yaml) — the gate matches the manifest `name` or its path key.
  Bundled backends auto-load. Built-in names are reserved.
- Provider classification attributes (core consults these, not name lists):
  `is_remote`, `is_container`, `skip_container_guards`, `cache_path_base`,
  `strip_env_keys` (stripped from every spawned subprocess — put vendor
  credentials here), `session_isolated_when_nonpersistent`.
- Methods: `is_available()` (cheap, NO network — UI paints call it),
  `check_requirements(config)`, `probe()` → `(ready|needs_setup|unavailable, detail)`,
  `doctor_checks()` → `[(ok, label, detail)]`, `create_environment(*, cwd,
  timeout, task_id, image, container_config, **kwargs)` (must ignore unknown
  kwargs).
- Subclass `tools.environments.base.BaseEnvironment` to inherit the
  login-shell snapshot bootstrap (`_snapshot_timeout`), cwd-marker tracking,
  timeouts, output caps. Implement `_run_bash() -> Popen` (merge stderr into
  stdout) + `cleanup()`. Set `_stdin_mode = "heredoc"` when the transport has
  no stdin. Wrapped command scripts are bash-specific (declare -F, shopt).
- `is_container = False` for backends that expose HOST paths by bind mount:
  `True` makes core sanitize host-looking cwds, flip file-path resolution to
  container semantics, and (via the `skip_container_guards` default) skip
  dangerous-command approvals. File tools dispatch through the backend's
  `execute()`, so the backend fences read/patch/search too.
- Mirror the terminal tool's cwd resolution (fail-soft):
  `from tools.terminal_tool import resolve_task_overrides, get_session_cwd`
  → override cwd → recorded cwd → request cwd → process cwd.
- Dev guide: `website/docs/developer-guide/terminal-environment-plugin.md`.

## Packaging (nix / home-manager)

- `services.hermes-agent.extraPlugins = [ pkg ]` symlinks entries as
  `$HERMES_HOME/plugins/nix-managed-<derivation-name>`; activation ERRORS if
  an entry lacks `plugin.yaml`; duplicate derivation names assert.
- Check without switching (paths only visible once the file is `git add`ed —
  untracked files are invisible to getFlake):
  `nix build --impure --no-link --print-out-paths --expr 'let f = builtins.getFlake (toString /persistent/etc/nixos); hm = f.nixosConfigurations.nixos-desktop.config.home-manager.users.codebam; in builtins.head hm.services.hermes-agent.extraPlugins'`
  and eval the `...home.activationPackage` `activate` script for the
  `nix-managed-` line.
- `pkgs.writers.writePython3Bin` runs flake8: only E501 belongs in
  `flakeIgnore`; fix F401/E203 properly.
- Embedded Python inside nix `''` strings: use double-quoted Python strings;
  a literal `''` or `${` breaks the string — escape `'''`/`''${` or avoid.
  Run a local extraction + `py_compile` on the block before `nix build`.

## Container pitfalls (helper-process backends)

- Debian `/etc/profile` force-resets PATH for root, discarding a PATH passed
  via the container-create env; the login-shell bootstrap then loses the
  mounted toolchain. Fix: write `/etc/profile.d/<nn>-name.sh` re-exporting
  PATH (profile.d is sourced after the reset; snippet filename must match
  run-parts' `^[a-zA-Z0-9_][a-zA-Z0-9._-]*\.sh$`).
- Shell sessions created before a setup change keep the old shape (sandboxes
  are reused by key); `--destroy` the old sandbox to pick up a fix.
- OpenSandbox/execd specifics: per-command server-side timeout =
  `RunCommandOpts.timeout` (timedelta); killed commands surface as
  `CommandExecError` with a negative value → map to rc 124 + a stderr note.
  State (`.id`/`.lock`) lives under `~/.local/state/opensandbox/<namespace>/`,
  flock-serialized; `destroy()` deletes a sandbox.

## Verification workflow

Drive the real provider with the Hermes venv Python instead of trusting the
build: load the built plugin dir via `importlib.util.spec_from_file_location`
(with `submodule_search_locations=[dir]`), then `create_environment()` +
`execute()` against the live server; check container hostname, host-path
write-through, cwd tracking, exit codes, and every fallback mode (default,
strict, bypass).
