#!/usr/bin/env node
// fsedit.mjs - file editing helper for environments where the agent's file-write/patch
// tools create 0-byte files or fail their post-write verification.
//
// Usage:
//   node fsedit.mjs write <path>                        # content on stdin
//   node fsedit.mjs append <path>                       # content on stdin
//   node fsedit.mjs replace <path> <oldFile> <newFile> [--all]
//   node fsedit.mjs insert-after <path> <anchorFile> <newFile>
//   node fsedit.mjs delete-line <path> <matchFile>
//
// Snippets are read from files so shell quoting never corrupts code.
// Exits 1 (loudly) when an anchor is missing or ambiguous.
import fs from "node:fs";
import path from "node:path";

const argv = process.argv.slice(2);
const mode = argv[0];
const all = argv.includes("--all");
const pos = argv.slice(1).filter((x) => x !== "--all");

function fail(msg) {
  console.error("fsedit: " + msg);
  process.exit(1);
}
function stdin() {
  return fs.readFileSync(0, "utf8");
}
function readSnippet(file) {
  if (!file) fail("missing snippet file");
  if (!fs.existsSync(file)) fail(`snippet file not found: ${file}`);
  return fs.readFileSync(file, "utf8");
}
function countOccurrences(hay, needle) {
  if (!needle) return 0;
  let n = 0,
    i = 0;
  for (;;) {
    const j = hay.indexOf(needle, i);
    if (j === -1) return n;
    n++;
    i = j + needle.length;
  }
}
function report(target, before, after, what) {
  const bl = before.split("\n").length,
    al = after.split("\n").length;
  const ch =
    countOccurrences(before, "\n") === countOccurrences(after, "\n")
      ? "same line count"
      : `lines ${bl} -> ${al}`;
  console.log(`fsedit: ${what} in ${target} (${ch}, ${after.length} bytes)`);
}

if (mode === "write" || mode === "append") {
  const target = pos[0];
  if (!target) fail(`usage: fsedit.mjs ${mode} <path>  (content on stdin)`);
  fs.mkdirSync(path.dirname(path.resolve(target)), { recursive: true });
  const content = stdin();
  if (mode === "append") fs.appendFileSync(target, content);
  else fs.writeFileSync(target, content);
  const size = fs.statSync(target).size;
  if (size === 0) fail(`write produced an empty file: ${target}`);
  console.log(`fsedit: wrote ${target} (${size} bytes)`);
} else if (mode === "replace" || mode === "insert-after" || mode === "delete-line") {
  const target = pos[0];
  const snippet = readSnippet(pos[1]);
  const replacement =
    mode === "replace" ? readSnippet(pos[2]) : mode === "insert-after" ? readSnippet(pos[2]) : "";
  if (!target || !fs.existsSync(target)) fail(`target not found: ${target}`);
  const before = fs.readFileSync(target, "utf8");
  const hits = countOccurrences(before, snippet);
  if (hits === 0) fail(`anchor not found in ${target}: ${JSON.stringify(snippet.slice(0, 80))}`);
  if (hits > 1 && !all)
    fail(`anchor is ambiguous (${hits} matches) in ${target}; add --all or use a longer anchor`);
  let after;
  if (mode === "replace")
    after = all ? before.split(snippet).join(replacement) : before.replace(snippet, () => replacement);
  else if (mode === "insert-after")
    after = all
      ? before.split(snippet).join(snippet + replacement)
      : before.replace(snippet, () => snippet + replacement);
  else after = all ? before.split(snippet).join("") : before.replace(snippet + "\n", "");
  fs.writeFileSync(target, after);
  report(target, before, after, `${mode} x${all ? hits : 1}`);
} else {
  fail(`unknown mode: ${mode || "(none)"}`);
}
