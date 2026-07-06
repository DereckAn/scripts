# linux

Backup of my CachyOS / Hyprland desktop: **Caelestia shell + Quakboard
clipboard**, migrated off ML4W's waybar/swaync/rofi/walker (2026-07-05).

**To rebuild on a fresh machine → [RESTORE.md](./RESTORE.md).**

| File | What |
|---|---|
| `RESTORE.md` | Step-by-step rebuild on fresh CachyOS |
| `HYPRLAND-RECOVERY.md` | Full migration history + desktop repair + system fixes |
| `config/hypr/custom.conf` | My Hyprland overrides + Caelestia keybinds (the important one) |
| `config/hypr/autostart.conf` | ML4W autostart with the old shell/daemons disabled |
| `config/hypr/quakboard.conf` | Quakboard's managed Super+V bind |
| `pkglist-explicit.txt` | `pacman -Qqe` snapshot (explicit packages) |
| `pkglist-aur.txt` | `pacman -Qqm` snapshot (AUR/foreign packages) |

> These are an **overlay** on a stock ML4W install, not a full config.
> ML4W (`~/.mydotfiles/com.ml4w.dotfiles.stable`, symlinked into `~/.config`)
> is the base and must be installed first — see RESTORE.md step 1.

Not tracked here (too big / binary — back up separately):
- Quakboard AppImage (`~/Applications/Quakboard-*.AppImage`, ~93M)
- Quakboard data (`~/.local/share/com.dereckan.quakboard/`, clipboard history)
- Wallpapers
