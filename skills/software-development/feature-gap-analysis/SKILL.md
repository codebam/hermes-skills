---
name: feature-gap-analysis
description: Use when asked what features an app is missing or needs.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [product-analysis, roadmap, codebase-recon, evidence, prioritization]
    related_skills: [plan, codebase-inspection, parallel-agent-worktrees]
---

# Feature Gap Analysis

Deliverable: a ranked, evidence-anchored analysis of what a codebase has, what it is missing, and
what to build next — something the user can choose from. Not a wish list, not a paraphrase of the
README.

## Non-negotiables

1. **Read the code, not the docs.** Inventory schema/tables, the route table, tool registries,
   and UI routes/components. The README states intent, the code states truth; where they
   diverge, the divergence is itself a finding worth reporting.
2. **Prove every "missing" claim with a grep and a `file:line` anchor** — for presence and for
   absence. If you did not grep it, write "not verified"; never present an inference as a
   verified absence.
3. **Record the observation time and the commit/branch you read**, so a reader who audits claims
   can re-probe instead of trusting.
4. **Split findings into half-built surfaces and absent features.** Half-built = scaffolding
   exists but nothing wires it up: settings declared and defaulted but never read, helpers never
   called, backend capabilities the UI never reaches, tool parameters the shared schema already
   supports. Those are the cheapest wins and the most persuasive findings — lead with them.
   Never blur the two: "we lack X" and "we have X but a path to it is broken" are different work
   items, and the second usually outranks the first.
5. **Mine demand signals instead of inventing priorities**: the upstream project's issue tracker
   (open/closed counts, labels, feature-request titles), user surveys, and the feature sets of
   established products in the domain. Quote numbers and attribute them.
6. **Every roadmap item names its extension point** — the exact files an implementer would touch.
   An item without an extension point is a wish, not a plan. Tag effort relatively (S/M/L), not
   in invented hours.
7. **State the cross-cutting prerequisites** several items share (migration discipline, test
   harness, background-job mechanism, auth model) so they get built once rather than per feature.
8. **End with open product questions, not assumptions** — the decisions that would change the
   ranking (privacy defaults, single- vs multi-user, delete semantics) belong to the user.
9. **Close with two or three smallest first steps**: independent, user-visible, S-sized.

## Procedure

1. Recon: repo shape, LOC, file map, recent `git log` for direction, remotes (is there an upstream
   to compare against and mine for demand?).
2. Capability inventory by layer — storage, inbound/processing, outbound, UI, API/tools, safety
   gates — each row anchored to files.
3. Grep every candidate gap; keep the anchor that proves absence.
4. Check the upstream tracker and surveys for what users actually ask for.
5. Assemble the document (shape below), save it under `.hermes/plans/` unless asked to commit it,
   and say where it is.
6. Offer the smallest first steps and ask which to start with — do not begin implementing
   unasked.

## Document shape that works

existing-capabilities table (layer | capability | anchor) → reference checklist of what a good
product in this domain does, grounded in at least one external source → gap table
(feature | today | evidence | effort) → damaged/incomplete surfaces → prioritized roadmap
(P0–P3: item | extension point | sketch) → cross-cutting prerequisites → open questions →
suggested first PRs.

## Pitfalls

- **An empty grep is only evidence if the search was broad enough** — search the symbol and its
  synonyms (`snooze`, `scheduled`, `defer`) before declaring a feature absent.
- **Dead config reads as a feature.** A declared-and-defaulted setting that nothing consumes
  looks implemented from the type definitions; trace every setting to a reader.
- **Don't rank by novelty.** The user's stated pain and the tracker's request counts outrank what
  is technically interesting.
- **Guardrails are findings too**: note the safety invariants (verification steps, rate limits,
  send confirmations) that new features are most likely to weaken, and say so in the roadmap.
- Keep the document out of the tracked tree unless asked; `.hermes/plans/` is the default home.
