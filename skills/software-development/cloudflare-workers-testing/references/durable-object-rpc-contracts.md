# Durable Object RPC Contracts in Tests

What decides how a DO test should assert errors, and what those assertions are worth.

## A rejected DO method is reported twice

Awaiting a DO method that throws gives you the rejection — and the pool reports the DO-side
exception a second time as an unhandled rejection, so `vitest run` exits non-zero even though
every test passed. A synchronous throw does not reproduce it, and `runInDurableObject`
reproduces it too, so no choice of call style avoids it.

- Do NOT set `dangerouslyIgnoreUnhandledErrors` — it also hides real unhandled rejections for
  the rest of the suite.
- Assert the HTTP contract instead: drive the request through the worker with `SELF` from
  `cloudflare:test` and check the status and error message the route returns.

```ts
import { SELF } from "cloudflare:test";

const res = await SELF.fetch(`http://example.com/api/v1/mailboxes/${mailbox}/rules`, {
	method: "POST",
	headers: { "content-type": "application/json" },
	body: JSON.stringify(payload),
});
expect(res.status).toBe(400);
expect((await res.json()).error).toMatch(/Unknown folder/);
```

The route needs its prerequisites present first (e.g. the mailbox record in R2) — seed them
with the same call the app makes, not with a mock.

Converting these assertions from stub RPC to the route is also what exposed a real bug: the
route returned 500 for input the DO rejected, because the transported error no longer matched
its `instanceof` guard.

## Errors crossing the RPC boundary lose their class

A thrown error subclass arrives at the caller as a rebuilt `Error`: `instanceof` fails, `name`
is generic, and the original class name survives only as a message prefix
(`RuleValidationError: Unknown folder: ...`). An error-mapping guard written as
`e instanceof MyError || e.name === "MyError"` therefore falls through, and the route answers
500 where it meant 400.

- Match the message prefix as well when mapping transported errors.
- Better: validate at the edge. Run the same validation the DO runs — through a pure helper
  both sides import, so they cannot drift — before the RPC call, so bad input returns 400
  without a round-trip and the suite stays free of DO-side rejections.

## The `agents` framework's `destroy()` needs the DO name first

`destroy()` — the `agents`/partyserver teardown that drops an agent DO's tables, alarms and
storage — fails over RPC with `Attempting to read .name on <Agent> before it was set`. The RPC
path skips the request entry point that hydrates the name from the DO id, and `destroy()` emits
an event that reads it. Set the name explicitly first; `setName` is write-once and takes the
same value the fetch path would have derived (the instance id the stub was created from):

```ts
const stub = env.EMAIL_AGENT.get(env.EMAIL_AGENT.idFromName(mailboxId));
await stub.setName(mailboxId);
await stub.destroy();
```

`destroy()` aborts the DO context, so a later `runInDurableObject` on that stub re-instantiates
a fresh instance — which is exactly how a test proves history is gone: seed a key, destroy, then
read it back as `undefined`.

## Typed Hono variables

When the app types its context as `Context<{ Variables: { stub: X } }>`, a helper that takes
the stub is typed `MyContext["Variables"]["stub"]` — indexing the context type directly
(`MyContext["stub"]`) is a compile error.
