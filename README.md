# macOS Setup Script

This script automates the setup of a development environment on macOS, installing essential tools and configuring your terminal for productivity.

## Features

This script will install and configure the following on your macOS system:

- **Homebrew**: The macOS package manager.
- **Git**: Version control system with global configuration (`user.name`, `user.email`).
- **Oh My Zsh**: A framework for managing Zsh configuration.
- **Powerlevel10k Theme**: A highly customizable theme for Oh My Zsh.
- **Zsh Plugins**: Enhances terminal functionality with plugins like `zsh-autosuggestions`, `zsh-syntax-highlighting`, and more.
- **GitHub CLI (gh)**: For managing GitHub repositories and adding SSH keys.
- **Development Tools**: A curated list of tools including programming languages (Python, Java, Rust, etc.), IDEs (VS Code, IntelliJ), browsers, databases, and more.
- **SSH Key Configuration**: Generates an SSH key and adds it to GitHub automatically.
- **macOS Customization**: Optionally hides the macOS Dock.
- **Terminal Restart**: Automatically restarts the terminal to apply changes.

## Installation

To run the script, copy and paste the following command in your terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/DereckAn/scripts/main/setup_macos.py | python3 -
```
