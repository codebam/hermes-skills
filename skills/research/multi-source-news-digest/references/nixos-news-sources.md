# NixOS ecosystem news sources (verified 2026-09)

Companion to the feed list. NixOS "news" is thin and lopsided: official
announcements are sparse, and most activity lands on **Discourse**, not in any
newsletter. Harvest the discourse API, not just RSS.

## Source map

| Source | Endpoint | Status / notes |
|---|---|---|
| nixos.org blog | `/blog/feed.xml`, `/blog/announcements-rss.xml`, `/blog/newsletters-rss.xml`, `/blog/stories-rss.xml` | Real RSS 2.0 (`<item>` + `<pubDate>`). Discovered from the `<link>` tags on `/blog/` — the obvious `/blog/rss.xml` and `/feed.xml` are **404**. |
| nixos.org announcements | same feed, announcements variant | Sparse: the official release/news channel. Expect a handful of items per *year*. |
| Discourse (all) | `discourse.nixos.org/latest.rss` | Mostly support questions — poor signal for news, good for "what are people hitting". |
| Discourse (announcements) | `/c/announcements/8.json?order=created` | **The best news source.** `order=created` beats `latest`, which mixes pinned/old topics in. |
| Discourse (topic body) | `/t/<slug>/<id>.json` → `.post_stream.posts[0].cooked` | Strip tags for an excerpt; check `.posts_count` to spot threads with pushback. |
| Discourse (events) | `/c/events/13.json?order=created` | Meetups, NixCon logistics. |
| Security advisories | `api.github.com/repos/NixOS/nixpkgs/security-advisories` | No `nixos.org/security/` page (**404**). This API is the advisories source; `html_url` is the citable page. |
| Nix releases | `api.github.com/repos/NixOS/nix/tags` | `/releases` returns `[]` — Nix does not use GitHub releases. Versioning lives in tags; get a tag date from `/git/refs/tags/<tag>` then `/git/tags/<sha>` (`.tagger.date`). |
| nixpkgs release branches | `api.github.com/repos/NixOS/nixpkgs/git/matching-refs/heads/nixos-` | Current stable + `nixos-unstable`; tells you the release lineage without guessing. |
| nixpkgs churn | `/repos/NixOS/nixpkgs/commits?per_page=N` | Not news, but a recency signal for "is the repo alive". |
| RFCs | `api.github.com/repos/NixOS/rfcs/pulls?state=closed&sort=updated` | `.merged_at != null` = landed. Governance changes surface here before any blog post. |
| r/NixOS | `reddit.com/r/NixOS/new.rss` | Needs a descriptive UA; **429s on rapid repeats** — pause ~10-15s and retry, the retry succeeds. |
| Hacker News | `hn.algolia.com/api/v1/search_by_date?query=NixOS&tags=story` | Better than the firebase top-stories API for a niche domain: it returns community-relevant posts that never reach a news desk. |

## Discourse category ids are not the defaults

Verified by `GET /categories.json` (Guides 15, Help 9, Development 14,
**Announcements 8**, Events 13, Links 12, Meta 53, Jobs 23). Guessed ids for a
"security" or "news" category both returned **404** — read the categories list
once instead of guessing ids from other Discourse instances.

## A 200 is not a live feed

`weekly.nixos.org/feeds/all.rss.xml` resolves, parses, and carries 50 items —
the newest is **#05, June 2021**. The site itself returns 200. Sort the feed and
check the newest `pubDate` before treating a source as covered, and say
"Dormant since <date>" rather than silently listing nothing for it.

## Cross-checks worth running before delivering

- **Sweep every URL you intend to cite** for a real status, in one loop:
  `curl -sS -m 25 -A "$UA" -o /dev/null -w '%{http_code}' -L "$u"`. A headline
  in a feed dump is not a source, and a 404 mid-digest costs the reader's trust.
- **Separate the versioning facts from the news.** "Current stable / next
  release" comes from announcement + ref checks, not from a blog's silence.
- **Name the gaps.** "Official blog has nothing newer than <date>", "advisory
  API is quiet since <date>", "Discourse is where the recent items are" is more
  useful than implying full coverage.
