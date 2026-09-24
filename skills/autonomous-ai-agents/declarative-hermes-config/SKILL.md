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
Nix keys replace the same keys on disk.

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
   `github:NousResearch/hermes-agent/v<version>`; read that exact revision
   (`references/reading-hermes-source.md` has the fetch-and-grep recipe) and
   take the key from the code, not from docs (docs track main) or memory.
3. **Edit with a why-comment.** House style: comments explain the reason a
   value is pinned, not what it is. One concern per change; do not refactor
   neighbouring settings.
4. **Verify what is verifiable in-session** (next section), then commit with
   a short imperative subject plus a body carrying the reasoning.
5. **Hand off the switch** — activation is the human's call: `nh os switch`
   from the repo root. State plainly what you verified and what you did not.

## Capability wiring (web backends, MCP, memory, secrets)

Same rules, different surfaces: web search/extract backends, MCP servers,
and memory flags are `settings` keys in `home/hermes.nix`; credentials flow
through `desktop/configuration/sops.nix`; fleet-shared services are defined
once in `home/agents.nix` and consumed through a shared import file (pattern:
`home/email-mcp.nix`). Full checklist — secret→`.env` wiring, backend
selection precedence, MCP registration and probing, memory flags and standing
facts: `references/tool-and-service-wiring.md`.

Two shape-deciding rules:

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
  a clean run is real syntax evidence.
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
  what the build actually gates on.
- **`hermes doctor` is the non-interactive status surface** — it prints the
  active web search/extract providers, enabled toolsets, and gated features.
  `hermes tools` refuses non-TTY runs, so unlike `hermes config get <section>`
  it is not usable from an agent session.
- **The full build gate (`nixos-rebuild build`, `osb-work`) may be
  unreachable from the session container** (`osb-work`'s server listens on
  the host loopback). When it is, do not invent a result: report exactly
  what was verified, name the gap, and leave the build to the user's
  `nh os switch` (which builds).

## Pitfalls

- **A file-tool write that reports a post-write verification failure may
  have left the target truncated (0 bytes).** Check the size before
  retrying; if it is gone, `git restore <file>` and apply the edit with a
  script through the terminal (`python3` with exact-string replacements
  assert-guarded), then confirm with `git diff`. Never blind-retry a write
  whose verification failed.
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

## Handoff shape

The expected deliverable is: change committed, the exact switch command, and
one line each on what was verified versus what was not. New sessions pick up
the new default after the switch; say so rather than implying a live change.
