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