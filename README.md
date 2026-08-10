# hermes-skills

My own [Hermes agent](https://github.com/NousResearch/hermes-agent) skills, kept
in one place so they are versioned, reviewable, and shared between every profile
on my machines instead of living inside three agent-writable `HERMES_HOME` trees.

## Layout

```
skills/                     # loaded by every profile
  <category>/<name>/SKILL.md
profiles/<profile>/         # loaded only by `hermes -p <profile>`
  <category>/<name>/SKILL.md
```

Both are consumed through Hermes' `skills.external_dirs`, which is read-only:
the agent can read and use these skills but cannot edit them. Anything the agent
writes itself still lands in `HERMES_HOME/skills` and shadows a same-named skill
here.

## Contents

| Skill | Where | What |
| --- | --- | --- |
| `github/git-branch-cleanup` | all | Pruning merged and stale branches |
| `github/reviewing-github-repos` | all | Reading an unfamiliar repo before touching it |
| `nixos/nixos-security-hardening` | all | Hardening a NixOS host |
| `research/polymarket` | all | Polymarket market data |
| `software-development/viewport-compositor` | all | Working on the Viewport Smithay compositor |
| `communication/caveman` | all | Token-compressed output mode |
| `software-development/git-worktree-development` | site | Worktree-per-task workflow |
| `web-development/sveltekit-static-site` | site | SvelteKit static site work |
| `software-development/xwayland-input-debugging` | viewport | Debugging XWayland input |
| `software-development/wayland-xwayland-input-debugging` | viewport | Wayland/XWayland input, wider scope |

## Consuming this from NixOS

The NixOS config does not read this working tree — that would make evaluation
impure. It clones this repo to a fixed path on the host and points
`skills.external_dirs` at that clone:

```
/var/lib/hermes/skills-repo/skills               -> every profile
/var/lib/hermes/skills-repo/profiles/<profile>   -> that profile only
```

A `hermes-skills-sync` systemd unit (daily timer, plus at boot) pulls `origin`
and hard-resets, so the host tracks whatever is on GitHub. The clone is
root-owned and read-only to the agent.

Edit loop: change a skill here, commit, push, then either wait for the timer or
run `run0 systemctl start hermes-skills-sync`.

To lift a skill the agent wrote itself out of its writable tree and into this
repo, use `hermes-skill-promote <category>/<name> [profile]`.

## Attribution

`research/polymarket` started as Nous Research's `optional-skills/finance/polymarket`
(MIT). `communication/caveman` is derived from the caveman Claude Code plugin.
Everything else is mine. MIT, see `LICENSE`.
