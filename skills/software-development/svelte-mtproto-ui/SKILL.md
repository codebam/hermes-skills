---
name: svelte-mtproto-ui
description: Use when building Svelte UI over MTProto manager proxies.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [svelte, mtproto, telegram, media, worker]
    related_skills: [systematic-debugging, test-driven-development]
---

# Svelte MTProto UI Seam

## Overview

Use this skill for Svelte components that display or act on data returned from the Telegram MTProto manager proxy. The UI layer must use wrapper functions and manager APIs, preserve worker-safe values, and lazy-load media rather than letting a render trigger an unbounded download burst.

## When to Use

- Adding or debugging a Svelte chat, picker, inline-bot, media, sticker, or bot UI.
- Rendering records returned by an `app*Manager` proxy.
- A Svelte UI shows result metadata but lacks media previews or fails to send a manager request.

Do not use this for the legacy Solid client unless the change belongs in its shared manager layer.

## Worker Boundary

1. Get MTProto-facing data through a `$lib/telegram/` wrapper and `bootTelegram()`; do not invoke raw API methods from UI code.
2. Hand only plain, structured-cloneable values to Svelte state. A `$state` proxy must never be returned to a worker proxy.
3. Keep raw API objects needed for a later operation in a module-private `Map`, keyed by a stable plain ID. Expose only render metadata and IDs to components.

Completion criterion: the component receives plain presentation data, and any later worker call gets a raw object or fresh manager lookup rather than a Svelte proxy.

## Media Result Previews

Inline results arrive in two useful shapes:

- `botInlineMediaResult`: preview media is `document` or `photo`.
- `botInlineResult`: preview media is normally an image `thumb` web document.

Map enough plain metadata for deterministic rendering (query/result ID, title, description, type, and optional thumbnail identifiers), but retain the raw result in a private map for downloading.

1. Create a small preview component rather than adding download work to a large chat component.
2. Observe the preview element with `IntersectionObserver`; begin the download only when it approaches the viewport.
3. Route the download through the existing bounded `enqueueLoad` queue.
4. Use `appDownloadManager.downloadMediaURL({media, thumb})`; select a bounded photo/document size with `choosePhotoSize` when the media is a photo or document. Web documents download directly without a photo-size argument.
5. Render a text/letter fallback while loading and for result types without preview media.
6. Cache resolved URLs by stable result ID so rerenders do not repeat downloads.

Completion criterion: every visual inline result has a visible fallback immediately, and image-capable results replace it with a thumbnail without downloading offscreen results.

## Reference Implementation Notes

See `references/inline-result-previews.md` for the data shapes and implementation checklist used for Svelte inline-result thumbnails.

## Common Pitfalls

1. **Passing raw results into `$state`.** Nested result objects become reactive proxies and can fail structured cloning when handed back to a manager. Store raw records privately and pass stable IDs instead.
2. **Using only title/description mapping.** This makes media-heavy inline bots look like empty or invisible result panels. Preserve enough media identity to render a preview.
3. **Eagerly downloading every grid item.** A bot can return many documents. Use both viewport observation and the bounded queue.
4. **Downloading a photo without a size.** Select a concrete size via `choosePhotoSize`; an empty size can fail in the download layer.
5. **Making raw MTProto calls from a component.** Extend the manager or wrapper API instead, so peers, caches, and update processing remain consistent.

## Verification Checklist

- [ ] The Svelte component consumes only plain values and stable IDs.
- [ ] Raw result media stays outside `$state` and is never sent through the worker as a proxy.
- [ ] Result previews defer downloading until visible and use `enqueueLoad`.
- [ ] The UI has a visible non-media fallback.
- [ ] A focused mapping test covers media and web-thumbnail result shapes.
- [ ] The Svelte build passes.
- [ ] An authenticated browser run confirms an actual inline bot yields visible previews before reporting the UI fix complete.
