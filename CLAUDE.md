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
bun run lint     # ESLint
bun run type-check  # TypeScript type check (no emit)
```

Bun is the required package manager (not npm/yarn).

### Architecture

Uses **Next.js App Router** with the following layout:

- `src/app/` — Pages and API routes. Each feature has a matching page directory (e.g., `generate-scripts/`, `convert-images/`) and API route under `api/`.
- `src/components/` — Reusable React components, typically one per feature area.
- `src/data/apps.ts` — Static database of 40+ applications with OS-specific install commands (Homebrew, APT, DNF, Pacman, Snap, Flatpak).
- `src/utils/` — Pure utility functions that mirror the feature areas (script generation, image conversion, scraping, etc.).
- `src/types/` — TypeScript interfaces per feature.
- `src/lib/utils.ts` — `cn()` helper for Tailwind class merging.

Path alias `@/*` maps to `./src/*`.

### Features and Data Flow

**Script Generator** (`/generate-scripts`): Users select a target OS and apps → frontend POSTs to `/api/generate-script` → server builds a bash script from `src/utils/script-generator.ts` using the app database in `src/data/apps.ts` → user downloads script + README.

**Image Converter** (`/convert-images`): Client-side upload → `/api/convert-image` → returns converted file (JPEG/PNG/WEBP/AVIF).

**Social Media Galleries** (`/instagram-photos`, `/twitter-photos`): API routes proxy requests to external APIs; auth tokens handled server-side.

**AI Image Analysis** (`/image-analysis`): Connects to local LLM providers (Ollama, LM Studio) configured via `AIProviderConfig` component.

## Automation Scripts

The macOS setup automation has three equivalent implementations in different languages:

| Implementation | Location | Notes |
|---|---|---|
| Rust binary | `rust/setup_macos/` | Fastest; distributed via `apps/install.sh` |
| Python | `apps/setup_macos.py` | Uses `rich` for CLI output |
| Bash | `apps/setup_macos.sh` | No dependencies |

The PowerShell script (`powershell/install-oh-my-posh.ps1`) handles Windows terminal setup. It accepts a `-Quick` flag for non-interactive execution and a `-Param` block that must stay at the top of the file for remote execution via `iex`.
