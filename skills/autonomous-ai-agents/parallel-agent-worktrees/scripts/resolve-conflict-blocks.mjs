#!/usr/bin/env node
// List or resolve the conflict blocks git left in a file.
//
//   node resolve-conflict-blocks.mjs --list <file>
//       Print every conflict block: index, ours, theirs.
//   node resolve-conflict-blocks.mjs <file> <out-file> <plan.mjs>
//       Write <out-file> with each block replaced by its planned resolution.
//
// <plan.mjs> default-exports one entry per block, in file order:
//   null     drop both sides
//   "text"   replace the block with this text (tabs and newlines are fine)
// The write happens only after every check passes: a plan whose length disagrees with
// the file, or any surviving marker, aborts with a non-zero exit and leaves <out-file>
// untouched. Generate plans with JSON.stringify or template literals so tab-indented
// code never has to be retyped.

import fs from "node:fs";
import { pathToFileURL } from "node:url";

const BLOCK = /<<<<<<< [^\n]*\n([\s\S]*?)\n?=======\n([\s\S]*?)\n?>>>>>>> [^\n]*\n/g;

function usage() {
	console.error("usage: resolve-conflict-blocks.mjs --list <file>");
	console.error("       resolve-conflict-blocks.mjs <file> <out-file> <plan.mjs>");
	process.exit(2);
}

const args = process.argv.slice(2);

if (args[0] === "--list") {
	const file = args[1];
	if (!file) usage();
	const source = fs.readFileSync(file, "utf8");
	const blocks = [...source.matchAll(BLOCK)];
	for (const [index, block] of blocks.entries()) {
		console.log(`\n=== block ${index} ===\n--- ours ---\n${block[1]}\n--- theirs ---\n${block[2]}`);
	}
	console.log(`\n${blocks.length} block(s) in ${file}`);
	process.exit(0);
}

const [source, outFile, planPath] = args;
if (!source || !outFile || !planPath) usage();

const { default: plan } = await import(pathToFileURL(planPath).href);
if (!Array.isArray(plan)) {
	console.error(`${planPath}: default export must be an array of resolutions`);
	process.exit(2);
}

const text = fs.readFileSync(source, "utf8");
let seen = 0;
const out = text.replace(BLOCK, () => {
	const resolution = plan[seen++];
	if (resolution === undefined) {
		throw new Error(`plan has no resolution for block ${seen}`);
	}
	if (resolution === null) return "";
	if (typeof resolution !== "string") {
		throw new Error(`resolution ${seen} must be null or a string`);
	}
	return resolution.endsWith("\n") ? resolution : `${resolution}\n`;
});

if (seen !== plan.length) {
	throw new Error(`file has ${seen} conflict block(s) but the plan has ${plan.length}`);
}
if (/^<<<<<<<|^>>>>>>>/m.test(out)) throw new Error("markers remain after resolution");

fs.writeFileSync(outFile, out);
console.log(`resolved ${seen} block(s) -> ${outFile} (${out.length} bytes)`);
