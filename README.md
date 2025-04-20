# macOS Setup Script

This repository provides scripts to automate the setup of a macOS development environment,
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


## License

MIT License

---

_Built with ❤️ by DereckAn_
