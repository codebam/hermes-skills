# Tool and service wiring (web backends, MCP, memory, secrets)

Companion to the main skill: where capability changes live, and how each
piece is wired and verified. Names below are for the pinned revision — when
a version bump is the reason for the change, re-confirm them against the
pinned source (`references/reading-hermes-source.md`).

## Where each piece lives

| Change | File |
|---|---|
| Capability keys (`web.*`, `memory.*`, `agent.*`) | `home/hermes.nix` → `settings` |
| MCP servers | `home/hermes.nix` → `mcpServers` (mirrors `config.yaml` → `mcp_servers`) |
| Credentials → `$HERMES_HOME/.env` | `desktop/configuration/sops.nix` → secret declarations + `templates."hermes-env"` |
| Non-secret env (e.g. allowlists) | `home/hermes.nix` → `environment` |
| Fleet-shared service definitions | `home/agents.nix`, extracted into an import file (pattern: `home/email-mcp.nix`) once more than one harness needs it |

## Secrets → .env checklist

A credential sitting in `secrets.yaml` does nothing until all of:

1. Declared under `sops.secrets.<name>` (`owner = "codebam"; group = "users";`).
2. Referenced in the `hermes-env` template as
   `ENV_VAR=${config.sops.placeholder.<name>}`, using the env-var name Hermes
   resolves for that provider (from the pinned source, e.g.
   `plugins/web/tavily/provider.py` → `TAVILY_API_KEY`).
3. Activation copies the template to `$HERMES_HOME/.env` (the module's
   `environmentFiles`).

Verify names only: `cut -d= -f1 ~/.hermes/.env | sort`. Never print values.

## Credential pools: which of several keys serves

A provider with two keys is a pool, and "make Hermes use the other key" is
an ordering change — never a new config key and never a new secret.

- **Discovery order is env-var name order.** The provider plugin declares
  `env_vars`; the pool appends the numbered siblings `VAR_2`, `VAR_3`, … up
  to the first number whose variable does not resolve, seeding them in that
  order with ascending priorities. `fill_first` (the default strategy)
  selects `available[0]`, so `VAR` is tried before `VAR_2`.
- **The lever is which secret holds which slot**: cross the placeholder
  values in the `hermes-env` template — put the second key's placeholder in
  the unnumbered slot. The pool shape and seeding order are untouched, and
  so is every other harness (their wrappers read `/run/secrets/<name>`
  directly; only Hermes reads the template).
- **Say what happens to the other key.** Crossing values leaves the first
  key as the fallback entry; a "that key only" request is a different edit
  (drop the first key from the template). State which shape you shipped
  instead of silently picking one.
- **A swapped value clears stored exhaustion state.** The pool stores a
  token fingerprint and clears the entry's status when the fingerprint
  changes on seeding, so no `hermes auth reset` is needed after the switch
  — prescribing one is wrong.
- **`credential_pool_strategies.<provider>` is a strategy knob, not an
  ordering knob** (`fill_first` / `round_robin` / `least_used` / `random`).
  Priorities are normalized at load for `anthropic` only; for every other
  provider the persisted auth.json order stands, which is why env-name
  order is the initial order. Runtime reordering (`hermes auth priority`)
  writes auth.json — not declarative, so do not reach for it in a flake
  change.
- **Confirm against the pinned source, not the docs**: provider
  `plugins/model-providers/<name>/__init__.py` (`env_vars`),
  `agent/credential_pool.py` (`_env_key_var_candidates`,
  `get_pool_strategy`, `_select_unlocked`, `_upsert_entry`,
  `_normalize_pool_priorities`).
- **A running process keeps its old env.** End the report with the switch,
  then `systemctl --user restart hermes-agent.service` and a Desktop
  relaunch; the pool re-hydrates from `.env` at process start only. Before
  claiming the swap is live, verify file AND process: compare `~/.hermes/.env`
  slots against `/run/secrets/<name>` as equality booleans (never print
  values), and compare the file's mtime with the consumers' start times —
  `systemctl --user show hermes-agent.service -p ExecMainStartTimestamp` and
  the desktop process (`pgrep -a -f hermes-desktop`). File older than the
  commit that changed the template = the switch has not run yet; file newer
  than a consumer = that consumer needs its restart. Do NOT check
  `/proc/<pid>/environ` for these values: it is the exec-time snapshot and
  does not reflect dotenv-loaded vars, so absence there proves nothing.
  `hermes auth list` (run the binary from the unit's `ExecStart` path with
  `HERMES_HOME` set) shows pool entries, seeding order and the active marker —
  structure only, values stay out of view.

## Web search / extract backends

Selection precedence (`agent/web_search_registry.py` docstring):
`web.search_backend` / `web.extract_backend` → `web.backend` → availability
walk → legacy preference → keyless ring (last resort). The capability filter
applies at every step, so a search-only provider can never serve extract.

Facts that decide routing:

- The keyless ring (Exa / Parallel / Firecrawl / Keenable) serves anonymous
  last-resort traffic; logs show it as `<vendor> keyless …`. Seeing it is
  evidence the request fell *past* the configured backends, not evidence of
  what is configured.
- Availability is env-driven: this host exports `SEARXNG_URL` (local SearXNG,
  `http://127.0.0.1:8081`, from `home.nix` sessionVariables), which resolves
  as the search backend without any config key. Pin backends explicitly when
  routing matters.
- Per-capability split is the resilient shape (e.g. local SearXNG for search
  plus a keyed vendor for extract); a single `web.backend` swaps both
  capabilities at once.
- Tavily is built in (`plugins/web/tavily/provider.py`): search + extract,
  `TAVILY_API_KEY` optional (opt-in keyless when selected), keyed tier for a
  real quota.
- Status surfaces: `hermes doctor` prints the active search/extract
  providers; `hermes tools` is interactive-only and refuses non-TTY runs.

## MCP servers

- Config shape: stdio (`command`/`args`/`env`) or HTTP (`url`/`headers`),
  plus `timeout` / `connect_timeout` per server. Tool names become
  `mcp__<server>__<tool>`.
- This revision ignores a server's `InitializeResult.instructions` — when and
  how to use the tools must be rendered into `agent.environment_hint` /
  `agent.coding_instructions` in `hermes.nix`.
- Fleet services run once behind mcp-proxy as systemd user services on
  loopback, and every harness registers the URL rather than spawning its own
  stdio copy — a server that rewrites one file per write (the knowledge graph
  at `~/.local/share/agent-memory/memory.jsonl`, port `7979`) must never get
  a second writer.
- Probe an HTTP endpoint before wiring it — POST `initialize`, then
  `tools/list`, with `Content-Type: application/json` and
  `Accept: application/json, text/event-stream`; stateless servers answer
  without a session.
- Connectivity evidence: `tools.mcp_tool: registered N tool(s) from M
  server(s)` lines in `~/.hermes/logs/agent.log`; a failed server is named
  there with its error, and `~/.hermes/logs/mcp-stderr.log` carries stdio
  bridge stderr.
- The build ships the `mcp` SDK with streamable HTTP; confirm with the
  launcher's interpreter (the store wrapper exports `HERMES_PYTHON`):
  `$HERMES_PYTHON -c "from mcp.client import streamable_http"`.

## Built-ins beat skills for API capabilities

Before writing a skill around an external API, grep the pinned store for a
provider plugin (`plugins/web/`, browser and image-gen providers): Hermes
ships these as first-class backends selected through config keys. A skill
around the same API loses caching, capability routing, keyless rescue, and
`hermes doctor` visibility.

## Memory flags and standing facts

- `memory.memory_enabled` / `memory.user_profile_enabled` gate MEMORY.md /
  USER.md: false means neither injected nor writable, and the memory tool
  goes away. `memory.write_approval` gates writes while keeping injection;
  `memory_char_limit` (default 2200) is the injection budget.
- `agent.environment_hint` is this revision's only always-on system-prompt
  surface reachable from `config.yaml` — the declarative home for standing
  invariants (the email and sandbox policies already live there).
- Recall-on-demand stores (e.g. a knowledge-graph MCP) do not substitute for
  always-in-context facts: a silent recall miss reads as confident wrong
  behaviour. Standing facts → `environment_hint`; durable knowledge → the
  shared graph.