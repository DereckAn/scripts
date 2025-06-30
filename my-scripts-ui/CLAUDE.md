# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Next.js 15 application with TypeScript, Tailwind CSS v4, and React 19. The project uses **Bun** as the preferred package manager and is set up with the App Router architecture.

## Commands

- **Development**: `bun dev` - Starts development server with Turbopack at http://localhost:3000
- **Build**: `bun run build` - Creates production build
- **Start**: `bun start` - Starts production server
- **Lint**: `bun run lint` - Runs ESLint with Next.js rules

**Note**: Bun is the preferred package manager for this project.

## Architecture

- **Framework**: Next.js 15 with App Router (`src/app/` directory)
- **Styling**: Tailwind CSS v4 with PostCSS
- **TypeScript**: Configured with path mapping (`@/*` maps to `./src/*`)
- **Fonts**: Uses Geist Sans and Geist Mono from Google Fonts
- **Linting**: ESLint with Next.js core web vitals and TypeScript rules

## Key Files

- `src/app/layout.tsx` - Root layout with font configuration
- `src/app/page.tsx` - Homepage component
- `src/app/globals.css` - Global styles with Tailwind directives
- `tsconfig.json` - TypeScript configuration with path aliases
- `eslint.config.mjs` - ESLint configuration using flat config format