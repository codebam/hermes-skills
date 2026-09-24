# Cron runtime environment, script failures, and claim freshness

Companion to the `local-log-digest-jobs` umbrella. The umbrella's Phase 4 says
"verify end-to-end"; this file is the detail behind that step, plus the two
failure modes that survive a green interactive test. Read it before declaring a
collector done, and again before repeating any prior run's claim to the user.

## The runtime environment is not your shell

**Symptom.** The collector runs clean by hand with real data; the first
scheduled fire delivers:

```
## Script Error
Script exited with code 1
stdout:
dsh-task-scan: missing dependency: zstd
```

Nothing in the script changed between those two runs — only the environment did.

**Cause.** Cron executes `script=` with the **gateway process's** environment,
not your interactive shell's PATH. On NixOS that PATH is a /nix/store-only list
(`hermes-agent`, `bash-interactive`, `coreutils`, `git`, `nodejs`, `ripgrep`,
`openssh`, `ffmpeg`, …), which contains **neither**:

- `/run/current-system/sw/bin` → `zstd`, `gawk`, `find`, `sed` invisible
- `/etc/profiles/per-user/<user>/bin` → `jq`, `node` invisible

Note what this does to a symptom: `sort` and `mktemp` still work (they ship with
coreutils, which *is* on that PATH), so a partial failure looks arbitrary. Test
every dependency you rely on, not just the one that errored.

**Fix.** Prepend the system/profile bins at the very top of the collector, before
any `command -v` check — copy `templates/cron-script-prologue.sh`. Do **not**
"fix" it by hardcoding absolute `/nix/store/...` paths: those hashes change on
every rebuild and the script breaks silently later.

**Test it the way cron runs it**, by taking the real environment off the running
gateway rather than guessing at it:

```bash
gpid=$(jq -r .pid ~/.hermes/gateway.pid)               # gateway.pid is JSON
GW_PATH=$(tr '\0' '\n' < /proc/$gpid/environ | sed -n 's/^PATH=//p')
env -i PATH="$GW_PATH" HOME="$HOME" USER="$(id -un)" \
    "$(command -v bash)" ~/.hermes/scripts/<collector>.sh | head -3
```

You can also read any service's real environment instead of simulating it:
`systemctl --user show-environment` (the user manager's PATH, which units
inherit) and `systemctl --user show <unit> -p Environment -p EnvironmentFiles`.
That distinction mattered once — a service's `203/EXEC` was *not* a PATH problem
because the user manager's PATH did include the profile bins, which
`show-environment` proved and a hand-rolled `PATH=/usr/bin:/bin` simulation
would have "confirmed" wrongly. Verify with the runtime's own view of the
environment, not with a plausible-looking substitute.

A collector that has only ever run in your interactive shell has not been
tested.

## A failing pre-run script does not abort the job

A non-zero exit from `script=` does **not** skip the run. The runner injects a
`## Script Error` block (`Script exited with code 1` + stdout) into the job's
prompt, ahead of the prompt text, and the agent runs anyway. In one real fire
the agent then quietly hand-rolled its own scan of the source with a widened cap
and still delivered a digest — so a broken collector can look like a working job
until you read the output file.

Three consequences for how you wire the job:

- **Write the failure contract into the prompt.** Lead with the failure
  *verbatim*, then produce the digest from the source directly. Say that a
  `missing dependency` error is a regression to flag, not a normal state.
- **Forbid the job from editing its own tooling.** "Never edit anything under
  `~/.hermes/` — you are a reporter here, not a fixer." That same fire patched
  the collector to add a PATH fallback and reported it as fixed and verified.
  The patch was correct, but an unattended job mutating the thing that feeds it
  must not be left implicit; read the file and verify the change yourself.
- **Read the delivered run, don't infer it.** Every finished run is written to
  `~/.hermes/cron/output/<job_id>/<timestamp>.md` — the prompt as the agent
  received it (including any injected `## Script Error` block) and its final
  response. That file is the audit record; a job's own summary of itself is a
  self-report.

## Evidence has a timestamp: observed-at is not true-now

Every digest line, and every "verified" in your own report, is scoped to the
moment it was checked. Two ways this bites, both hit the same night:

- **A digest line went stale within minutes.** "Both user services are
  crash-looping, `node_modules` empty → needs `pnpm install`" was false by the
  time it was read: `tsx` was present and working, and `jobscrape.service` had
  recovered on its 16th restart. A crash-looping unit is also *not* the same as a
  broken install — check whether it is flapping-and-recovering
  (`systemctl --user is-active`, `NRestarts`, `ActiveEnterTimestamp`, journal
  tail) before writing a diagnosis, and re-probe a prior run's item before
  repeating it.
- **Historical proof does not license a present-tense claim.** A plugin's steer
  appearing in one session's log proves it was mounted and firing *then*; it does
  not prove it is mounted *now*, and a grep of the current manifests can flatly
  contradict the present tense. Say which one you mean — and when the user
  challenges a claim, restate the evidence *with its timestamp* rather than
  defending the framing.

Prefer one fresh probe over three quoted log lines. When you report a state you
did not re-check, say so.

## Proof-of-life: did the thing actually run?

When the question is "is my plugin/tool/service alive?", the log is evidence —
but only if you read it exactly:

- A **mention** of a name proves nothing. 226 occurrences of
  `thinking-auditor` in one session were mostly the model reading its own
  source and README.
- An **injected message** proves it ran. The decisive check is a `user/message`
  whose `source.kind == "plugin"` and `source.plugin == <the plugin>`, arriving
  via an `agent/inbox/spliced` event:

  ```bash
  zstd -dc -- "$log" | jq -r 'select(.type=="user/message" and .data.source.kind=="plugin")
    | "\(.data.source.plugin) :: \([.data.content[]? | select(.type=="text") | .text] | join(" ") | .[0:120])"'
  ```

  A plugin that is not mounted cannot inject that frame, so a hit proves it was
  live at that timestamp — and says nothing about now.
