# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Structure

This is a monorepo with two main areas:

- **`my-scripts-ui/`** — Next.js web application (primary codebase)
- **`apps/`**, **`bash/`**, **`powershell/`**, **`rust/`**, **`python/`**, **`square/`** — Standalone automation scripts

## Next.js Application (`my-scripts-ui/`)

### Commands

All commands run from `my-scripts-ui/`:

```bash
bun dev          # Development server with Turbopack at http://localhost:3000
bun run build    # Production build
bun run type-check  # TypeScript type check (no emit)
```

Bun is the required package manager (not npm/yarn).

### Architecture

Uses **Next.js App Router** with the following layout:

- `src/app/` — Dashboard and client-side tool pages (`generate-scripts/`, `convert-images/`, and `svg-to-pdf/`).
- `src/components/` — Reusable React components, typically one per feature area.
- `src/data/apps.ts` — Static database of 40+ applications with OS-specific install commands (Homebrew, APT, DNF, Pacman, Snap, Flatpak).
- `src/utils/` — Utilities for script generation, image conversion, and SVG-to-PDF conversion.
- `src/types/` — TypeScript interfaces per feature.

Path alias `@/*` maps to `./src/*`.

### Features and Data Flow

**Script Generator** (`/generate-scripts`): Users select a target OS and apps → the browser generates Bash and README previews using `src/utils/script-generator.ts` and `src/data/apps.ts` → users download individual files or a ZIP.

**Image Converter** (`/convert-images`): Client-side upload and conversion → users download JPEG, PNG, WebP, or AVIF files individually or in a ZIP.

**SVG to PDF** (`/svg-to-pdf`): SVG/SVGZ upload → users arrange pages and configure paper settings → jsPDF and svg2pdf.js generate a merged PDF or individual PDFs in a ZIP.

**Shared UI**: The dashboard and all three tools use `src/components/dashboard/WorkspaceShell.tsx` for navigation and light/dark themes.

## Automation Scripts

The macOS setup automation has three equivalent implementations in different languages:

| Implementation | Location | Notes |
|---|---|---|
| Rust binary | `rust/setup_macos/` | Fastest; distributed via `apps/install.sh` |
| Python | `apps/setup_macos.py` | Uses `rich` for CLI output |
| Bash | `apps/setup_macos.sh` | No dependencies |

The PowerShell script (`powershell/install-oh-my-posh.ps1`) handles Windows terminal setup. It accepts a `-Quick` flag for non-interactive execution and a `-Param` block that must stay at the top of the file for remote execution via `iex`.
