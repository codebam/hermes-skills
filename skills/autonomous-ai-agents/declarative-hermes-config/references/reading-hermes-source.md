# Reading the pinned Hermes source

Why: option keys, provider ids, catalogs and effort vocabularies change
between releases, and the docs track `main`, not the pinned tag. Verify
against the revision the flake actually builds.

## Find the pin

`flake.nix` inputs: `hermes-agent.url = "github:NousResearch/hermes-agent/v<version>"`.
The home-manager module used for config lives in that repo at `nix/`
(`homeManagerModules.nix`, `moduleCommon.nix` — the `settings` option and the
generated-config merge are in `moduleCommon.nix`).

## Recipe A — tagged tarball in the container (preferred)

```
cd /tmp
curl -sSL -o ha.tar.gz 'https://codeload.github.com/NousResearch/hermes-agent/tar.gz/refs/tags/v<version>'
mkdir -p ha && tar -xzf ha.tar.gz -C ha && cd ha/hermes-agent-*/
grep -rn 'reasoning_effort' agent/ hermes_constants.py
```

~75 MB download, no rate limit, full tree (including `nix/`, `tests/`, and
`hermes_cli/models_catalog_static.py` with the static per-provider model
lists). Fetch it once per session and grep; do not fetch file by file.

## Recipe B — the /nix/store copy

`ls -d /nix/store/*hermes-agent*` finds installed trees
(`*-hermes-python-source`, `*-source`, the package dirs). They may be older
than the pin — check `pyproject.toml`'s version first. Good enough for stable
internals (`hermes_constants.py`, `agent/reasoning_effort.py`); use Recipe A
for anything the pin bump was about.

## Recipe C — GitHub API via curl

The API is rate-limited unauthenticated (60/hour), so fetch the recursive
tree once and grep paths:

```
curl -sS 'https://api.github.com/repos/NousResearch/hermes-agent/git/trees/v<version>?recursive=1' -o tree.json
python3 -c "import json;d=json.load(open('tree.json'));print([p['path'] for p in d['tree'] if 'opencode' in p['path']])"
```

Then `raw.githubusercontent.com/NousResearch/hermes-agent/v<version>/<path>`
for individual files. Caveat: going through a page-extraction tool can drop
the `?ref=` query and silently serve the default branch — read the API with
`curl` from the container and check the ref in the response.

## What to grep for which question

| Question | Where |
|---|---|
| Config key exists / its exact name | `hermes_constants.py`, `hermes_cli/` |
| Reasoning levels a route accepts | `agent/reasoning_effort.py`, `plugins/model-providers/<name>/__init__.py` |
| Static model list for a provider | `hermes_cli/models_catalog_static.py` |
| Model metadata / capability fallbacks | `agent/models_dev.py`, `agent/model_metadata.py` |
| How the home-manager module renders config | `nix/moduleCommon.nix`, `nix/configMergeScript.nix` |
| State dir / install split | `nix/homeManagerModules.nix` — `services.hermes-agent.hermesHome` is the state directory; `programs.hermes-agent` installs the CLI and desktop |
| Behaviour pinned to a fix (regression detail) | `tests/` — the test name states the contract |
