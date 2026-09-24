# Tool-Surface Contracts

An app with two tool surfaces (an in-app agent and an MCP server) drifts: a tool lands on one,
the other keeps the old list, and nothing fails. Pin both lists with a test — they are the
contract clients and the model see, and a rename is a breaking change.

## MCP surface: drive the real endpoint

`tools/list` is static registration, so no mailbox or resource has to exist first. The transport
is Streamable HTTP: initialize, send the initialized notification, then list — carrying the
`mcp-session-id` header the initialize response returned. Responses arrive as SSE, so parse the
`data:` lines rather than calling `res.json()`.

```ts
const init = await SELF.fetch("http://example.com/mcp", {
	method: "POST",
	headers: {
		"content-type": "application/json",
		accept: "application/json, text/event-stream",
	},
	body: JSON.stringify({
		jsonrpc: "2.0",
		id: 1,
		method: "initialize",
		params: {
			protocolVersion: "2025-06-18",
			capabilities: {},
			clientInfo: { name: "test", version: "1" },
		},
	}),
});
expect(init.status).toBe(200);
const session = init.headers.get("mcp-session-id") ?? "";
const headers = {
	"content-type": "application/json",
	accept: "application/json, text/event-stream",
	...(session ? { "mcp-session-id": session } : {}),
};
await SELF.fetch("http://example.com/mcp", {
	method: "POST",
	headers,
	body: JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }),
});
const list = await SELF.fetch("http://example.com/mcp", {
	method: "POST",
	headers,
	body: JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/list" }),
});
const messages = (await list.text())
	.split("\n")
	.filter((line) => line.startsWith("data:"))
	.map((line) => JSON.parse(line.slice(5).trim()) as Record<string, unknown>);
const tools =
	(messages[0]?.result as { tools?: { name: string }[] } | undefined)?.tools ?? [];
expect(tools.map((tool) => tool.name).sort()).toEqual(EXPECTED_TOOL_NAMES);
```

Assert the FULL sorted list, not `arrayContaining`: an addition or a rename is the drift you are
guarding against, and editing the constant is then the deliberate act. Do not assert on tool
descriptions — they are prose and churn.

## Agent surface: export the factory

When an agent builds its tools in a factory (`createEmailTools(env, mailboxId | null)`), export
that factory and assert the key set per scope. This covers the mode-dependent surface (a global
chat vs a chat scoped to one resource) without booting a model or a websocket:

```ts
import { createEmailTools } from "../workers/agent/index";

const SCOPED = ["create_rule", "delete_email", /* ... */];
const GLOBAL_ONLY = ["list_mailboxes", "search_all_mailboxes"];

expect(Object.keys(createEmailTools(env, "scoped@example.com")).sort()).toEqual(SCOPED);
expect(Object.keys(createEmailTools(env, null)).sort()).toEqual(
	[...SCOPED, ...GLOBAL_ONLY].sort(),
);
```

Importing the agent module from a test is fine — it is the same module the worker already loads,
and building the tool objects is pure (no DO, no model).

## Keeping the two surfaces honest

- Both surfaces should call the same shared tool implementations, with the deliberate
difference (an agent that drafts but never sends; MCP clients that do both) expressed as two
named constants in one test file.
- The test catches drift after the fact; the grep explains which side is missing it:
  `grep -nE ': defineTool' <agent file>` and `grep -nA3 'this.server.tool(' <mcp file>`.
