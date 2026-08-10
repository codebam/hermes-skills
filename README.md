# hermes-skills

Backup of the skills my [Hermes agent](https://github.com/NousResearch/hermes-agent)
wrote for itself.

`HERMES_HOME/skills` is agent-writable by design — Hermes creates and edits
skills as it learns — which makes everything it authors there unbacked state. A
reinstall, an `hermes update`, or one bad edit takes it with it. This repo is
that state, versioned.

Only skills the agent authored are here. Anything Hermes ships upstream, in
`skills/` or `optional-skills/`, is skipped: republishing Nous Research's skill
tree would not be a backup.

## Layout

Mirrors the agent's trees exactly, so a restore is a plain copy back:

```
skills/<category>/<name>/          <- HERMES_HOME/skills/<category>/<name>/
profiles/<profile>/<category>/<name>/  <- HERMES_HOME/profiles/<profile>/skills/<category>/<name>/
```

## Contents

| Skill | Profile | What |
| --- | --- | --- |
| `github/git-branch-cleanup` | default | Pruning merged and stale branches |
| `github/reviewing-github-repos` | default | Reading an unfamiliar repo before touching it |
| `nixos/nixos-security-hardening` | default | Hardening a NixOS host |
| `research/polymarket` | default | Polymarket market data |
| `software-development/viewport-compositor` | default | Working on the Viewport Smithay compositor |
| `caveman` | default | Token-compressed output mode |
| `software-development/git-worktree-development` | site | Worktree-per-task workflow |
| `web-development/sveltekit-static-site` | site | SvelteKit static site work |
| `software-development/xwayland-input-debugging` | viewport | Debugging XWayland input |
| `software-development/wayland-xwayland-input-debugging` | viewport | Wayland/XWayland input, wider scope |

## Taking a backup

`hermes-skills-backup` is on PATH, defined in my NixOS config
(`desktop/configuration/hermes-agent.nix`):

```bash
hermes-skills-backup            # collect, commit, push
hermes-skills-backup --no-push  # collect and commit only
HERMES_SKILLS_REPO=/some/other/checkout hermes-skills-backup
```

It runs as me, not as the `hermes` user, so it pushes with my own git
credentials and no deploy key exists on the host. It never deletes: a skill
removed from `HERMES_HOME` stays here until I `git rm` it deliberately.

The NixOS config does not read this working tree — that would make evaluation
depend on a directory edited between rebuilds. Nothing here is consumed by the
running system; it is a backup, not a source.

## Restoring

```bash
cp -rT skills /var/lib/hermes/.hermes/skills
cp -rT profiles/viewport /var/lib/hermes/.hermes/profiles/viewport/skills
```

## Attribution

`research/polymarket` shares a name with Nous Research's
`optional-skills/finance/polymarket` but its contents diverged. `caveman` is
derived from the caveman Claude Code plugin. MIT, see `LICENSE`.
