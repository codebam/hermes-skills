---
name: declarative-hermes-config
description: "Use when changing Hermes Agent config on this host."
version: 1.0.0
metadata:
  hermes:
    tags: [hermes, nixos, home-manager, declarative-config, model, reasoning]
---

# Declarative Hermes config (NixOS flake hosts)

Any request to change how Hermes Agent behaves on this machine — default
model/provider, reasoning effort, toolsets, MCP servers, plugins, gateway,
skin — is a Nix edit in `/persistent/etc/nixos` plus a human-run switch.
`hermes config set` and editing `$HERMES_HOME/config.yaml` by hand are dead
ends: that file is generated from the flake on every activation, and the
Nix keys replace the same keys on disk. When the misbehaviour is a bug
upstream already fixed, the edit is a pin bump: procedure and pitfalls
below.

The repo's `AGENTS.md` carries the hard rules for any change (never
switch/boot/test the system, verify with a build, format and lint, secrets
stay in SOPS). This skill is the Hermes-specific path through them.

## Procedure

1. **Confirm the managed path before editing anything.** `home/hermes.nix`
   holds `services.hermes-agent.settings`; `home/agents.nix` contributes
   `services.hermes-agent.settings.providers`. The `settings` option is a
   free-form attrset (type check is `builtins.isAttrs`, merge is
   `lib.recursiveUpdate` across modules), serialized with `builtins.toJSON`
   and deep-merged into `config.yaml` at activation — keys you set replace
   the same keys on disk, runtime-written keys you did not set survive.
2. **Never guess a key name or model id.** The flake pins
   `github:NousResearch/hermes-agent/<rev>` — a release tag normally, a full
   main commit SHA when a bump carried an upstream fix; read that exact
   revision (`references/reading-hermes-source.md` has the fetch-and-grep
   recipe) and take the key from the code, not from docs (docs track main)
   or memory.
3. **Edit with a why-comment.** House style: comments explain the reason a
   value is pinned, not what it is. One concern per change; do not refactor
   neighbouring settings.
4. **Verify what is verifiable in-session** (next section), then commit with
   a short imperative subject, a body carrying the reasoning, and a closing
   `Verified:` paragraph that names exactly what was checked and what was
   left to the switch (house style across this repo's history). Write the
   message to a file and use `git commit -F <file>`: inside a single-quoted
   `-m '...'` argument an apostrophe typed as `''` closes and reopens the
   string, so the quote vanishes and a body full of possessives needs an
   amend. Commits are GPG-signed (`commit.gpgsign = true`); when the signing
   path is unavailable, an unsigned commit matches existing precedent.
5. **Hand off the switch** — activation is the human's call: `nh os switch`
   from the repo root. State plainly what you verified and what you did not.

**Restoring something the history removed** — a tool, a module, a setting —
is recover-and-adapt, not rewrite: find the last living version in git
(`git log -S`, then `git show <rev>:<path>`), splice it in assert-guarded,
and re-point its bindings at the current options instead of carrying the
retired module's internals. Recipe: `references/restoring-removed-config.md`.

## Upstream bugs: bump the pin, do not patch locally

When the misbehaviour is upstream Hermes — a desktop view, a gateway event,
a transcript read — the fix is a pin bump, not a local patch (the user asks
for exactly that). One input feeds both halves, the agent package and the
desktop package, so one rev moves both.

1. **Pick the rev.** Confirm the fix is on `main` (the tracking issue's state
   and merge date versus the current pin) and take the tip SHA from
   `GET /repos/NousResearch/hermes-agent/commits/main`. Pin the tip *at lock
   time*; main keeps moving, and commits landing while you build are not
   worth a second lock — report the delta instead.
2. **Edit the input to the full SHA** in `flake.nix`
   (`github:NousResearch/hermes-agent/<sha>`; a raw rev is deliberate, and
   `nix flake update` will not drift it), then re-lock only that input:
   `nix flake update hermes-agent`. `git diff flake.lock` must touch only
   that node.
3. **Diff the consumed build surface.** List upstream commits touching `nix/`
   since the old pin (`GET /repos/.../commits?path=nix/&since=<old rev
   date>`); if `nix/desktop.nix` changed, re-check the electron-headers
   workaround in `home/hermes.nix` against it before trusting the bump.
4. **Verify.** All three host toplevels evaluate against the new lock, then
   build both packages in the osb-work sandbox:

   ```
   osb-work run nix --dir /persistent/etc/nixos --timeout 3600 -- nix build --impure --no-link --print-out-paths --extra-experimental-features 'nix-command flakes' --expr 'let f = builtins.getFlake "/workspace"; hm = f.nixosConfigurations.nixos-desktop.config.home-manager.users.codebam; in [ hm.programs.hermes-agent.package hm.programs.hermes-agent.desktop.package ]'
   ```

   The agent half builds end to end there (sources, uv env, package). The
   desktop renderer's `tsc -b` aborts on the sandbox's memory limit (builder
   exit 134, V8 heap OOM — the sandbox has no memory knob): expected, not a
   signal about the pin. Say so and leave the desktop half to the host build
   the switch runs.
5. **Commit as soon as the change is verified, then hand off.** The human
   runs the switch and wants the commit early; extended mechanism analysis
   belongs in the report's caveats or after the handoff, never in front of
   it.
6. **A bump does not heal stored data.** Fixes that change how rows are
   written or flagged leave already-written rows alone (upstream does not
   backfill). Name which existing sessions keep the old broken state and
   offer the repair as a separate step.

Symptom-to-mechanism for transcript rows, the read/display semantics behind
"Result unavailable", and running the pinned desktop code offline:
`references/desktop-transcript-forensics.md`.

## Capability wiring (web backends, MCP, memory, secrets)

Same rules, different surfaces: web search/extract backends, MCP servers,
and memory flags are `settings` keys in `home/hermes.nix`; credentials flow
through `desktop/configuration/sops.nix`; fleet-shared services are defined
once in `home/agents.nix` and consumed through a shared import file (pattern:
`home/email-mcp.nix`). Full checklist — secret→`.env` wiring, backend
selection precedence, MCP registration and probing, memory flags and standing
facts: `references/tool-and-service-wiring.md`.

Three shape-deciding rules:

- **Built-ins beat skills for API capabilities.** Before adding a skill
  around an external API (search, extract, image gen, browser, TTS), grep
  the pinned store's `plugins/` — Hermes ships these as provider plugins
  selected through config keys, and a skill around the same API is a
  redundant worse copy (no caching, no capability routing, no visibility in
  `hermes doctor`).
- **Check the fleet before defining a service twice.** `home/agents.nix`
  registers the other harnesses (opencode, dsh, pi); anything shared — email
  bridge, memory graph, playwright — already has a definition and a naming
  convention there. Hermes renders MCP tools as `mcp__<server>__<tool>`,
  the same shape dsh uses, so guidance text can be shared verbatim.
- **Changing which of a provider's keys Hermes uses is a value swap, not a
  config key.** Numbered env siblings (`VAR_2`, …) seed the credential pool
  in name order and `fill_first` takes the first, so "use the other key"
  means crossing the placeholder values in the `hermes-env` template (the
  pool shape and the other harnesses stay untouched);
  `credential_pool_strategies` picks a rotation strategy, never an order.
  The wiring may already exist from an earlier change — read the template
  comments and `git log -S <secret-name>` before adding anything. Mechanics,
  the fallback-entry choice, and why no `hermes auth reset` is needed:
  `references/tool-and-service-wiring.md`.

## Model and reasoning keys

| Need | Key | Notes |
|---|---|---|
| Startup route | `model.default`, `model.provider`, `model.base_url` | `base_url = ""` clears a stale URL persisted by an earlier default so the provider's built-in endpoint wins. |
| Global effort | `agent.reasoning_effort` | Main loop only; ladder `none/minimal/low/medium/high/xhigh/max/ultra`; unknown value falls back to medium with a warning; `false`/`none`/`disabled` turns thinking off. |
| Per-model effort | `agent.reasoning_overrides.<model-id>` | Beats the global; spelling-tolerant; provider-prefixed keys are the most specific form. |
| Catalog metadata | `model_overrides.<provider>.<model>` | Only for capability data the catalogs get wrong or lack; models.dev and the live model list are consulted first. |

Depth — resolution order, wire clamping per provider, aux-task behaviour,
and the model ids each provider accepts on this box:
`references/model-and-reasoning.md`.

## Verification in-session

- **Format and lint from the host store.** The session container has no Nix
  daemon, but store binaries run:
  `/nix/store/*nixfmt*/bin/nixfmt --check <file>`,
  `/nix/store/*deadnix*/bin/deadnix --fail <file>`,
  `/nix/store/*statix*/bin/statix check <file>`. All three parse the file, so
  a clean run is real syntax evidence. Several nixfmt versions coexist in
  the store — run `--check` on an untouched file first as a control; the
  version that passes there is the one the tree is formatted with.
- **A settings-only change cannot fail option eval** (the type is free-form),
  but a wrong model id or provider still ships a broken default — confirm the
  id against the pinned catalog or `https://models.dev/api.json`.
- **Verify a settings merge with a dirty-tree eval** — evaluation only, no
  build, so it is allowed on a tree the agent just changed:
  `nix eval --impure --json --expr 'let f = builtins.getFlake
  "/persistent/etc/nixos"; in f.nixosConfigurations.nixos-desktop.config
  .home-manager.users.codebam.services.hermes-agent.settings'`. The service
  is a **home-manager** module: `config.services.hermes-agent` does not exist
  at system level (errors `attribute 'hermes-agent' missing`). `systemd.user`
  units live under the same `home-manager.users.<user>` root; the sops
  template stays under system `config.sops.templates."hermes-env"`. The
  rendered JSON shows exactly what lands in config.yaml. **But a selective
  eval is lazy and is not the final gate**: values only forced by the build
  (e.g. a string spliced into an instruction-file derivation, an attribute
  a consumer reads in another module) stay unchecked, and a missing export
  can pass this eval and then fail `nh os switch`. Finish with a full-force
  eval of `...config.system.build.toplevel.drvPath` (~1 min; evaluation and
  instantiation only — no builders run, so it stays within the no-build-on-
  agent-touched-trees rule) — it forces the whole configuration graph and is
  what the build actually gates on. Evaluation needs a writable store: from
  the sandbox container `nix eval` dies with `remounting /nix/store writable:
  Operation not permitted`, so this is a host-shell/`osb-work` gate — when
  neither is reachable, report the eval as not run instead of dressing up
  parse/lint as one.
- **A backend plugin's built Python can be probed byte-exact.** The plugin
  text is a `writeTextFile` derivation input: pull it out with
  `osb-work ... -- base64 -w0 <built>/__init__.py`, diff against a local
  extraction, and/or import the byte-identical copy in the pinned venv
  (`agent.terminal_env_registry.register_provider` plus the real
  `tools.terminal_tool` helpers) to exercise core keying and env semantics
  without a switch. `osb-work start` / `exec` / `stop` keeps one sandbox
  alive when one step's output (a build path) feeds the next.
- **`hermes doctor` is the non-interactive status surface** — it prints the
  active web search/extract providers, enabled toolsets, and gated features.
  `hermes tools` refuses non-TTY runs, so unlike `hermes config get <section>`
  it is not usable from an agent session.
- **The full build gate (`nixos-rebuild build`, `osb-work`) may be
  unreachable from the session container** (`osb-work`'s server listens on
  the host loopback; `osb-work list` still prints the sandbox catalog in the
  container — a static read, no server call — so it never proves
  reachability; probe with a real `run`/`start` and expect
  connection-refused when the server is out of reach). When it is, do not
  invent a result: report exactly what was verified, name the gap, and leave
  the build to the user's `nh os switch` (which builds). When the session
  runs on the host shell (the sandbox-fallback notice), `osb-work` is
  reachable — build just the changed package in the container store and
  compare it with the host eval's `.drvPath`:

  ```
  osb-work run nix --dir /persistent/etc/nixos --timeout 1200 -- nix build --impure --no-link --print-out-paths --extra-experimental-features 'nix-command flakes' --expr 'let f = builtins.getFlake "/workspace"; hm = f.nixosConfigurations.nixos-desktop.config.home-manager.users.codebam; in builtins.head (builtins.filter (x: x.name == "<pkg>") hm.home.packages)'
  ```

  Identical hashes mean the container built exactly the derivation this
  tree pins; the sandbox store is ephemeral, so the successful build —
  whose checkPhase runs `bash -n` + shellcheck for a
  `writeShellApplication` — is the evidence.
- **A `writeShellApplication`'s composed script is readable without a
  build.** Eval the derivation's `.text` (the same flake → `home.packages`
  → filter-by-name expression) — it returns the whole script: shebang,
  `set -o errexit/nounset/pipefail`, the runtimeInputs PATH, then the
  body. `bash -n` plus shellcheck on that text are the build's own
  checkPhase, so they can run before any store build.
- **An env/credential change is live only when the file AND the process agree.**
  `$HERMES_HOME/.env` is written at activation and read at process start, so
  verify by comparing its slots against `/run/secrets/<name>` as equality
  booleans (never print values) and the file's mtime against the consumers'
  start times (`systemctl --user show hermes-agent.service -p
  ExecMainStartTimestamp`; the desktop process). File older than the commit that
  changed the template = the switch has not run; file newer than a consumer =
  restart it. Never check `/proc/<pid>/environ` for these values — it is the
  exec-time snapshot, and Hermes loads `.env` in-process (dotenv), so they never
  appear there; `hermes auth list` shows the pool's structure/order only, not
  values. Recipe: `references/tool-and-service-wiring.md`.

## Pitfalls

- **A file-tool write that reports a post-write verification failure may
  have left the target truncated (0 bytes).** On this backend that was a
  bug, not a boundary: the sandbox transport embedded stdin as a heredoc
  the writer never received. `1c251f6` fixes it — the payload is staged
  through the container files API and the command runs with `< file`.
  Its sibling `43b8d84` fixes the READ side: the executor appended a
  newline to every output event, and this SDK already sends blank lines
  with theirs, so every blank line in command output appeared twice —
  `read_file`/`search_files` returned inflated content and shifting line
  numbers, and `patch` baked its doubled view into files while reporting
  "the patch did not persist" (the edit had in fact landed). Until both
  commits are switched in, treat tool-reported file state as suspect:
  settle sizes and content with `awk` / `sed -n l` / `git diff` in the
  container, never blind-retry a failed write, and `git restore` a
  zero-byte target. After the switch the tools are byte-exact and a hash
  failure is a genuine error.
- **`web_extract` on `api.github.com` can drop the `?ref=<tag>` query and
  serve the default branch** — the returned URLs say `ref=main`. A listing
  from main can show files that do not exist at the pinned tag. Use `curl`
  from the container plus `python3/json` to read the API, and check the ref
  you actually got.
- **`/nix/store` copies of the Hermes source may lag the flake pin** (old
  versions sit alongside new ones). Check the version in `pyproject.toml`
  before trusting a copy, and prefer the tagged tarball for anything that
  changed recently.
- **Setting the global effort is a fleet-wide decision, not a per-model
  one.** It applies to the main loop on every route (each route clamps onto
  the levels it accepts) and to fallbacks; auxiliary tasks keep their own
  per-task effort. They are separate keys — pick deliberately.
- **A committed config change does not touch running sessions.** Open
  chats, including a desktop tab, keep their session model until reset or
  replaced by a new session.
- **Native memory is off on this host by design.** The always-on facts live
  in `home/hermes.nix` (`agent.environment_hint` / `coding_instructions`),
  durable facts in the shared agent-memory graph (`home/agent-memory.nix`;
  `mcp__memory__*` tools registered via `services.hermes-agent.mcpServers`).
  New sessions do not load `MEMORY.md` / `USER.md` — edit the standing-facts
  block for always-on changes instead of writing memory files.
- **A plugin terminal backend that mounts a workspace must be
  session-isolated.** Core keys the container cache by the ambient session
  context (`tools.terminal_tool._resolve_container_task_id` ->
  `_current_session_key()`), and a dispatching turn that lacks it collapses
  to the shared `"default"` slot — a session then runs its commands in
  another workspace's container ("the container has the wrong repo
  mounted"). The lever is plugin-side, not a core patch: declare
  `session_isolated_when_nonpersistent` on the provider and set
  `terminal.container_persistent: false`; core keys by the explicit
  per-turn task id, containers go one-per-session, the env's
  `_session_scoped` marker (docker's precedent) keeps the per-turn teardown
  from reaping them, and `terminal.lifetime_seconds` decides the
  idle-destroy window (session close destroys immediately). Live shape:
  `home/hermes-opensandbox.nix` + `home/hermes.nix`.
- **An empty capability key in generated `config.yaml` is not absence.**
  Selection falls through the availability walk next, and env vars count:
  this host exports `SEARXNG_URL` via `home.nix` sessionVariables, so the
  self-hosted SearXNG is the live search backend with no `web.*_backend` key
  set. State current routing from `hermes doctor` and the per-call provider
  lines in `~/.hermes/logs/agent.log`, never from the empty key.
- **A key that exists in `secrets.yaml` is not wired.** It must be declared
  under `sops.secrets.<name>` and referenced in the `hermes-env` template by
  the env-var name Hermes actually resolves (read the name from the pinned
  source). Verify the live file by listing names only —
  `cut -d= -f1 ~/.hermes/.env` — never print values.
- **Test a tool that writes or pushes against a throwaway copy of its
  destination.** Copy the destination (a work tree, a repo), strip the
  remote (`git remote remove origin`), run the tool with its override
  pointed at the copy and `--no-push` where offered, and confirm the real
  destination is untouched (`git status`) before reporting. A test run of
  a backup tool must not be able to reach the real repository.

## Handoff shape

The expected deliverable is: change committed, the exact switch command, and
one line each on what was verified versus what was not. New sessions pick up
the new default after the switch; say so rather than implying a live change.
