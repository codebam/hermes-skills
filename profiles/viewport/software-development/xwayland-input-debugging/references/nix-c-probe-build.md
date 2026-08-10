# Compiling a C instrument/probe against the NixOS store X11 headers

On NixOS (nixpkgs, immutable store), headers live in `-dev` outputs and the
runtime libs in the plain output. `pkg-config` often isn't on PATH and the
include dirs aren't exposed, so compile against store paths directly.

## One-liner that worked (xiprobe.c / grabprobe.c on NixOS desktop)

```sh
# Resolve the dev/runtime store dirs (adjust to your kernel if versions differ;
# the store paths are stable once present in the closure).
PROTO=$(ls -d /nix/store/*xorgproto*/include/X11/X.h | head -1 | sed 's|/X11/X.h||')
LIBX11DEV=$(ls -d /nix/store/*libx11-*dev*/ | head -1)
LIBX11RUN=$(ls -d /nix/store/*libx11-*/ | head -1)   # runtime output
XIDEV=$(ls -d /nix/store/*libxi-*dev*/ | head -1)
XIRUN=$(ls -d /nix/store/*libxi-*/ | head -1)
XEXTDEV=$(ls -d /nix/store/*libxext-*dev*/ | head -1)
XFIXDEV=$(ls -d /nix/store/*libxfixes-*dev*/ | head -1)

nix shell nixpkgs#gcc -c sh -c \
  "gcc -I$PROTO -I$LIBX11DEV/include -I$XIDEV/include -I$XEXTDEV/include -I$XFIXDEV/include \
       xiprobe.c -o xiprobe -lm -L$LIBX11RUN/lib -lX11 -L$XIRUN/lib -lXi"

# grabprobe only needs libX11:
nix shell nixpkgs#gcc -c sh -c \
  "gcc -I$PROTO -I$LIBX11DEV/include grabprobe.c -o grabprobe -L$LIBX11RUN/lib -lX11"
```

## Gotchas hit the hard way

- `Xlib.h` is in `libx11-*-dev` (NOT xorgproto). `xorgproto` holds `X11/X.h` and
  friends.
- `XInput2.h` is in `libxi-*-dev`. It pulls `Xge.h` (libxext-dev) and
  `Xfixes.h` (libxfixes-dev) — add all four `-I` dirs or include order breaks.
- If a dev output path ends in `/include`, do NOT append `/include` again
  (`-I$XIDEV/include` where `XIDEV=.../libxi-1.8.3-dev` is right; `...-dev/include`
  is wrong).
- Bare `-I` with an empty var is an error; guard each with a real glob result.
- `XIRawEvent` raw values are in `re->raw_values` (field on the event struct),
  NOT `re->valuators.raw_values`. `re->valuators.values`/`raw_values` are the
  (usually identical) pair on IXvaluator; for raw events read `re->raw_values[i]`.
- `nix run nixpkgs#xinput` / `nix run nixpkgs#xdotool` are how you get those tools
  without installing (the `xorg.*` alias is deprecated in 22.11+; use `xinput`,
  `xdotool` directly).
- `xinput test-xi2 --root` needs a display and blocks; wrap in `timeout`.
- When parsing raw event output, note `device: N (M)` — the event device and a
  secondary id; the mask_len field (`v2=8`) is bits, not count (loop i < mask_len*8
  when walking `XIMaskIsSet`).