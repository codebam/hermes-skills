#!/usr/bin/env python3
"""Harvest RSS/Atom feeds plus Hacker News into a compact, citation-ready list.

Stdlib only. Each output line carries the feed name, an ISO timestamp, the
title, and the URL -- the URL is included deliberately, because a digest cannot
cite a story it has no link for.

Usage:
    python3 harvest_feeds.py                          # built-in tech feed set
    python3 harvest_feeds.py --feeds-file feeds.txt   # one "Name | URL" per line
    python3 harvest_feeds.py --lookback-hours 48 --max-items 15
    python3 harvest_feeds.py --json                   # machine-readable
    python3 harvest_feeds.py --no-hn                  # skip Hacker News

Feed file format (blank lines and #-comments ignored):
    Ars Technica | https://feeds.arstechnica.com/arstechnica/index
"""

import argparse
import datetime as dt
import email.utils
import json
import re
import ssl
import sys
import urllib.request
import xml.etree.ElementTree as ET

UA = "Mozilla/5.0 (compatible; HermesNewsDigest/1.0)"

DEFAULT_FEEDS = [
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
    ("The Verge", "https://www.theverge.com/rss/index.xml"),
    ("TechCrunch", "https://techcrunch.com/feed/"),
    ("Engadget", "https://www.engadget.com/rss.xml"),
    ("Wired", "https://www.wired.com/feed/rss"),
    ("The Register", "https://www.theregister.com/headlines.atom"),
    ("Techmeme", "https://www.techmeme.com/feed.xml"),
    ("9to5Mac", "https://9to5mac.com/feed/"),
    ("MIT Tech Review", "https://www.technologyreview.com/feed/"),
]

ATOM = {"a": "http://www.w3.org/2005/Atom"}


def opener():
    """Prefer a verifying TLS context; fall back once if the CA store is thin."""
    for ctx in (ssl.create_default_context(),
                ssl._create_unverified_context()):  # noqa: SLF001 - intentional fallback
        yield ctx


def fetch(url, timeout=25):
    last = None
    for ctx in opener():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            return urllib.request.urlopen(req, timeout=timeout, context=ctx).read()
        except Exception as exc:  # try the next context, then give up
            last = exc
    raise last


def strip_tags(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def parse_date(raw):
    """Feeds mix RFC-822 (RSS) and ISO-8601 (Atom). Return aware UTC or None."""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        stamp = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            stamp = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    return stamp.astimezone(dt.timezone.utc)


def feed_entries(name, url, max_items):
    root = ET.fromstring(fetch(url))
    items = root.findall(".//item") or root.findall(".//a:entry", ATOM)
    out = []
    for entry in items[:max_items]:
        title = strip_tags(entry.findtext("title")
                           or entry.findtext("a:title", None, ATOM) or "")
        link = entry.findtext("link")
        if not link:
            node = entry.find("a:link", ATOM)
            link = node.get("href") if node is not None else ""
        when = parse_date(
            entry.findtext("pubDate")
            or entry.findtext("a:updated", None, ATOM)
            or entry.findtext("a:published", None, ATOM)
            or entry.findtext("{http://purl.org/dc/elements/1.1/}date")
        )
        if title and link:
            out.append({"source": name, "title": title,
                        "url": link.strip(), "when": when})
    return out


def hacker_news(limit, lookback_hours):
    base = "https://hacker-news.firebaseio.com/v0"
    ids = json.loads(fetch(f"{base}/topstories.json"))[:limit]
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=120)
    out = []
    for item_id in ids:
        try:
            item = json.loads(fetch(f"{base}/item/{item_id}.json"))
        except Exception:
            continue
        when = dt.datetime.fromtimestamp(item.get("time", 0), dt.timezone.utc)
        if when < cutoff or not item.get("title"):
            continue
        out.append({"source": f"HN {item.get('score', 0)}pts",
                    "title": item["title"],
                    "url": item.get("url") or f"https://news.ycombinator.com/item?id={item_id}",
                    "when": when})
    return out


def load_feeds(path):
    feeds = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "|" not in line:
                print(f"warn: skipping malformed feed line: {line}", file=sys.stderr)
                continue
            name, url = (part.strip() for part in line.split("|", 1))
            feeds.append((name, url))
    return feeds or DEFAULT_FEEDS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feeds-file")
    ap.add_argument("--lookback-hours", type=float, default=36.0)
    ap.add_argument("--max-items", type=int, default=12,
                    help="cap entries read per feed (guards against output truncation)")
    ap.add_argument("--hn-top", type=int, default=18, help="Hacker News top stories to inspect")
    ap.add_argument("--no-hn", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    feeds = load_feeds(args.feeds_file) if args.feeds_file else DEFAULT_FEEDS
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=args.lookback_hours)

    rows, gaps = [], []
    for name, url in feeds:
        try:
            rows.extend(feed_entries(name, url, args.max_items))
        except Exception as exc:
            # A failure means unknown coverage for that source, not "no news".
            gaps.append({"source": name, "url": url, "error": f"{type(exc).__name__}: {exc}"})

    if not args.no_hn:
        try:
            rows.extend(hacker_news(args.hn_top, args.lookback_hours))
        except Exception as exc:
            gaps.append({"source": "Hacker News", "url": "firebaseio", "error": str(exc)})

    undated = [r for r in rows if r["when"] is None]
    fresh = [r for r in rows if r["when"] and r["when"] >= cutoff]
    fresh.sort(key=lambda r: r["when"], reverse=True)

    if args.json:
        print(json.dumps({
            "generated": dt.datetime.now(dt.timezone.utc).isoformat(),
            "lookback_hours": args.lookback_hours,
            "items": [{**r, "when": r["when"].isoformat() if r["when"] else None} for r in fresh],
            "undated": [r["url"] for r in undated],
            "gaps": gaps,
        }, indent=2, ensure_ascii=False))
        return

    for row in fresh[:400]:
        stamp = row["when"].strftime("%Y-%m-%d %H:%M")
        print(f"- [{row['source']}] {stamp} | {row['title']} | {row['url']}")

    print(f"\n# {len(fresh)} item(s) in the last {args.lookback_hours:g}h "
          f"from {len(feeds)} feed(s)"
          + (f"; {len(undated)} undated (unfiltered)" if undated else ""))
    if gaps:
        print("# coverage gaps (retry, or substitute an equivalent source):")
        for gap in gaps:
            print(f"#   {gap['source']}: {gap['error']}")


if __name__ == "__main__":
    main()
