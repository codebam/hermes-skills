---
name: nixos-news-digest
description: "Weekly NixOS news digest: sources, queries, quirks."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [nixos, nix, news, digest, rss, cron, research]
---

# NixOS weekly news digest

Builds Sean's Monday 8:00 AM NixOS digest from a fixed, verified source set. Driven by the
Hermes cron job **`weekly NixOS news digest`** with `~/.hermes/scripts/nixos-news-collect.sh`
as its pre-run script (its stdout arrives in the prompt).

## When to Use

- The cron job `weekly NixOS news digest` fires — the normal path.
- Sean asks "any NixOS news?", "what happened in nixpkgs this week?", or wants the source
  set widened/narrowed (then edit the script, not the prompt).
- A digest arrives with a stale/wrong item — fix the collector or a note here, don't hand-patch.

Not for: general tech news (use `multi-source-news-digest`), or a single lookup (just fetch it).

## Source set (verified 2026-09-17; all returned HTTP 200)

| Source | Endpoint | Role |
|---|---|---|
| Discourse announcements | `discourse.nixos.org/c/announcements/8.json?order=created` | primary news (tools, releases, foundation) |
| Discourse events | `discourse.nixos.org/c/events/13.json?order=created` | meetups, NixCon |
| Discourse weekly top | `discourse.nixos.org/top.json?period=weekly` | community signal (`like_count`, `views`, `posts_count`) |
| Topic excerpts | `discourse.nixos.org/t/<id>.json` → `post_stream.posts[0].cooked` | real content, not headlines |
| nixos.org blog | `nixos.org/blog/announcements-rss.xml` (also `/newsletters-rss.xml`, `/stories-rss.xml`, `/feed.xml`) | official announcements; feed is quiet |
| nixpkgs advisories | `api.github.com/repos/NixOS/nixpkgs/security-advisories` | security; unauthenticated OK |
| Nix versions | `api.github.com/repos/NixOS/nix/tags` | **tags are the versioning — the releases API is empty** |
| Release branches | `api.github.com/repos/NixOS/nixpkgs/git/matching-refs/heads/nixos-` | current stable/unstable |
| RFCs | `api.github.com/repos/NixOS/rfcs/pulls?state=closed&sort=updated&direction=desc` | governance landings |
| Hacker News | `hn.algolia.com/api/v1/search_by_date?query=NixOS&tags=story&restrictSearchableAttributes=title,url&numericFilters=created_at_i>{epoch}` | dev-relevant discussion |
| r/NixOS | `reddit.com/r/NixOS/new.rss` | best-effort; 429s often |

## Dead / unreliable sources — do not cite

- **`weekly.nixos.org` is dead.** The feed (`/feeds/all.rss.xml`) still resolves and looks
  alive, but the last issue is **#05, June 2021**. Never present it as current news.
- **Discourse `latest.rss` is not news.** It is dominated by support threads. News lives in
  the announcements category and the weekly top list.
- **`nixos.org/security/` is 404.** Advisories come from the GitHub security-advisories API.
- **The GitHub API is unauthenticated here** (no token in env or `~/.hermes/.env`): 60 calls/hr.
  The collector uses ~6 and prints the remaining budget; when it runs out, sections go missing
  and appear as coverage gaps — report the gap, never "no news".
- **r/NixOS rate-limits hard** (429) — retry with a UA, or accept the gap.

## Digest shape

Group by what changed, newest first; bold lede per item, then the evidence, then a link:

1. **Headline** — the single most consequential item of the week (often governance/release).
2. **Governance & foundation** — RFCs merged, team changes, funding.
3. **Releases & core** — 26.11 timeline, Nix tag bumps, dynamic derivations.
4. **Ecosystem & tooling** — new flakes/tools from announcements (with one-line what-it-does).
5. **Security** — advisories in the window; if none, say "none since <date>" (a quiet window
   is information, not an all-clear).
6. **Events** — NixCon/meetups with dates.
7. **Coverage gaps** — explicitly list any source that failed.
8. Sources with numbered links at the end (`https://` stripped for chat).

Keep it under ~2500 characters. With `continuity: true`, mark items that repeat from last
week's digest as still-open/carried-over rather than re-announcing them.

## Pitfalls

- **Don't upgrade sponsorship into authorship.** The cargo-dyndrv post reads "Obsidian Systems,
  supported by Saronic, decided to bridge this gap" — the first digest rendered that as
  "Built with Saronic", which credits a funder as a co-author. Keep "supported by" as
  "supported by"; funding relationships in this ecosystem are frequently newsworthy precisely
  because they are relationships, not code contributions.
- **Atom needs its namespace.** `root.findall(".//entry")` returns nothing on r/NixOS; use
  `{http://www.w3.org/2005/Atom}entry`. A bare findall silently yields "no items" — a false
  negative that looks like "no news".
- **Lightweight tags break the tag-date lookup.** `NixOS/nix` tags point straight at commits,
  so `/git/tags/<sha>` 404s; fall back to `/commits/<sha>`. (Releases API is empty for this repo.)
- **Algolia matches story text, not titles.** Without
  `restrictSearchableAttributes=title,url`, "NixOS" pulls in unrelated stories that merely
  mention it in comments.
- **Parse dates, never string-match them.** Discourse is ISO-UTC; the blog feed is RFC-822 GMT;
  HN/Reddit differ again.
- **A headline is not a source.** Fetch the topic (`/t/<id>.json`) before citing content; the
  collector pre-fetches excerpts for the items most likely to be cited.

## Verify an edit

```bash
bash -n ~/.hermes/scripts/nixos-news-collect.sh
bash ~/.hermes/scripts/nixos-news-collect.sh | head -40
# cron condition (gateway PATH has no curl/jq/python in it):
env -i PATH="$(tr '\0' '\n' < /proc/$(python3 -c 'import json;print(json.load(open("/home/codebam/.hermes/gateway.pid"))["pid"])')/environ | sed -n 's/^PATH=//p')" \
  HOME=$HOME USER=$USER bash ~/.hermes/scripts/nixos-news-collect.sh | head -5
```
