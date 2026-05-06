# Development Environment Setup Scripts

Automate the setup of your development environment on macOS, Linux, or Windows with a single command.

---

## 🍎 macOS Setup

Installs and configures: Homebrew, Git, Oh My Zsh, Powerlevel10k, Zsh plugins, SSH keys for GitHub, and your choice of apps (IDEs, browsers, languages, databases, and more).

### Run it

Pick any of the three options — they all do the same thing:

**Rust (recommended)** — fastest, best UI:
```bash
sh -c "$(curl -fsSL https://raw.githubusercontent.com/DereckAn/scripts/main/apps/install.sh)"
```

**Python:**
```bash
curl -fsSL https://raw.githubusercontent.com/DereckAn/scripts/main/apps/setup_macos.py | python3 -
```

**Bash** — no dependencies:
```bash
bash <(curl -fsSL https://raw.githubusercontent.com/DereckAn/scripts/main/apps/setup_macos.sh)
```

### After running

- Set your terminal font to **FiraCode Nerd Font Mono** to see icons correctly.
- Restart your terminal to apply all changes.
- Run `p10k configure` to customize your prompt theme.

### Verify the setup

```bash
bash apps/smoke_test.sh
```

---

## 🐧 Linux Setup

Supports **Ubuntu/Debian**, **Fedora/RHEL**, and **Arch/Manjaro** — the script auto-detects your distro and uses the right package manager (`apt`, `dnf`, or `pacman`).

Installs and configures: Git, Zsh, Oh My Zsh, Powerlevel10k, Zsh plugins, SSH keys for GitHub, and your choice of apps (IDEs, browsers, languages, databases, and more).

### Run it

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/DereckAn/scripts/main/apps/setup_linux.sh)
```

### After running

- Set your terminal font to a **Nerd Font** (e.g. FiraCode Nerd Font) to see icons correctly.
- Restart your terminal to apply all changes.
- Run `p10k configure` to customize your prompt theme.
- If Docker was installed, log out and back in to use it without `sudo`.

---

## 🪟 Windows Setup (PowerShell)

Installs Oh My Posh, Nerd Fonts, PSReadLine, Terminal-Icons, posh-git, and `z` for directory navigation.

### Run it

```powershell
irm https://raw.githubusercontent.com/DereckAn/scripts/main/powershell/install-oh-my-posh.ps1 | iex
```

**Quick install** (non-interactive, uses defaults — theme: montys, font: FiraCode):
```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/DereckAn/scripts/main/powershell/install-oh-my-posh.ps1))) -Quick
```

### After running

- Set your terminal font to the installed Nerd Font:
  - **Windows Terminal**: Settings → Profiles → Appearance → Font Face
  - **VS Code**: Settings → Terminal › Integrated: Font Family → `FiraCode Nerd Font`
- Restart your terminal to apply changes.

---

## Help and inspiration

- [macOS Setup Script](https://github.com/sapoepsilon/scripts.git)

## License

MIT — Built with ❤️ by [DereckAn](https://github.com/DereckAn)
