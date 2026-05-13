# Plan — Rust Implementations with Ratatui UI

## Goal

Rewrite the macOS Rust binary with a full TUI (Ratatui), then create equivalent
Rust binaries for Linux and Windows. All three share the **same UI and logic via
a workspace crate**; only the install commands and OS-specific steps differ.

Decisions locked in:
- **Full parity with the bash source of truth** (`apps/setup_macos.sh`). The Rust
  port must match the bash feature-for-feature (multi-account SSH, GitHub
  Enterprise, managed-block markers, gh confirmation flow, `resolve_user_zshrc`).
- **Cargo workspace + shared crate from the start** (`setup_core`). No
  copy-pasted `ui.rs` across binaries.

> **Source of truth:** `apps/setup_macos.sh` (macOS) and `apps/setup_linux.sh`
> (Linux, already verified). Windows mirrors `powershell/install-oh-my-posh.ps1`.

---

## 0. Why this differs from the first draft

Two facts on the ground reshaped the plan:

1. **The existing `rust/setup_macos/src/main.rs` (867 lines) lags the bash.**
   It uses `console`/`indicatif`/`dialoguer`/`prettytable` and a *simpler*
   single-key SSH path. The bash now has multi-account SSH, GH Enterprise hosts,
   `_ensure_gh_account` + `_ensure_gh_scope`, idempotent managed-block markers,
   `resolve_user_zshrc` (Terax / VS Code `$ZDOTDIR`), and `clean_zshrc` heredity
   cleanup. Reaching parity is real work in `installer.rs` / `ssh.rs`.

2. **The bash is intensely interactive** (`read -r` for git name/email, per-account
   SSH email, gh account `[1/2/3]`, many y/N). In a raw-mode TUI these cannot be
   stdin reads — they become **modal input widgets**. This is the biggest design
   effort and is now first-class in the plan.

---

## 1. Shared TUI (Ratatui)

One UI codebase in `setup_core`, used by all three binaries. Three screens plus
a modal prompt overlay.

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
  [↑↓] navegar   [Tab] cambiar panel   [Space] seleccionar
  [A] todo       [Enter] confirmar      [Q] salir
```

### Screen 3 — Install Log (live, streamed output)
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

### Modal prompt overlay (the new part)
Replaces every bash `read`. A `Prompt` enum drives an input overlay:
`Text{label}`, `YesNo{label, default}`, `Choice{label, options}`. The installer
worker *requests* a prompt and blocks on a reply channel; the UI renders the
modal and sends the answer back. This is how git name/email, per-account SSH
email, and the gh `[1/2/3]` selection work without `read`.

### Keyboard navigation
| Key | Action |
|-----|--------|
| `↑` / `↓` | Navegar lista activa |
| `Tab` | Cambiar entre panel de categorías y panel de apps |
| `Space` | Seleccionar / deseleccionar app |
| `A` | Seleccionar todas las apps de la categoría |
| `Enter` | Confirmar / aceptar modal |
| `Q` / `Esc` | Salir / volver / cancelar modal |

---

## 2. Project Structure (workspace)

```
rust/
├── Cargo.toml                  # [workspace] members = core + 3 bins
├── setup_core/                 # shared library crate
│   ├── Cargo.toml
│   └── src/
│       ├── lib.rs
│       ├── model.rs            # AppEntry, Category, InstallSpec, InstallEvent, Prompt, ShellRc
│       ├── ui.rs               # Ratatui: screens, state machine, event loop
│       ├── tui.rs              # terminal init/teardown + suspend/resume helper
│       ├── runner.rs           # run_command + streaming child output → channel
│       ├── shell.rs            # resolve_user_zshrc, managed block, clean_zshrc
│       ├── ssh.rs              # ssh key + multi-account gh flow (OS-parametrized)
│       └── platform.rs         # `trait Platform` (the OS seam)
│
├── setup_macos/                # macOS (Homebrew)
│   ├── Cargo.toml              # depends on setup_core
│   └── src/{main.rs, installer.rs, apps.rs}
├── setup_linux/                # apt / dnf / pacman + flatpak
│   ├── Cargo.toml
│   └── src/{main.rs, installer.rs, apps.rs}
└── setup_windows/              # winget / scoop + Oh My Posh
    ├── Cargo.toml
    └── src/{main.rs, installer.rs, apps.rs}
```

Each binary is tiny: a `Platform` impl (`installer.rs`), a catalog (`apps.rs`),
and a ~10-line `main.rs`. Everything else lives in `setup_core` — no duplication.

---

## 3. The OS seam — `trait Platform`

```rust
pub trait Platform {
    fn ensure_prereqs(&self, tx: &Sender<InstallEvent>) -> bool; // brew+git / distro+zsh / winget
    fn catalog(&self) -> Vec<Category>;
    fn is_installed(&self, app: &AppEntry) -> bool;
    fn install(&self, app: &AppEntry, tx: &Sender<InstallEvent>) -> bool;
    fn uninstall(&self, app: &AppEntry) -> bool;
    fn post_install(&self, app: &AppEntry);          // eza aliases, zoxide init, docker group…
    fn shell_rc(&self) -> ShellRc;                   // zsh ~/.zshrc vs PowerShell $PROFILE
    fn ssh_add_args(&self) -> &[&str];               // --apple-use-keychain vs nothing
}
```

`ui.rs`, `ssh.rs`, `shell.rs`, `runner.rs` are shared and OS-parametrized through
this trait — they are never duplicated.

---

## 4. Data model (replaces the `:`-delimited bash strings)

```rust
pub struct AppEntry {
    pub name: String,
    pub install: InstallSpec,   // Brew{formula} / Cask{token} | Apt/Dnf/Pacman/Flatpak | Custom(fn) | Winget/Scoop
    pub path_export: Option<(String, String)>, // (path_to_add, executable) for add_to_path
    pub check: CheckKind,       // package-list vs executable-on-PATH
}
pub struct Category { pub title: String, pub apps: Vec<AppEntry> }
```

---

## 5. Cargo.toml dependencies (`setup_core`)

```toml
[dependencies]
ratatui   = "0.28"
crossterm = "0.28"
chrono    = "0.4"
anyhow    = "1"
```

Remove from the old `setup_macos`: `console`, `dialoguer`, `prettytable`, `indicatif`.
No async runtime — streaming uses `std::thread` + `std::sync::mpsc`.

---

## 6. Two hard problems to solve early (highest risk)

1. **Suspending the TUI for inherently-interactive subprocesses.**
   `gh auth login` (browser + terminal prompts), `p10k configure` (full-screen
   wizard), and the final `exec zsh -l` cannot run in raw mode. `tui.rs` provides
   `suspend(|| { ... })`: leave alternate screen + disable raw mode → run the
   child with inherited stdio → restore. **Prototype this in Step 1.**

2. **Streaming `brew`/`apt` output live** into the log pane. `runner.rs` spawns
   the child with piped stdout/stderr; a reader thread pushes
   `InstallEvent::Line` over an `mpsc::Sender`; the UI appends + updates the
   `[3/7] ████░░ 42%` bar. Prototype in Step 3.

---

## 7. Parity checklist to port into Rust

- `resolve_user_zshrc` + Terax / VS Code `$ZDOTDIR` logic → `shell.rs`
- Managed-block markers (idempotent write/remove) → `shell.rs`
- `clean_zshrc` heredity sweep + `clean_ssh_config` 5-line block delete → `shell.rs`
- Multi-account SSH loop, `slugify`, `github-<slug>` host aliases, GH Enterprise host → `ssh.rs`
- `_ensure_gh_account` (choice + confirm), `_ensure_gh_scope`, `gh ssh-key add` + SSH test → `ssh.rs`
- `post_install_config`: eza Nerd Font + aliases, zoxide init, mactop note → macOS `installer.rs`
- Linux extras (`setup_linux.sh` is the spec): distro detection, zsh + `chsh`,
  `usermod -aG docker`, distro-specific `gh` repo, flatpak fallback → linux `installer.rs`

---

## 8. Implementation Order

Each step ends at a green `cargo build` + `cargo clippy` + a manual run.

- [ ] **Step 1** — Scaffold the `rust/` workspace + `setup_core` skeleton; prove
      `tui.rs` init/teardown **and** the `suspend()` helper (run a dummy
      `less`/`vim` and return cleanly). De-risks problem 6.1 first.
- [ ] **Step 2** — `ui.rs` main menu + two-panel selection against a hardcoded
      catalog (no installs yet).
- [ ] **Step 3** — `runner.rs` streaming + InstallLog screen with a fake
      multi-step job (proves problem 6.2 + progress bar).
- [ ] **Step 4** — Modal prompt system (Text / YesNo / Choice round-trip through channels).
- [ ] **Step 5** — macOS `Platform` impl + `apps.rs`; port `shell.rs` / `ssh.rs`
      to full bash parity; wire real install/uninstall. Verify end-to-end on Mac.
      **← first reviewable milestone / PR.**
- [ ] **Step 6** — `setup_linux`: distro detection + apt/dnf/pacman/flatpak catalog.
- [ ] **Step 7** — `setup_windows`: winget/scoop + `$PROFILE` / Oh My Posh.
- [ ] **Step 8** — CI + `apps/install.sh` OS/arch detection + README one-liners.

> Steps 1–5 are the real milestone. Linux/Windows reuse the seam and are mostly
> a catalog + a `Platform` impl each.

---

## 9. Release Binaries

| Binary | Target | Built on |
|--------|--------|----------|
| `setup_macos` | `aarch64-apple-darwin` | macOS (GitHub Actions) |
| `setup_macos_x86` | `x86_64-apple-darwin` | macOS (GitHub Actions) |
| `setup_linux` | `x86_64-unknown-linux-gnu` | Ubuntu runner |
| `setup_windows.exe` | `x86_64-pc-windows-msvc` | Windows runner |

CI builds all four on every release tag and uploads them to GitHub Releases.
`apps/install.sh` detects the OS/arch and pulls the right binary automatically.
