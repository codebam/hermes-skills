# Fixes found landing foreign-toplevel / output-management / ext-workspace wire tests

Verified against the merged `wt/combined` tree (all 8 suite tests green: 5 existing + 3 new).
Three small, easy-to-miss pitfalls beyond what the main SKILL.md already covers.

## 1. A deadline-dispatch loop MUST poll(); a blocking `wl_display_dispatch` hangs on a quiet socket
`wl_display_dispatch(display)` blocks until an event arrives. A "dispatch until timeout" loop
that calls it will block forever once the interesting events have been consumed — the timeout
check is between reads, and a quiet socket never returns from the blocking read. The loop then
never exits (it hangs the whole `.test.sh`, and `timeout 60` eventually kills the python driver
with no output).

Use the poll-based pattern (as `foreign-toplevel-client.c` does):
`wl_display_prepare_read` → `poll(&fds, 1, remain_ms)` → on POLLIN `wl_display_read_events` +
`wl_display_dispatch_pending`, on timeout `wl_display_cancel_read` + return. Returns 0 on
deadline, -1 on connection error; the caller inspects its own flags after.
`#include <poll.h>` and `<errno.h>` (EINTR handling) are required.

## 2. python driver: use `python3 -u` (unbuffered) or its stdout is lost when killed by timeout
When a `.test.sh` pipes the python control-socket driver to a file (`> "$WORK/py.log" 2>&1`),
python's stdout is block-buffered. If `timeout 60 python3 ...` kills a hung driver, the buffer is
never flushed and `py.log` is empty — so you see NOTHING about where it hung. Run
`timeout 60 python3 -u - "$SOCK"` so partial output survives, and `cat "$WORK/py.log"` on the
failure branch to surface the real error (e.g. which subprocess blocked).

## 3. Compositor must run INSIDE the devshell, or it panics on libEGL (false test failure)
Running `tests/*.test.sh` / the compositor binary through plain `bash` (outside `nix develop`)
fails to load `libEGL.so.1` and panics at smithay `backend/egl/ffi.rs`
(`Library::new("libEGL.so.1").expect("Failed to load LibEGL")`). That looks like a workspace/protocol
failure but is purely an environment artifact. Always run the suite and its `.test.sh` via
`nix develop .#rust -c ...`. Diagnosis hint: a Rust panic note (`note: run with RUST_BACKTRACE=1`)
in the compositor log that mentions egl/ffi means this, not your test.

## 4. Build workspaces list over the control socket, not the Wayland socket
The ext-workspace test proves the round trip by sending `workspace.list` JSON over the control
socket, then asserting a `workspace.request` comes BACK on the control socket after a client's
`activate`+`commit`. That request is the observable proof and lives entirely on the control
socket — nothing about the round trip is visible on the Wayland socket itself.
