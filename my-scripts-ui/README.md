# My Scripts UI

A Next.js 15 application for generating custom installation scripts for macOS and Linux systems. This tool allows users to create automated installation scripts for popular development tools, applications, and programming languages with a user-friendly web interface.

## Features

- 🎯 **Smart OS Detection**: Automatically filters apps based on selected operating system
- 📦 **Comprehensive App Database**: Support for 40+ popular applications and tools
- 🔧 **Multiple Package Managers**: Homebrew (macOS), APT, DNF, Pacman, AUR, Snap, Flatpak
- ⚡ **Oh My Zsh Integration**: Optional installation with Powerlevel10k theme and plugins
- 📝 **Script Customization**: Various options for backup, system updates, and dotfiles
- 💾 **Export Options**: Download generated scripts and README files
- 🌓 **Dark/Light Theme**: Responsive design with theme switching
- 📱 **Mobile Friendly**: Works on both desktop and mobile devices

## Supported Operating Systems

- **macOS**: Homebrew, Cask packages
- **Ubuntu/Debian**: APT, Snap packages
- **Fedora**: DNF, Flatpak packages  
- **Arch Linux**: Pacman, AUR packages

## Supported Applications

### Productivity Tools
- Raycast (macOS only)
- Spotify
- Amphetamine (macOS only)

### Code Editors/IDEs
- Visual Studio Code
- Cursor
- IntelliJ IDEA
- Vim
- WebStorm
- Zed
- VSCodium

### Terminals
- Warp (macOS only)
- iTerm2 (macOS only)

### Browsers
- Google Chrome
- Brave
- Microsoft Edge
- Firefox
- Opera

### Development Tools
- Git
- GitHub CLI
- AWS CLI
- Docker Desktop
- LLM Studio

### Programming Languages
- Python
- Java
- Rust
- Node.js
- Ruby
- Go
- C#/.NET
- C++
- PHP

### Frameworks
- Laravel (PHP)
- Kubernetes

## Tech Stack

- **Framework**: Next.js 15 with App Router
- **Language**: TypeScript
- **Styling**: Tailwind CSS v4
- **Package Manager**: Bun
- **Runtime**: Node.js 18+

## Getting Started

### Prerequisites

- Node.js 18.0 or later
- Bun 1.0 or later (recommended package manager)

### Installation

1. **Clone the repository**:
   \`\`\`bash
   git clone https://github.com/your-username/my-scripts-ui.git
   cd my-scripts-ui
   \`\`\`

2. **Install dependencies**:
   \`\`\`bash
   bun install
   \`\`\`

3. **Start the development server**:
   \`\`\`bash
   bun dev
   \`\`\`

4. **Open your browser**:
   Navigate to [http://localhost:3000](http://localhost:3000)

### Build for Production

\`\`\`bash
# Build the application
bun run build

# Start the production server
bun start
\`\`\`

### Development Commands

\`\`\`bash
# Start development server with Turbopack
bun dev

# Build for production
bun run build

# Start production server
bun start

# Run ESLint
bun run lint

# Type check without emitting files
bun run type-check
\`\`\`

## Project Structure

\`\`\`
src/
├── app/                          # Next.js App Router
│   ├── api/                      # API routes
│   │   └── generate-script/      # Script generation endpoint
│   ├── convert-images/           # Image conversion page
│   ├── generate-scripts/         # Script generation page (main feature)
│   ├── web-scraping/            # Web scraping page
│   ├── globals.css              # Global styles
│   ├── layout.tsx               # Root layout
│   └── page.tsx                 # Homepage
├── components/                   # Reusable React components
│   ├── AppSelector.tsx          # Individual app selection component
│   ├── CategorySection.tsx      # App category grouping component
│   ├── Navbar.tsx              # Sidebar navigation
│   └── ThemeToggle.tsx         # Dark/light theme switcher
├── data/                        # Static data
│   └── apps.ts                 # Application database
├── types/                       # TypeScript type definitions
│   └── script-generator.ts     # Script generation types
└── utils/                       # Utility functions
    └── script-generator.ts      # Script generation logic
\`\`\`

## Usage

### Generating Installation Scripts

1. **Select Operating System**: Choose your target OS (macOS, Ubuntu, Fedora, or Arch Linux)
2. **Choose Applications**: Select from categorized lists of applications and tools
3. **Configure Options**: 
   - System update before installation
   - Backup creation
   - Progress display
   - Dotfiles configuration
   - Oh My Zsh installation
4. **Generate Script**: Click the generate button to create your custom script
5. **Download**: Download the script and README files

### Script Features

Generated scripts include:

- **Color-coded output** for better readability
- **Error handling** with proper exit codes
- **Dependency checking** before installation
- **Package manager setup** (Homebrew, yay, etc.)
- **Post-installation configuration**
- **Idempotency** - safe to run multiple times

### Example Generated Script Structure

\`\`\`bash
#!/bin/bash
# Color definitions and utility functions
# System update (optional)
# Backup creation (optional)
# Package manager installation
# Application installations with error checking
# Oh My Zsh setup (optional)
# Dotfiles configuration (optional)
# Completion message
\`\`\`

## API Endpoints

### POST /api/generate-script

Generate installation script and README.

**Request Body**:
\`\`\`json
{
  "os": "macos" | "ubuntu" | "fedora" | "arch",
  "selectedApps": ["app-id-1", "app-id-2"],
  "options": {
    "updateSystem": boolean,
    "createBackup": boolean,
    "showProgress": boolean,
    "configureDotfiles": boolean,
    "installOhMyZsh": boolean
  }
}
\`\`\`

**Response**:
\`\`\`json
{
  "script": "#!/bin/bash\\n...",
  "readme": "# Installation Script\\n...",
  "filename": "install-script-macos.sh",
  "readmeFilename": "README-macos.md"
}
\`\`\`

## Configuration

### Adding New Applications

To add a new application to the database:

1. **Edit** \`src/data/apps.ts\`
2. **Add** a new app object with the required fields:

\`\`\`typescript
{
  id: 'unique-app-id',
  name: 'App Name',
  description: 'Brief description',
  icon: '🎯',
  category: 'category-name',
  macosOnly?: boolean,  // Optional: macOS only
  linuxOnly?: boolean,  // Optional: Linux only
  install: {
    macos?: { homebrew?: 'package', cask?: 'package', command?: 'custom' },
    ubuntu?: { apt?: 'package', snap?: 'package', command?: 'custom' },
    fedora?: { dnf?: 'package', command?: 'custom' },
    arch?: { pacman?: 'package', aur?: 'package', command?: 'custom' }
  },
  postInstall?: {
    macos?: ['command1', 'command2'],
    // ... other OS commands
  },
  checkInstall?: 'command -v app-name'
}
\`\`\`

### Supported Categories

- \`productivity\` - Productivity tools
- \`code-editors\` - Code editors and IDEs
- \`terminals\` - Terminal emulators
- \`browsers\` - Web browsers
- \`development-tools\` - Development utilities
- \`programming-languages\` - Programming languages and runtimes
- \`frameworks\` - Frameworks and orchestration tools

## Contributing

1. **Fork** the repository
2. **Create** a feature branch: \`git checkout -b feature/amazing-feature\`
3. **Commit** your changes: \`git commit -m 'Add amazing feature'\`
4. **Push** to the branch: \`git push origin feature/amazing-feature\`
5. **Open** a Pull Request

### Development Guidelines

- Use TypeScript for type safety
- Follow the existing code style
- Add appropriate error handling
- Test new applications across different OS
- Update documentation for new features

## Security Considerations

- Scripts only install from official sources
- No modification of critical system files
- Backup options for configuration files
- Clear error messages and validation
- Package verification where possible

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- **Next.js** team for the excellent framework
- **Tailwind CSS** for the utility-first CSS framework
- **Homebrew** and other package manager maintainers
- **Open source community** for the amazing tools and applications

## Support

If you encounter any issues or have questions:

1. Check the [Issues](https://github.com/your-username/my-scripts-ui/issues) page
2. Create a new issue with detailed information
3. Provide your OS, browser, and steps to reproduce

---

**Generated by My Scripts UI** - Making software installation easier, one script at a time. 🚀