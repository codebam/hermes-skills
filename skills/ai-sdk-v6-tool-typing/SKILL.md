---
name: ai-sdk-v6-tool-typing
description: Use when typing AI SDK v6 tools or zod tool schemas.
---

# Typing AI SDK v6 tool sets

## Widen the tool set to `ToolSet` where the SDK consumes it

`streamText` / `generateText` infer `TOOLS` from the concrete tools object, and
`StreamTextOnFinishCallback<ToolSet>` (what `AIChatAgent.onChatMessage` receives and
must forward to `streamText`) is NOT assignable to the callback instantiated with a
concrete tool record: `StepResult<ConcreteTools>` -> `StepResult<ToolSet>` fails
because the `ToolSet` member carries `input: never`.

Fix: annotate the consumption site `const tools: ToolSet = buildTools(...)`. The
builder keeps full per-tool typing (generic over `z.ZodTypeAny` so `z.infer<S>` types
each `execute` arg); only the call site is widened. Then `onFinish` passes through
unchanged and `result.steps[].toolResults[].output` is readable - assign it to
`const output: unknown` first (`any -> unknown` is allowed by no-unsafe-assignment).

Do not narrow the callback parameter to the concrete tool record instead: the
override/assignment check is bivariant and both directions fail on `input: never`.

## zod v3: a shape entry typed as an optional property degrades that key to `unknown`

`const field: { mailboxId?: z.ZodString } = cond ? { mailboxId: z.string() } : {};`
then `z.object({ ...field, other: z.string() })` -> `z.infer` gives
`{ other: string; mailboxId: unknown }` (only that key). Cause: `objectOutputType`
maps `Shape[k]["_output"]`; an optional key adds `| undefined`, and that lookup is an
error suppressed by `skipLibCheck`, so the key collapses to `unknown`.

Fixes that work:
- Keep the optional-field annotation (so the key survives in the params type) and
  narrow the value once at the boundary that consumes it, e.g. a resolver that does
  `typeof x === "string" ? x : undefined`. One site, no per-tool noise.
- Or declare each tool's input type explicitly and take the schema as `z.ZodTypeAny`
  (loses the schema -> type link).

Do not bother trying: `z.ZodType<string>` values, `as` casts of the field object,
`{ k?: never }` fixed-mode branches, or `z.object<ExplicitShape>(...)` - all still hit
the `| undefined` lookup. Do not spread a union of shapes (`cond ? {a} : {}`) either:
that degrades every key.

## Workers `request.json()` needs no assertion

`Request.json<T>(): Promise<T>` infers from the variable annotation:
`const body: MyPayload = await request.json();` - and no-unnecessary-type-assertion
flags the `await request.json() as MyPayload` spelling, so use the annotation.

## Keep `AIChatAgent<Env>` generic typed

`AIChatAgent<Env extends Cloudflare.Env>`: pass the project `Env` (which extends
`Cloudflare.Env`) rather than `any` - `this.env` is then typed, `this.env as Env`
casts become unnecessary assertions, and no safety is lost.
