# Hyprland / ML4W Recovery Guide

A cheat sheet for when the desktop breaks (no waybar, wrong keybinds, dead
buttons). Written 2026-05-29.

> Note: this system uses the **fish** shell. Commands below work in fish.
> `sudo` password prompts do NOT work inside Claude Code — run sudo commands
> in a normal terminal window.

---

## My good backup

A full working copy of the Hyprland config is saved at:

    ~/.config/hypr-GOOD-backup-20260529-1436

---

## The golden rule

NEVER edit these directly:
  - ~/.config/hypr/hyprland.conf
  - ~/.config/hypr/conf/*.conf   (the default files)

Put ALL personal changes (gaps, keybinds, etc.) in this ONE file:

    ~/.config/hypr/conf/custom.conf

It is sourced last, so it always wins, and ML4W never overwrites it.
After editing it, apply changes with:

    hyprctl reload

---

## PROBLEM 1: Waybar is gone AND/OR keybinds are wrong

Cause: `hyprland.conf` got replaced by a default "STUB" file, so it stopped
loading all the ML4W config (autostart, keybindings, etc.).

How to check — open the file and look at the top. If it says
"This config is a STUB!", it's broken.

FIX — restore it from the backup, then reload:

    cp ~/.config/hypr-GOOD-backup-20260529-1436/hyprland.conf ~/.config/hypr/hyprland.conf
    hyprctl reload

If the file is locked (see "Extra protection" below), unlock it first:

    sudo chattr -i ~/.config/hypr/hyprland.conf
    cp ~/.config/hypr-GOOD-backup-20260529-1436/hyprland.conf ~/.config/hypr/hyprland.conf
    hyprctl reload

---

## PROBLEM 2: Waybar buttons do nothing (calendar, power menu, settings, sidebar)

Cause: Quickshell (`qs`) is not running. Those buttons send commands to
Quickshell; if it's not running, nothing happens.

Check if it's running:

    pgrep -af qs

FIX — re-run the autostart script (starts Quickshell + friends):

    ~/.config/ml4w/scripts/ml4w-autostart

OR, the most reliable reset of everything: just LOG OUT and LOG BACK IN.

---

## PROBLEM 3: Waybar disappears for a second then comes back

That's not a bug — it's the wrong shortcut.

  - Super + Shift + B  = RELOAD waybar (kills + restarts it)  ← what you were pressing
  - Super + Ctrl  + B  = TOGGLE waybar on/off                 ← the one you want

---

## Change the waybar theme

  - Press: Super + Ctrl + T   (opens a visual theme picker)

Or manually (example):

    echo '/ml4w-modern;/ml4w-modern/colored' > ~/.config/ml4w/settings/waybar-theme.sh
    ~/.config/waybar/launch.sh

---

## Extra protection (optional): lock hyprland.conf so it can't be regenerated

Lock it (nothing can overwrite it):

    sudo chattr +i ~/.config/hypr/hyprland.conf

Unlock it (needed before you or ML4W can change it):

    sudo chattr -i ~/.config/hypr/hyprland.conf

---

## Make a fresh backup after things are working

    cp -r ~/.config/hypr/. ~/.config/hypr-GOOD-backup-$(date +%Y%m%d-%H%M)/

---
---

# CUSTOMIZATIONS WE ADDED (2026-05-29)

## The "doctor" script — one-command repair

Instead of fixing problems 1 & 2 by hand, just run:

    ~/.config/hypr/scripts/hypr-doctor.sh

It automatically:
  - detects if hyprland.conf is a STUB and restores it from the newest
    ~/.config/hypr-GOOD-backup-* folder, then reloads Hyprland
  - detects if Quickshell (qs) is dead and restarts the ML4W autostart
  - makes sure waybar is running

Note: if you locked hyprland.conf with `chattr +i`, the script will ask for
your sudo password to unlock it before restoring (run it in a terminal).

---

## How the waybar is customized (so it survives ML4W theme changes)

Two files control the bar:
  - WHICH buttons show + their position:
      ~/.config/waybar/themes/ml4w-modern/config         (default, can be overwritten)
      ~/.config/waybar/themes/ml4w-modern/config-custom  (OUR copy - used if it exists)
  - WHAT each button does (icon / on-click / tooltip):
      ~/.config/waybar/modules.json

launch.sh automatically prefers `config-custom` over `config`, so ALWAYS edit
config-custom. Same idea for style: use `style-custom.css` instead of style.css.

After editing either file, reload the bar:

    ~/.config/waybar/launch.sh

### Hide a button
Comment it out in the modules-left/center/right array in config-custom:

    // "custom/exit",

### Change what a button does
Edit its "on-click" in modules.json, e.g.:

    "custom/exit": {
        "format": "",
        "on-click": "qs ipc call power toggle",   // <- change this
        "tooltip-format": "Open Power Menu"
    }

### Add a new button
1. Define it in modules.json:

    "custom/mybutton": {
        "format": "",
        "on-click": "some-command",
        "tooltip-format": "What it does"
    }

2. Add "custom/mybutton" to a modules-* array in config-custom.
3. Reload: ~/.config/waybar/launch.sh

---

## "Show all keybindings" button (added)

  - Already on the bar (left of the notification bell), defined as
    "custom/keybinds" in modules.json -> runs ~/.config/hypr/scripts/keybindings.sh
  - Also available via keyboard shortcut:  Super + Ctrl + K

---

## Quick reference: which file for what

  Personal Hyprland settings (gaps, keybinds) -> ~/.config/hypr/conf/custom.conf
  Which waybar buttons show / their order     -> .../themes/ml4w-modern/config-custom
  What each waybar button does                -> ~/.config/waybar/modules.json
  Repair a broken desktop                     -> ~/.config/hypr/scripts/hypr-doctor.sh

---
---

# POST-RAIN HEALTH CHECK + SUDO FIX (2026-06-30)

After the PC got wet, ran a full health check. Hardware is fine:
  - All 32 threads online, no offline cores, no MCE/CPU faults.
  - All-core stress test held ~4.9-5.0 GHz steady -> power delivery solid.
    (CPU pegs at 95C under load -- NORMAL for the 9950X3D, not overheating.)
  - GPUs (RX 9070 XT + integrated) clean, no amdgpu errors.
  - No brownout/undervolt/throttle events; reboot history all clean shutdowns.
  - Note: GPU was NOT stress-tested (no tool installed). For the full power
    torture test: `sudo pacman -S glmark2` then run a combined CPU+GPU burn.

## The real issue: "sudo says wrong password even when it's right"

Cause: `pam_faillock`. Defaults were deny=3 / unlock_time=600, so 3 typos
locked the account for 10 min -- during which the CORRECT password is also
rejected. Pure software policy, predates the rain. NOT a keyboard problem.

Fix (run in a REAL terminal, not Claude Code -- sudo prompts need a real tty):

    sudo faillock --user dereck --reset                 # clear current lock
    # edit /etc/security/faillock.conf:  deny = 10  /  unlock_time = 120
    # (or comment out the 3 pam_faillock.so lines in /etc/pam.d/system-auth
    #  to disable lockout entirely)

Check your current failure tally anytime:

    faillock --user dereck

## Show failed-attempt count at the sudo prompt (added)

Script `/usr/local/bin/sudo-attempts.sh` + an `auth optional pam_exec.so`
line at the top of `/etc/pam.d/sudo`. Next sudo prompt after a failure shows:

    ⚠ sudo: 1/10 failed attempts for dereck (account locks at 10)

It auto-reads `deny` from faillock.conf. The `optional` keyword means a bug
in it can never lock you out of sudo. To remove:

    sudo sed -i '\#pam_exec.so stdout /usr/local/bin/sudo-attempts.sh#d' /etc/pam.d/sudo

---
---

# CMOS BATTERY PULL + FAN SMOOTHING (2026-07-01)

## I removed the CMOS coin battery (CR2032) for several days -- is that OK?

YES, no harm. That battery only keeps BIOS settings + clock alive while the PC
is UNPLUGGED. Pulling it was actually smart for a wet board (no residual power
while drying). The only effects:
  - BIOS settings reset to "Optimized Defaults"
  - Clock lost (Linux re-syncs it over the internet on next boot)

Battery health check: unplug the PC from the wall for a few minutes. If the
clock + BIOS settings SURVIVE, the cell is good. If they reset, the CR2032 is
dead -> replace it (~$1, any store, flat/+ side faces UP).

## Because BIOS reset to defaults, RE-APPLY in BIOS:
  - EXPO  -> memory profile. If OFF, RAM runs slow. TURN IT ON. (easy to forget)
  - Fan curve (below)
  - Anything else custom: boot order, Resizable BAR, etc.

## Fan smoothing -- stops the 1-2 sec fan surge on small tasks

WHY it happens: the Ryzen 9950X3D spikes ~20C in under 1 second on ANY load
burst (measured: 55C -> 78C instantly). The default fan curve chases that spike
-> fans blast for 1-2s -> task ends -> fans calm. Normal Zen 5 behavior, NOT a
fault. Fix = tell the fan to ignore sub-second spikes.

Steps (ASUS TUF B850M-PLUS):
  1. Reboot, tap DEL to enter BIOS (F2 also works).
  2. If on EZ Mode, press F7 for Advanced Mode.
  3. Press F6 to open Q-Fan Control (or Monitor tab -> Q-Fan Configuration).
  4. Select CPU Fan.
  5. CPU Fan Profile -> Manual.
  6. CPU Fan Step Up Time   -> INCREASE to slowest (several seconds). <-- THE FIX
     CPU Fan Step Down Time -> moderate (eases down smoothly).
     CPU Fan Speed Lower Limit -> optional gentle baseline.
  7. Optional: raise the low temp points on the graph so ~78C blips stay under
     the ramp threshold (e.g. hold low % up to ~70-75C).
  8. F10 -> save & exit. Repeat step 4 for Chassis/Case fans if those are loud.

The Step Up Time increase alone kills the surge -- it makes the fan ignore
anything shorter than the delay, which is exactly what the Zen 5 spikes are.

---
---

# ALT+TAB CYCLES WORKSPACES (2026-07-03)

Wanted Windows/macOS-style switching, but between workspaces (desktops)
instead of windows. All changes are in `~/.config/hypr/conf/custom.conf`
(the one file that always wins), applied with `hyprctl reload`.

Result:
  - Alt + Tab          -> next workspace
  - Alt + Shift + Tab  -> previous workspace
  - Super + Tab        -> next workspace (same thing)
  - Super + Shift + Tab-> previous workspace

`e+1` / `e-1` = relative move that includes empty workspaces and wraps around
(last -> first), so it never dead-ends.

What we OVERRODE (originals live in the default ML4W files, untouched):
  - Alt+Tab used to cycle WINDOWS (cyclenext) -> now cycles workspaces.
  - Super+Tab used to open the Quickshell overview menu -> now cycles
    workspaces. The overview menu currently has NO shortcut.

The block added to custom.conf:

    unbind = ALT, Tab
    bind = ALT, Tab, workspace, e+1
    bind = ALT SHIFT, Tab, workspace, e-1
    unbind = SUPER, Tab
    bind = SUPER, Tab, workspace, e+1
    bind = SUPER SHIFT, Tab, workspace, e-1

To undo: delete that block from custom.conf and `hyprctl reload` (the ML4W
defaults for Alt+Tab / Super+Tab come back automatically).

---
---

# SWITCHED FROM WAYBAR TO CAELESTIA SHELL (2026-07-05)

Replaced the ML4W waybar with **Caelestia** (a Quickshell-based shell,
`caelestia-shell` from the AUR). Runs on top of Hyprland like waybar did.

## What we changed (2 things)

1. DISABLED waybar using ML4W's own native off-switch (a marker file):

       touch ~/.config/ml4w/settings/waybar-disabled

   `~/.config/waybar/launch.sh` checks for this file and skips launching
   waybar when it exists. Survives reboots.

2. AUTOSTART Caelestia -- added to ~/.config/hypr/conf/custom.conf:

       exec-once = caelestia shell -d

## GOTCHAS (things that secretly re-enable waybar -> 2 bars again)

  - Super + Ctrl + B  (toggle.sh) DELETES the marker + relaunches waybar.
    Don't press it. (Super + Shift + B = reload, respects the marker, safe.)
  - hypr-doctor.sh also DELETES the marker + relaunches waybar. If you run
    it, re-disable waybar afterwards with:
        touch ~/.config/ml4w/settings/waybar-disabled && pkill waybar

## Manually start / stop Caelestia

    caelestia shell -d        # start
    caelestia shell -k        # stop  (or: pkill -f 'qs -c caelestia')
    caelestia shell -s        # list available IPC commands

## FULL REVERT back to waybar

    rm ~/.config/ml4w/settings/waybar-disabled
    ~/.config/waybar/launch.sh
    # then delete the "exec-once = caelestia shell -d" line from custom.conf

## Caelestia keybinds we added (in custom.conf)

IMPORTANT: Caelestia's IPC syntax is `caelestia shell <target> <function> [args]`
(NOT `caelestia shell ipc call ...`). List drawers: `caelestia shell drawers list`.

  - Super + Space     -> launcher   (was Walker/Rofi via launcher.sh)
  - Super + Escape    -> session    (power / logout menu)
  - Super + Shift + = -> session    (was confirm-poweroff.sh/rofi; now same as Escape)
  - Super + D         -> dashboard
  - Super + N         -> sidebar    (notifications)

All are `bind = SUPER, <key>, exec, caelestia shell drawers toggle <name>`.
Available drawers: bar, osd, session, launcher, dashboard, utilities, sidebar.
To revert Super+Space to the old ML4W launcher:
    bind = SUPER, SPACE, exec, ~/.config/hypr/scripts/launcher.sh

Note: the OLD power menu (Super+Ctrl+P -> `qs ipc call power toggle`) still
points at ML4W's quickshell, not Caelestia. Harmless; ignore or remove it.

## MIGRATION TO CAELESTIA + BARE HYPRLAND (2026-07-05, cont.)

Goal: use Caelestia for everything the shell can do; keep ML4W's Hyprland
.conf files (they're just Hyprland config now, no ML4W daemon left running).
Fresh backup made first: ~/.config/hypr-GOOD-backup-20260705-2223-precaelestia

Step 1 - Notifications: swaync -> Caelestia's built-in server.
  - Commented `exec-once = swaync` in conf/autostart.conf.
  - Caelestia now owns org.freedesktop.Notifications. Toggle DnD:
      caelestia shell notifs toggleDnd

Step 2 - Autostart trim (all in conf/autostart.conf, commented not deleted):
  - listeners.sh --startall   (only gtk-theme-switcher + low-bat; desktop=no battery)
  - ml4w-wallpaper-app --restore   (Caelestia renders+restores wallpaper itself)
  - ml4w-autostart            (was launching ML4W's quickshell: bar backend,
                               settings app, overview, welcome -- all replaced)
  KEPT (essential, not ML4W-shell): polkit, gnome-keyring, gtk.sh, hypridle,
  cliphist, cleanup.sh, com.ml4w.hyprlandsettings/hyprctl.sh (just hyprctl keywords).
  Also killed the leftover running ML4W `qs` instances.

  Wallpaper now managed by Caelestia:
      caelestia wallpaper -f <image>      # set + auto-generate theme colors
      caelestia wallpaper -r <dir>        # random
  Current tracked at ~/.local/state/caelestia/wallpaper/path.txt

Step 3 - Package removal (run in a real terminal, needs sudo):
      sudo pacman -D --asexplicit qt6-wayland      # protect it (Caelestia needs it)
      sudo pacman -Rns waybar swaync walker        # genuinely unused now
  ROFI IS NOW REMOVABLE (2026-07-05): all its keybind users were disabled
  (see Step 5 below). So the safe removal is now:
      sudo pacman -Rns waybar swaync walker rofi rofi-wayland
  The scripts that used rofi (ml4w-sidepad, screenshot.sh, keybindings.sh,
  ml4w-wallpaper-app, text-extractor.sh) stay on disk but are all unbound.

CLIPBOARD: handled by Quakboard (own Tauri app, NO rofi), bound Super+V via
~/.config/hypr/quakboard.conf (sourced last, so it OVERRIDES ML4W's
Super+V -> ml4w-cliphist). The ml4w-cliphist rofi bind is dead/overridden.

Step 4 - More keybind changes (2026-07-05):
  - Poweroff: Super+Shift+= now opens Caelestia's session drawer (power menu)
    instead of confirm-poweroff.sh (rofi). Script still on disk, unbound.
  - Dropped Super+Escape (was a duplicate session-menu bind).
  - Dropped Super+Alt+A (text-extractor OCR) -- it wasn't working. Unbound in
    custom.conf; script still on disk if you want to fix it later.
  - Keybind viewer (Super+Ctrl+K) stays on rofi. Caelestia has NO keybind
    cheatsheet, and rofi stays for the utilities above anyway, so keeping the
    viewer on rofi means ONE menu tool, not two. (keybindings.sh walker branch
    was dropped since walker is uninstalled.)
    NOTE: that viewer reads conf/keybindings/default.conf, so it shows the
    ML4W defaults, NOT your custom.conf overrides. For the exact live set:
        hyprctl binds

Step 5 - Disabled unused ML4W keybinds (2026-07-05, unbind lines in custom.conf):
  These were the last rofi users; disabling them frees rofi for removal.
    Super+S / Super+Shift+S / Super+Ctrl+Left / Super+Ctrl+Right  -> sidepad
    Super+Ctrl+W / Super+Shift+W / Super+Alt+W                    -> ML4W wallpaper
    Super+Print / Super+Alt+F / Super+Alt+S                       -> ML4W screenshot menu
    Super+Ctrl+K                                                  -> keybind viewer
  To re-enable any: delete its `unbind` line from custom.conf + hyprctl reload.
  For the exact live keybind set at any time: `hyprctl binds`.

Step 6 - Disabled dead waybar control keys (2026-07-05, custom.conf):
    Super+Shift+B  (waybar reload)
    Super+Ctrl+B   (waybar toggle - also re-triggered the disable marker)
    Super+Ctrl+T   (waybar theme switcher)
  Pointless once the waybar package is removed. Unbound.

# ====================================================================
# CAN I REMOVE ML4W?  -- NO. Here is the definitive explanation.
# ====================================================================

ML4W is NOT a package (nothing to `pacman -R`). It is a GIT DOTFILES REPO
stowed into ~/.config via symlinks:

    ~/.config/hypr    -> ~/.mydotfiles/com.ml4w.dotfiles.stable/.config/hypr
    ~/.config/ml4w    -> ~/.mydotfiles/com.ml4w.dotfiles.stable/.config/ml4w
    ~/.config/waybar  -> ~/.mydotfiles/com.ml4w.dotfiles.stable/.config/waybar

That repo IS your Hyprland config. hyprland.conf sources ~10 of its files
(monitor, keyboard, autostart, window, decoration, layout, workspace,
keybindings, ...). ML4W scripts also power everyday keybinds that still work:
    Super+Return -> terminal   Super+B -> browser   Super+E -> file manager
    Super+Ctrl+C -> calculator   emoji picker, theme toggle, float toggles, etc.

Deleting ~/.mydotfiles/com.ml4w.dotfiles.stable/ = no desktop. DON'T.
Also DON'T delete ~/.config/waybar (symlink into the repo).

IMPORTANT: because these are symlinks, ALL our custom.conf edits actually live
inside the dotfiles repo at:
    ~/.mydotfiles/com.ml4w.dotfiles.stable/.config/hypr/conf/custom.conf
So you can `git -C ~/.mydotfiles/com.ml4w.dotfiles.stable commit` to version them.

What "removing ML4W" really meant, and is ALREADY DONE: kill the ML4W
shell/daemons (waybar, swaync, ML4W quickshell, wallpaper app, listeners) and
let Caelestia own the UI. No ML4W process runs anymore. What remains is just
your Hyprland config. That IS "Caelestia + bare Hyprland".

# ====================================================================
# CURRENT STATE (after full migration, 2026-07-05)
# ====================================================================

UI shell:      Caelestia only (bar, launcher, notifications, dashboard,
               sidebar, session/power menu, wallpaper + theming)
Clipboard:     Quakboard (own Tauri app, Super+V) -- NOT rofi
Screenshots:   hyprshot (Super+Shift+3/4/5)
Config base:   ML4W dotfiles repo (symlinked) -- keep it
Wallpaper:     caelestia wallpaper -f <img>

Caelestia keybinds (custom.conf):
    Super+Space     -> launcher
    Super+Shift+=   -> session / power menu
    Super+D         -> dashboard
    Super+N         -> notifications sidebar

Packages to remove (run once, sudo, real terminal):
    sudo pacman -D --asexplicit qt6-wayland
    sudo pacman -Rns waybar swaync walker rofi rofi-wayland

Backups:
    ~/.config/hypr-GOOD-backup-20260705-2223-precaelestia   (pre-migration)
    ~/.config/hypr-GOOD-backup-20260529-1436                (older)

FULL REVERT to pre-Caelestia:
    cp -r ~/.config/hypr-GOOD-backup-20260705-2223-precaelestia/. ~/.config/hypr/
    rm -f ~/.config/ml4w/settings/waybar-disabled
    # reinstall removed pkgs if needed: sudo pacman -S waybar swaync rofi
    hyprctl reload   (or log out/in)

WHAT STILL "IS" ML4W (and why it's fine): the Hyprland .conf files under
~/.config/hypr/conf/ are organized by ML4W but are plain Hyprland config that
Hyprland reads directly. No ML4W process runs anymore. That IS "bare Hyprland
+ Caelestia". No need to rewrite them.

To FULLY REVERT the migration: restore the pre-caelestia backup:
    cp -r ~/.config/hypr-GOOD-backup-20260705-2223-precaelestia/. ~/.config/hypr/
    rm ~/.config/ml4w/settings/waybar-disabled
    hyprctl reload   (or log out/in)

## Notes
  - ALL keybinds live in Hyprland config, not the shell -- switching shells
    does NOT change any hotkey. Screenshots, Alt+Tab, etc. are unaffected.
  - ML4W's own Quickshell (`qs`) processes are left running -- harmless,
    they power a few leftover ML4W popups. Not used by Caelestia.
  - Caelestia config lives in ~/.config/caelestia/shell.json
    (theme auto-generates from the wallpaper).
  - DON'T remove qt6-wayland (shows as an orphan but Caelestia needs it).
    Protect it: `sudo pacman -D --asexplicit qt6-wayland`
