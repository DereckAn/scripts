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



Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.