# Restoring a piece the history removed

When the ask is to add something back — a command, a tool, a module, a
setting — the last living version is in git history. Recover it and adapt
it; do not rewrite from scratch. The historical version encodes design
decisions (selection rules, why-comments) that took a review to get right,
and this repo's comments carry that reasoning forward.

## Find the last living version

```
git log --all --oneline -S '<distinctive string>'   # the add and the delete
git log --oneline --follow -- <path>                # the file's full history
```

`-S` reports only commits that changed the number of occurrences, so it
finds the add and the delete but not edits made in between. Take the file
at its last revision before deletion, and when the file was moved before
it died, diff the block between the move commit and the deletion to
confirm the version you extracted is final:

```
diff <(git show <move>:'<path>' | sed -n '/<start marker>/,/<end marker>/p') \
     <(git show <deletion>^:'<path>' | sed -n '/<start marker>/,/<end marker>/p')
```

## Splice it in

Apply the edit with a python script through the terminal, exact-string
anchored and assert-guarded (the same reason as the file-tool-write
pitfall in SKILL.md — a mismatch must abort before writing, not truncate).
Then adapt; a restored block is not a copy-paste:

- Re-point bindings at the current options. Read the pinned source for the
  option path; do not carry the retired module's internals. Worked
  example: the old system module's `stateDir` is now
  `services.hermes-agent.hermesHome` in the upstream home-manager module.
- Rewrite comment sentences that referenced the retired structure (a
  service user that no longer exists, "the block above" that moved), keep
  the why-comments that still hold, and add one line saying where the
  piece came from — history is worth a comment when it explains the code.
- Install where the current layout says: user-level tools belong in the
  home/ file that owns the concern, as `home.packages = lib.optionals
  <gate> [ <pkg> ]`, gated the same way the service they belong to is.

## Verify

`nixfmt --check` will not insert a blank-line separator a splice missed
between the last binding and the inserted block — read the diff for style,
not just the formatter's verdict. Then the SKILL.md verification section
applies; for a shell tool also run the composed-script check, and on the
host shell the osb-work single-package build. Test the restored tool
against a copy of its destination (the scratch-copy pitfall in SKILL.md)
and leave activation to the user's `nh os switch`.
