#!/usr/bin/env python3
"""Prove what a deployed Cloudflare Worker is actually running.

Fetches the LIVE bundle of the worker through the Cloudflare API and counts
occurrences of each marker string, so "is this feature deployed?" is answered
with the running bytes rather than an assumption. Deploys carry no commit
metadata (Message: -), so marker presence -- a SQL table name, a tool name, a
header string -- is the proof of what is live.

Usage:
    live-worker-markers.py <worker-name> [marker ...]
    live-worker-markers.py - <marker ...>        # name from ./wrangler.jsonc

Auth: the OAuth token wrangler already stored in
~/.config/.wrangler/config/default.toml. Override the account with
CF_ACCOUNT_ID. Endpoint note: plain /content answers 405 for module workers;
/content/v2 is the one that returns the live bundle (multipart, possibly
several MB).

Exit codes: 0 = all markers found, 1 = fetch failed or a marker absent,
2 = usage/auth problem.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib

API = "https://api.cloudflare.com/client/v4"
TOKEN_FILE = "~/.config/.wrangler/config/default.toml"


def curl(url, token, dest=None):
    cmd = ["curl", "-sS", "-m", "120", "-H", f"Authorization: Bearer {token}"]
    if dest:
        cmd += ["-o", dest, "-w", "%{http_code}"]
    cmd.append(url)
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    return out if dest is None else out.strip()


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    worker, markers = argv[0], argv[1:]
    if worker == "-":
        try:
            worker = re.search(r'"name"\s*:\s*"([^"]+)"', open("wrangler.jsonc").read()).group(1)
        except (OSError, AttributeError):
            print("could not read worker name from ./wrangler.jsonc", file=sys.stderr)
            return 2
    token_path = os.path.expanduser(TOKEN_FILE)
    try:
        token = tomllib.load(open(token_path, "rb")).get("oauth_token", "")
    except OSError:
        token = ""
    if not token:
        print(f"no oauth_token in {token_path} (wrangler login there?)", file=sys.stderr)
        return 2

    account = os.environ.get("CF_ACCOUNT_ID")
    if not account:
        result = json.loads(curl(f"{API}/accounts", token)).get("result") or []
        if not result:
            print("could not list accounts; set CF_ACCOUNT_ID", file=sys.stderr)
            return 2
        account = result[0]["id"]

    dest = tempfile.mktemp(suffix=".worker")
    url = f"{API}/accounts/{account}/workers/scripts/{worker}/content/v2"
    status = curl(url, token, dest=dest)
    if status != "200" or not os.path.exists(dest):
        print(f"worker={worker} account={account} http={status}", file=sys.stderr)
        return 1
    data = open(dest, "rb").read()
    print(f"worker={worker} account={account} bytes={len(data)}")
    missing = []
    for marker in markers:
        count = data.count(marker.encode())
        print(f"  {marker}: {count}")
        if count == 0:
            missing.append(marker)
    if missing:
        print(f"MISSING: {', '.join(missing)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
