# Flake leftovers after WAN SSH closed (2026-08)

Checklist from the audit at `9a1b272`. Most items landed in the same
session; this file is the *after* state so the next pass does not
re-propose them.

## Applied (do not redo)

- C `viewport` flake input removed. Binary + portal are `viewport-smithay`.
- Dead `systemd.services.mopidy` fragment gone. `mopidy-subidy` and
  `duckdns-token` are unused in the flake; they may still exist as keys
  in `secrets/secrets.yaml` (do not edit the encrypted file unless asked).
- SearXNG is back: `desktop/configuration/searx.nix`, loopback `:8081`,
  JSON enabled, secret via `sops.templates."searx.env"`. Hermes skill
  `research/searxng` + Claude `~/.claude/skills/searxng` + `SEARXNG_URL`
  / `SEARXNG_API_URL`.
- Preservation: dropped `/var/lib/private/open-webui` and
  `/etc/mullvad-vpn`. Lidarr dir owner is `codebam:users`.
- Groups `libvirtd` / `docker` removed from `codebam`.
- `trustedInterfaces` is `tailscale0` only (`virbr0` gone).
- Desktop NAT / `dns0` gone.
- `services.ananicy` and `system.autoUpgrade` blocks deleted.
- `modules/sway-patches/` deleted.
- Unfree/insecure allowlists trimmed (`mongodb`, `vscode`, `open-webui`,
  `firefox-bin*`, `cuda_nvcc`, `android-sdk-platform-tools`, `pnpm-9.15.9`).
- Steam `dedicatedServer` / `remotePlay` / `localNetworkGameTransfers`
  `openFirewall = false`. Built nftables accepts `80, 443, 51413` only.
- helix/nixd options expr uses `osConfig.networking.hostName`.
- GPT swap partitions stay on disk; `swapDevices = lib.mkForce` drops
  them from fstab (desktop/Deck keep `/swap/swapfile`; laptop is zram
  only).
- `services.gcp-builder.enable` defaults to **false**. When enabled,
  `rebuild-switch` is local unless `--gcp`.

## Confirm, do not flip casually

- `lanzaboote` on every `mkNixosSystem` host, including Steam Deck —
  intended.
- `zramSwap.memoryPercent = 100` on the 64G desktop is still deliberate.
- Reclaiming the 2G/8G GPT swap partitions needs a repartition.

## Flake-eval pitfall

New files must be `git add`ed before `nixos-rebuild build`. The flake
copies from git; an untracked module fails as a missing store path.
