# Model and reasoning configuration

Sources read from the pinned hermes-agent revision: `hermes_constants.py`
(`resolve_reasoning_config`, `parse_reasoning_effort`), `agent/reasoning_effort.py`
(the ladder and per-provider vocabularies), `agent/reasoning_params.py`,
`plugins/model-providers/`.

## Resolution order

`hermes_constants.resolve_reasoning_config(cfg, model)` is the single
chokepoint for CLI, gateway, TUI, cron, `/model`, fallback activation, ACP,
curator and MoA:

1. `agent.reasoning_overrides` per-model entry (spelling-tolerant: exact id,
   dots/dashes, provider prefix stripped or added; provider-qualified keys
   win).
2. Otherwise `agent.reasoning_effort` (global).

`parse_reasoning_effort` maps a bare string to a config dict: `none`/`false`/
`disabled` → `{enabled: false}`, a value in the ladder → `{enabled: true,
effort: <level>}`, anything else → `None` with a "using default (medium)"
warning. The dict form `{enabled: true, effort: <bespoke>}` passes a
provider-specific tier through verbatim.

**Auxiliary tasks do not read the global.** They resolve effort from
`auxiliary.<task>.reasoning_effort`; when it is unset the task route decides
(profile default, or the request simply goes without). So "max reasoning"
means the main loop, and aux calls stay cheap unless asked otherwise.

## Wire clamping

`agent/reasoning_effort.py` owns the vocabulary math. `EFFORT_LADDER` is
`none, minimal, low, medium, high, xhigh, max, ultra` (`ultra` is
Hermes-internal; no wire accepts it). Each provider/transport declares what
it accepts; a request that is not accepted clamps to the **nearest weaker**
level (never up, never to `none` from an enabled ask), or via a declared
override map. `low`→`high`-only routes, `xhigh`→`max` maps, and tiny
three-level knobs all exist; the exact set lives per provider in that file
and in `plugins/model-providers/<provider>/__init__.py`.

The DeepSeek V4 family over an OpenAI-compatible wire accepts
`low/medium/high/max` with `xhigh` mapping onto `max`, so `max` is the
honest top tier for those routes.

## Model ids on this box

- **opencode-go is a flat namespace**: bare ids only (`deepseek-v4.1-flash`,
  `glm-5.3`, `kimi-k3`); vendor prefixes are stripped before the request
  because the relay rejects `vendor/model` ids. Same for opencode-zen.
- **DeepSeek V4.1 Flash** carries different ids per route: `deepseek-v4.1-flash`
  on opencode-go (the id models.dev and the relay catalog use; vision +
  reasoning, 1M context, 384k output) versus `deepseek-flash` on the direct
  DeepSeek API (which still aliases `deepseek-v4-flash`). Pin the id that
  matches the provider you set.
- **models.dev** (`https://models.dev/api.json`, provider id → models) is the
  fastest way to confirm an id, its modalities, context/output limits and
  the reasoning options a model advertises. Use it before adding a
  `model_overrides` entry — only the ids the catalogs get wrong need one.
- **Credentials**: opencode-go reads `OPENCODE_GO_API_KEY`; a numbered
  `OPENCODE_GO_API_KEY_2` sibling is auto-discovered into the credential
  pool, so a spent subscription rotates mid-session. Provider profiles also
  declare `base_url` (e.g. `https://opencode.ai/zen/go/v1`) — leave
  `model.base_url = ""` so that default wins.

## Checking a route's reasoning behaviour

Provider profiles live in `plugins/model-providers/<name>/` (opencode-go and
opencode-zen are registered from the same `opencode-zen/__init__.py`). A
profile's `build_api_kwargs_extras(reasoning_config, model)` is where the
route decides the wire shape (top-level `reasoning_effort`, a `thinking`
toggle, `extra_body`), and its `default_reasoning_config` is what applies
when the user sets nothing. Grep the profile before promising a level is
accepted — "the model supports reasoning" and "this route sends the effort
you asked for" are different claims.
