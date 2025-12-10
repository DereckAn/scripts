# Development Environment Setup Scripts

This repository provides scripts to automate the setup of development environments,
installing essential tools and configuring your terminal for productivity.

## Available Scripts

| Platform   | Script           | Description                                  |
| ---------- | ---------------- | -------------------------------------------- |
| 🍎 macOS   | Rust/Python/Bash | Complete macOS development environment setup |
| 🪟 Windows | PowerShell       | Oh My Posh terminal beautification           |

---

# 🪟 Windows PowerShell Setup (Oh My Posh)

Beautify your PowerShell terminal with Oh My Posh, Nerd Fonts, and useful modules.

## ⚡ One-Line Installation

Copy and paste this command in PowerShell to automatically configure everything:

```powershell
irm https://raw.githubusercontent.com/DereckAn/scripts/main/powershell/install-oh-my-posh.ps1 | iex
```

### Quick Install (Non-Interactive)

For a quick installation with default settings (theme: montys, font: FiraCode):

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/DereckAn/scripts/main/powershell/install-oh-my-posh.ps1))) -Quick
```

## What Gets Installed

- **Oh My Posh**: Beautiful prompt themes for PowerShell
- **Nerd Fonts**: Icons and glyphs for your terminal (FiraCode, CascadiaCode, etc.)
- **PSReadLine**: Predictive autocompletion based on history
- **Terminal-Icons**: File and folder icons in the terminal
- **z**: Quick directory navigation (like `cd` on steroids)
- **posh-git**: Git integration and status in your prompt

## Available Themes

The script offers 10+ popular themes to choose from:

- `montys` - Minimalist and clean
- `agnoster` - Classic and popular
- `dracula` - Elegant dark theme
- `catppuccin` - Soft color palette
- `tokyo` - Tokyo Night inspired
- And many more...

Preview all themes at: https://ohmyposh.dev/docs/themes

## Post-Installation Steps

1. **Change your terminal font** to the installed Nerd Font:

   - **Windows Terminal**: Settings → Profiles → Appearance → Font Face
   - **VS Code**: Settings → Terminal > Integrated: Font Family → `FiraCode Nerd Font`

2. **Restart your terminal** to apply changes

## Useful Aliases Included

| Alias    | Command         | Description                |
| -------- | --------------- | -------------------------- |
| `g`      | `git`           | Shortcut for git           |
| `ll`     | `Get-ChildItem` | List directory contents    |
| `touch`  | `New-Item`      | Create new files           |
| `which`  | Function        | Find command location      |
| `mkcd`   | Function        | Create and enter directory |
| `reload` | Function        | Reload PowerShell profile  |

---

# 🍎 macOS Setup Script

This section provides scripts to automate the setup of a macOS development environment,
installing essential tools and configuring your terminal for productivity.
Choose between three implementations: **Rust (precompiled binary)**, **Python**, or **Bash**.

## Features

The scripts will install and configure the following on your macOS system:

- **Homebrew**: The macOS package manager.
- **Git**: Version control system with global configuration (`user.name`, `user.email`).
- **Oh My Zsh**: A framework for managing Zsh configuration.
- **Powerlevel10k Theme**: A highly customizable theme for Oh My Zsh.
- **Zsh Plugins**: Enhances terminal functionality with plugins like `zsh-autosuggestions`, `zsh-syntax-highlighting`, and more.
- **GitHub SSH Key Setup**: Configures SSH keys for GitHub using GitHub CLI (`gh`).
- **Development Tools and Applications**: A curated list including Python, Java, Docker, VS Code, and more.
- **Optional Dock Hiding**: Hides the macOS Dock for a cleaner desktop.
- **Elegant CLI**: Interactive interface with colored tables, progress bars, and user-friendly prompts.

## Prerequisites

- macOS system (Apple Silicon recommended for the Rust binary).
- Internet connection.
- No Rust or Python installation required if using the precompiled Rust binary.

## Installation

Choose one of the following methods to run the script:

### Option 1: Rust (Precompiled Binary)

The Rust version is a precompiled binary, offering the best performance and a polished CLI experience with tables, progress bars, and colors. No Rust installation is required.

Run the following command to download and execute the binary:

```bash
sh -c "$(curl -fsSL https://raw.githubusercontent.com/DereckAn/scripts/main/apps/install.sh)"
```

Alternatively, you can download and run the binary manually:

1. Download the binary:

   ```bash
   curl -fsSL https://github.com/DereckAn/scripts/releases/latest/download/setup_macos -o setup_macos
   ```

2. Make it executable:

   ```bash
   chmod +x setup_macos
   ```

3. Run it:

   ```bash
   ./setup_macos
   ```

### Option 2: Python Script

The Python version requires Python 3 and uses the `rich` library for a colorful CLI. It's ideal if you prefer a Python-based solution.

1. Download and run the script directly:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/DereckAn/scripts/main/apps/setup_macos.py | python3 -
   ```

   This command downloads the script and executes it using Python 3. The script will automatically install the `rich` library if needed.

### Option 3: Bash Script

The Bash version is lightweight and requires only Bash (included in macOS). It provides a simpler CLI with basic colors but no progress bars.

Run the following command:

```bash
sh -c "$(curl -fsSL https://raw.githubusercontent.com/DereckAn/scripts/main/apps/setup_macos.sh)"
```

## Usage

1. Run the script using one of the methods above.
2. Follow the interactive prompts to:
   - Configure Git credentials and SSH keys for GitHub.
   - Select applications to install by category (e.g., IDEs, browsers, programming languages).
   - Hide the macOS Dock (optional).
   - Restart the terminal to apply changes (optional).

The script will:

- Skip already installed applications.
- Add programming language binaries to your PATH (e.g., `python3`, `java`).
- Display progress with colored tables, progress bars (Rust and Python versions), and clear prompts.

## Notes

- **GitHub CLI Authentication**: Some steps (e.g., adding SSH keys) may open a browser for GitHub CLI (`gh`) login.
- **Terminal Restart**: Restarting the terminal applies Oh My Zsh and PATH changes. The script defaults to Terminal.app. If you use iTerm2 or Warp, you may need to adjust the restart command (see Troubleshooting).
- **Rust Binary Compatibility**: The precompiled binary is for macOS Apple Silicon (arm64). For Intel (x86_64) Macs, you may need to use the Python or Bash version, or compile the Rust binary yourself (see Contributing).

## Help and inspiration

- [macOS Setup Script](https://github.com/sapoepsilon/scripts.git)

## License

MIT License

---

_Built with ❤️ by DereckAn_
