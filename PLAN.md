# Plan — Rust Implementations with Ratatui UI

## Goal

Rewrite the macOS Rust binary with a full TUI (Ratatui), then create equivalent
Rust binaries for Linux and Windows. All three share the same UI and logic,
only the install commands and OS-specific steps differ.

---

## 1. Shared TUI (Ratatui)

One UI codebase used by all three binaries. The layout has three screens:

### Screen 1 — Main Menu
```
┌──────────────────────────────────────────────┐
│       Setup — Development Environment        │
│                                              │
│         > [1] Instalar y configurar          │
│           [2] Desinstalar                    │
│           [3] Salir                          │
└──────────────────────────────────────────────┘
```

### Screen 2 — App Selection (two-panel layout)
```
┌─ Categorías ──────────────┐ ┌─ Apps ─────────────────────────────┐
│ > IDEs y Editores         │ │ [x] Visual Studio Code  (instalado)│
│   Navegadores             │ │ [x] Cursor                         │
│   Lenguajes               │ │ [ ] IntelliJ IDEA                  │
│   Bases de Datos          │ │ [ ] WebStorm                       │
│   Herramientas CLI        │ │                                    │
│   Otros                   │ │                                    │
└───────────────────────────┘ └────────────────────────────────────┘
  [↑↓] navegar categorías   [Tab] cambiar panel   [Space] seleccionar
  [A] seleccionar todo       [Enter] confirmar     [Q] salir
```

### Screen 3 — Install Log (live output)
```
┌─ Instalando ──────────────────────────────────┐
│ ✓ Homebrew encontrado                         │
│ ✓ Git encontrado                              │
│ ✓ Oh My Zsh instalado                         │
│ ⠸ Instalando Visual Studio Code...            │
│                                               │
│ [3/7] ████████████░░░░░░░░░░░░  42%           │
└───────────────────────────────────────────────┘
```

### Keyboard navigation
| Key | Action |
|-----|--------|
| `↑` / `↓` | Navegar lista activa |
| `Tab` | Cambiar entre panel de categorías y panel de apps |
| `Space` | Seleccionar / deseleccionar app |
| `A` | Seleccionar todas las apps de la categoría |
| `Enter` | Confirmar selección e ir a instalación |
| `Q` / `Esc` | Salir / volver |

---

## 2. Project Structure

```
rust/
├── setup_macos/        ← refactor existente (macOS, Homebrew)
│   ├── Cargo.toml
│   └── src/
│       ├── main.rs     ← entry point, wires UI + installer
│       ├── ui.rs       ← Ratatui TUI (shared logic)
│       ├── installer.rs← install/uninstall commands (macOS)
│       └── apps.rs     ← app catalog (macOS)
│
├── setup_linux/        ← nuevo (Ubuntu/Debian, Fedora, Arch)
│   ├── Cargo.toml
│   └── src/
│       ├── main.rs
│       ├── ui.rs       ← same as macOS (copy or shared crate)
│       ├── installer.rs← apt / dnf / pacman + distro detection
│       └── apps.rs     ← app catalog (Linux)
│
└── setup_windows/      ← nuevo (winget + scoop)
    ├── Cargo.toml
    └── src/
        ├── main.rs
        ├── ui.rs       ← same TUI
        ├── installer.rs← winget / scoop / PowerShell
        └── apps.rs     ← app catalog (Windows)
```

> **Note:** `ui.rs` is identical across all three. Consider extracting it into a
> shared workspace crate (`rust/setup_ui/`) to avoid duplication once all three
> are working.

---

## 3. Cargo.toml changes

Replace current deps with:

```toml
[dependencies]
ratatui    = "0.28"
crossterm  = "0.28"
chrono     = "0.4"
```

Remove: `console`, `dialoguer`, `prettytable`, `indicatif`

---

## 4. macOS (`setup_macos`) — Refactor

**What changes:**
- Replace all `dialoguer` prompts with Ratatui screens
- Replace `prettytable` tables with Ratatui widgets
- Replace `indicatif` progress bars with Ratatui progress bar widget inside the log screen
- Add `post_install_config` for eza aliases, zoxide init (already in current code)
- Keep all installer logic in `installer.rs` unchanged

**What stays the same:**
- All install/uninstall commands
- `apps.rs` catalog
- `clean_zshrc()`, `clean_ssh_config()` logic

---

## 5. Linux (`setup_linux`) — New

**Distro detection** (at startup, before showing UI):
```rust
fn detect_distro() -> Distro {
    // reads /etc/os-release
    // returns Distro::Debian | Distro::Fedora | Distro::Arch
}
```

**Package manager per distro:**
| Distro | Manager | Install cmd |
|--------|---------|-------------|
| Ubuntu / Debian / Mint | apt | `sudo apt install -y` |
| Fedora / RHEL / Rocky | dnf | `sudo dnf install -y` |
| Arch / Manjaro / EndeavourOS | pacman | `sudo pacman -S --noconfirm` |

**Extra steps vs macOS:**
- Install `zsh` if not present (not pre-installed on all distros)
- `chsh -s $(which zsh)` to set default shell
- Docker: `sudo usermod -aG docker $USER`
- GitHub CLI: distro-specific repo setup before `apt install gh`

**Uninstall cleans:**
- `~/.oh-my-zsh`, `~/.p10k.zsh`
- `~/.zshrc` entries added by the script
- `~/.ssh/id_ed25519` + GitHub block in `~/.ssh/config`

---

## 6. Windows (`setup_windows`) — New

**Package managers supported:**
- **winget** (built into Windows 11, preferred)
- **Scoop** (fallback, also handles CLI tools better)

**Detection at startup:**
```rust
fn detect_package_manager() -> PkgManager {
    // tries `winget --version`, then `scoop --version`
    // if neither found, installs Scoop via PowerShell
}
```

**App catalog differences vs macOS/Linux:**
- No iTerm2 / Warp → use Windows Terminal (already built-in) or Tabby
- No Homebrew → winget/scoop for everything
- Extra: Oh My Posh instead of Powerlevel10k (already in `powershell/install-oh-my-posh.ps1`)
- Shell setup: PowerShell 7 + Oh My Posh (mirrors existing PowerShell script)

**Shell config writes to:** `$PROFILE` (PowerShell profile) instead of `~/.zshrc`

**Uninstall:**
- `winget uninstall` / `scoop uninstall` per app
- Remove Oh My Posh from `$PROFILE`
- Remove SSH key

---

## 7. Implementation Order

- [ ] **Step 1** — Build shared `ui.rs` with Ratatui (main menu + app selector + log screen)
- [ ] **Step 2** — Refactor `setup_macos` to use the new UI, verify it compiles and runs
- [ ] **Step 3** — Create `setup_linux`, wire distro detection + apt/dnf/pacman catalog
- [ ] **Step 4** — Create `setup_windows`, wire winget/scoop catalog + PowerShell shell setup
- [ ] **Step 5** — Extract `ui.rs` into a shared workspace crate if duplication is painful
- [ ] **Step 6** — Update `apps/install.sh` to detect OS and download the right binary
- [ ] **Step 7** — Update `README.md` with new Linux and Windows one-line install commands

---

## 8. Release Binaries

| Binary | Target | Built on |
|--------|--------|----------|
| `setup_macos` | `aarch64-apple-darwin` | macOS (GitHub Actions) |
| `setup_macos_x86` | `x86_64-apple-darwin` | macOS (GitHub Actions) |
| `setup_linux` | `x86_64-unknown-linux-gnu` | Ubuntu runner |
| `setup_windows.exe` | `x86_64-pc-windows-msvc` | Windows runner |

CI builds all four on every release tag and uploads them to GitHub Releases.
`apps/install.sh` detects the OS/arch and pulls the right binary automatically.
