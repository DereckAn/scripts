# Script Installer Generator

A modern web application that generates custom installation scripts for Windows, macOS, and Linux platforms. Built with Astro, React, and Tailwind CSS for optimal performance and user experience.

## ✨ Features

- **Multi-Platform Support**: Generate scripts for Windows (PowerShell), macOS (Bash + Homebrew), and Linux (distribution-specific)
- **Interactive UI**: Step-by-step wizard with real-time validation
- **Popular Applications**: Pre-configured installation commands for development tools, browsers, media players, and utilities
- **Custom Scripts**: Tailored installation scripts based on your platform and application selection
- **Download & Copy**: Easy script export with clipboard and file download options
- **Responsive Design**: Works perfectly on desktop, tablet, and mobile devices

## 🚀 Quick Start

### Prerequisites

- Node.js 18+
- npm or yarn

### Installation

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd script-installer-generator

🏗️ Project Structure
src/
├── components/           # React components
│   ├── steps/           # Step-by-step form components
│   │   ├── PlatformStep.tsx
│   │   ├── DistributionStep.tsx
│   │   ├── ApplicationStep.tsx
│   │   └── PreviewStep.tsx
│   ├── ProgressBar.tsx
│   └── ScriptGenerator.tsx
├── lib/                 # Core logic and utilities
│   ├── applications.json # Application database
│   ├── scriptGenerator.ts # Script generation logic
│   └── types.ts         # TypeScript interfaces
├── pages/              # Astro pages
│   └── index.astro     # Main page
└── styles/             # Global styles
    └── global.css      # Tailwind imports
