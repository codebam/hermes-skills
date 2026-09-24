# Tech feed list and per-source notes

Verified working by direct fetch. Feed URLs are stable anchors; the *volume* and
*reliability* notes come from real harvest runs and are worth knowing before a
digest run so you can size the passes and interpret gaps.

## Feed set by section

Paste any subset into a `--feeds-file` (format: `Name | URL`).

**General tech / industry**

| Source | Feed | Notes |
|---|---|---|
| Ars Technica | `https://feeds.arstechnica.com/arstechnica/index` | ~20 items, RFC-822 dates, strong on policy + security. Also has section feeds (`/technology-lab`, `/gadgets`, ...) |
| The Verge | `https://www.theverge.com/rss/index.xml` | Atom. Per-section: `/rss/tech/index.xml`, `/rss/ai-artificial-intelligence/index.xml` |
| TechCrunch | `https://techcrunch.com/feed/` | RSS; dates run ahead in UTC — parse, don't string-match |
| Engadget | `https://www.engadget.com/rss.xml` | ~20 items, consumer-heavy |
| Wired | `https://www.wired.com/feed/rss` | ~10 items, review + features bias |
| The Register | `https://www.theregister.com/headlines.atom` | Atom. Terse, dated the same day in +0200 — good EU-side coverage |
| Techmeme | `https://www.techmeme.com/feed.xml` | Aggregator: best duplicate detector for the day's industry stories |
| MIT Tech Review | `https://www.technologyreview.com/feed/` | ~10 items, analysis over breaking news |

**Consumer electronics**

| Source | Feed | Notes |
|---|---|---|
| 9to5Mac | `https://9to5mac.com/feed/` | High-volume Apple/OS beta coverage |
| Wired / Engadget / Verge | *(above)* | All three review consumer hardware on launch day |

**Programming / dev**

News feeds under-serve this section — those stories are strongest on Hacker
News and vendor engineering blogs, not on general tech desks. Pull the
programming section from the HN API rather than from more RSS feeds:

- `https://hacker-news.firebaseio.com/v0/topstories.json` → array of item ids
- `https://hacker-news.firebaseio.com/v0/item/<id>.json` → `title`, `url`,
  `score`, `descendants` (comments), `time` (unix seconds, UTC)

Score + comment count is the ranking signal; the `url` field is usually a
project page, blog post, or paper — directly citable. A story with hundreds of
points and no big-outlet coverage is exactly what this section should surface.

## Quirks seen in practice

- **Feed formats are mixed.** Ars/TechCrunch/Engadget/Wired/9to5Mac are RSS
  (`item` + `pubDate`), Verge/Register are Atom (`entry` + `updated`). Parse
  both; `scripts/harvest_feeds.py` does.
- **Item counts vary 10–20.** Cap per feed when printing (`--max-items`) or a
  ten-feed run overflows tool output and gets truncated — which silently drops
  whole sources from the digest.
- **Individual sources fail per run.** Bot filters (HTTP 403) and rate limits
  (HTTP 429) hit single feeds on single runs while the rest succeed; the same
  URL often works minutes later. Treat it as a coverage gap, retry with a pause,
  or substitute an equivalent outlet. Never conclude a source is unusable.
- **Section feeds exist when you need narrower scope.** Most publishers expose
  `/rss/<section>/index.xml` (Verge-family) or `/category/<x>/feed/`
  (WordPress-family, e.g. TechCrunch, VentureBeat).
- **The same event lands on 4–6 sources.** Use Techmeme to spot the dupes
  before drafting, then keep the most substantive write-up plus one independent
  corroboration.

## Ranking a story into the digest

1. Does it fit a section the user named? (drop otherwise, no matter how big)
2. Is it from the lookback window, from a *parsed* timestamp?
3. Is it the best write-up of its event, or a duplicate?
4. Does it change something — a release, price, policy, outage, breach,
   benchmark — rather than restating background?

Anything you can't fetch and cite gets dropped or explicitly marked
`[unverified]`; a headline alone is not a source.
