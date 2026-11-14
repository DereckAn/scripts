# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Next.js 15 application with TypeScript, Tailwind CSS v4, and React 19. The project uses **Bun** as the preferred package manager and is set up with the App Router architecture.

## Commands

- **Development**: `bun dev` - Starts development server with Turbopack at http://localhost:3000
- **Build**: `bun run build` - Creates production build
- **Start**: `bun start` - Starts production server
- **Type check**: `bun run type-check` - TypeScript type checking (no emit)

**Note**: Bun is the required package manager for this project.

## Architecture

- **Framework**: Next.js 15 with App Router (`src/app/` directory)
- **Styling**: Tailwind CSS v4 with PostCSS
- **TypeScript**: Configured with path mapping (`@/*` maps to `./src/*`)
- **Fonts**: Uses Geist Sans and Geist Mono from Google Fonts

## Key Files

- `src/app/layout.tsx` - Root layout with font configuration
- `src/app/page.tsx` - Homepage component
- `src/app/globals.css` - Global styles with Tailwind directives
- `tsconfig.json` - TypeScript configuration with path aliases

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
