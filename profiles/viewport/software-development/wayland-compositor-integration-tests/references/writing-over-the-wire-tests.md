# Writing over-the-wire tests: recipes and first-run transcripts

Turnkey structure for the three protocol tests added in 2026-08, plus the exact
failures from the first full-suite run and their fixes. The test files live in
`tests/` on `wt/integration-tests` (uncommitted at time of writing): see them for
working code; this file is the "why and how it broke" map.

## Common client skeleton (all three C clients)

- `#define _GNU_SOURCE` FIRST, then `#include <time.h>` (clock_gettime), errno/poll as
  needed. Missing `<time.h>` is a hard compile error under `-std=c11 -Wall -Wextra`.
- Registry `handle_global` binds ONLY the globals needed (compositor+shm only if the client
  maps a window). Bind with the version the server advertises (`wl_registry_bind(..., N)`
  where N = the server's `const VERSION`).
- `wl_display_roundtrip()` once after adding the registry listener, then check the manager
  pointer: NULL → "compositor does not offer X" → exit 2 (protocol-global-missing).
- Deadline dispatch loop (do NOT block on `wl_display_dispatch` forever — the headless
  compositor keeps publishing, and a compositor that never answers must fail the test, not
  hang it):

```c
static int dispatch_until(struct wl_display *display, int timeout_ms) {
    struct timespec start; clock_gettime(CLOCK_MONOTONIC, &start);
    while (true) {
        if (wl_display_dispatch(display) < 0) return -1;
        struct timespec now; clock_gettime(CLOCK_MONOTONIC, &now);
        long el = (now.tv_sec - start.tv_sec) * 1000 + (now.tv_nsec - start.tv_nsec) / 1000000;
        if (el > timeout_ms) return -1;
    }
}
```
Callers check their own flags after it returns (the loop returns on deadline OR first
dispatch error — indistinguishable by design; the flag tells which happened).

## Test 1: foreign-toplevel (client + .test.sh with a paint-client)

- `.test.sh` starts `"$VIEWPORT" --headless --timeout 1`, reads WAYLAND_DISPLAY from the
  log regex `'WAYLAND_DISPLAY=[A-Za-z0-9_-]*'`, starts `paint-client foreign-test ...` in
  background, `sleep 5` (window must map; `foreign_management_state.add` needs the buffer
  commit), then runs the ft client.
- ft client: bind manager v3 (`wl_registry_bind(..., 3)`), ALSO bind `wl_seat` (see NULL
  pitfall in SKILL.md). Wait for `toplevel` handle (listing proof), then:
  - `set_fullscreen(real_output)` / `unset_fullscreen()` / `activate(real_seat)` — accepted,
    NOT asserted for echo (shell never echoes fullscreen);
  - `close()` → paint-client gets `xdg_toplevel.close`, exits → compositor
    `toplevel_destroyed()` → `foreign_management_state.remove(id)` → handle `closed` event.
    Wait ≤5 s for `closed`; that is the observable act.

First-run failure transcript (both errors are instructive):

```
ok   the compositor listed a toplevel
     error marshalling arguments for activate (signature o): null value passed for arg 0
     Error marshalling request for zwlr_foreign_toplevel_handle_v1.activate: Invalid argument
     the compositor did not report the toplevel as closed
```
Cause: `activate(handle, NULL)` — libwayland drops NULL object args at marshal even with
`allow-null="true"` in the XML. The dropped activate/set_fullscreen(NULL) silently wedged
the intended request sequence. Fix: pass real bound `wl_seat`/`wl_output` objects.

## Test 2: output-management (client + .test.sh)

- `.test.sh` identical skeleton; runs the om client with WAYLAND_DISPLAY exported.
- om client: bind manager v4. Manager listener: `head` (store first head), `done(serial)`
  (store serial; 0 is invalid — assert != 0), `finished`. Config listener: `succeeded`,
  `failed`, `cancelled`.
- Round: `create_configuration(serial)` → `enable_head(head)` → `apply()` (or `test()`);
  require `succeeded` within 5 s. Two rounds (apply + test) both pass headlessly because a
  config that only enable_heads an already-enabled head produces no mode change.

This test passed on the first run:

```
ok   advertised a head and done(serial=1)
ok   apply of enable_head succeeded
ok   test of enable_head succeeded
```

## Test 3: ext-workspace (client + .test.sh + python control-socket driver)

- `.test.sh` reads BOTH `'WAYLAND_DISPLAY='` and `'control socket at <path>'` from the log,
  then runs one python block that owns the control socket: connect `AF_UNIX`; `output.query`
  → scan events for `output.layout` → `outputs[0]["name"]` (headless = `HEADLESS-1`);
  send `{"type":"workspace.list","workspaces":[{"id":"1","name":"one","output":<name>,
  "active":true}]}`; `sleep 0.5`; subprocess-run the ws client with
  `env={**os.environ,"WAYLAND_DISPLAY":...}`; then scan events for
  `{"type":"workspace.request","action":"activate","id":"1"}`.
- Reading pattern: the compositor publishes continuously, so never "wait for silence" —
  collect `recv(65536)` chunks until a deadline, split lines, json-parse, match the target
  event (same pattern as `output-order.test.sh`).
- ws client: bind manager v1; listeners `workspace_group`, `workspace`, `done`, `finished`.
  Then `ext_workspace_handle_v1_activate(handle)` + `ext_workspace_manager_v1_commit(manager)`
  + flush, exit 0. The forwarding proof is the control-socket event, not anything the client
  sees.

First-run status: the compositor log proved the pipe worked end-to-end in the server half
(`workspaces: 1 from the shell [1 "one" on HEADLESS-1 active]`); the assertion phase failed
with **no python stderr captured** — the .test.sh only tails the compositor log on failure.
Trap: capture the python heredoc's stderr into a variable and print it, or you will debug
blind.

## Harness gotchas that cost runs

- New `.test.sh` files need `chmod +x` (written 0644 → `Permission denied` in the runner).
- `scripts/integration.sh` wiring: `generate <name> <xml>` produces
  `$work/<name>-client-protocol.h` — the C client's `#include "<name>-client-protocol.h"`
  must match that exact stem. Add the client to the `for client in ...` cc loop AND add a
  `run <name>` line after the existing ones.
- `set -e` in integration.sh: a compile error in ANY client aborts the whole run, not just
  that test — compile all clients or the first failure hides the rest.