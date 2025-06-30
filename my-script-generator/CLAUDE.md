# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

- **Start development server**: `npm run dev` or `bun dev`
- **Build for production**: `npm run build` or `bun build`
- **Preview production build**: `npm run preview`
- **Lint code**: `npm run lint` (ESLint for TypeScript, TSX, and Astro files)
- **Format code**: `npm run format` (Prettier with Astro plugin)

## Environment Setup

1. **Supabase Configuration**: 
   - Copy `.env.example` to `.env`
   - Set up your Supabase project and add credentials
   - Run the SQL schema from `supabase-schema.sql` in your Supabase SQL editor

2. **Install dependencies**: `npm install` or `bun install`

## Architecture Overview

This is a **Script Installer Generator** - a web application that generates custom installation scripts for Windows, macOS, and Linux platforms. Built with Astro, React, and TypeScript.

### Core Architecture

**Frontend Stack**:
- **Astro** (v5) - SSR-enabled with Vercel adapter for API routes
- **React** - UI components and state management
- **TypeScript** - Type safety throughout the application
- **Tailwind CSS v4** - Styling with Vite plugin integration

**Backend Stack**:
- **Supabase** - Database for temporary script storage
- **Astro API Routes** - RESTful endpoints for script generation and serving
- **Vercel Serverless Functions** - Deployment platform with automatic scaling

**Application Flow**:
1. **Multi-step wizard**: Platform selection → Distribution (Linux only) → Application selection → Script preview
2. **Script generation**: Uses `ScriptGenerator` class to create platform-specific installation scripts
3. **Export options**: 
   - Download as file or copy to clipboard
   - **Quick Install Command**: Generate temporary shareable curl command (10min expiry)

### Key Components

**State Management**:
- Central `FormState` interface manages wizard progression
- Step-specific validation and navigation logic
- Conditional step skipping (distribution step only for Linux)

**Script Generation Engine** (`src/lib/scriptGenerator.ts`):
- Platform-specific script templates for Windows (PowerShell), macOS (Bash), and Linux (distribution-specific)
- Application database with cross-platform package manager mappings
- Support for Winget, Chocolatey, Homebrew, APT, DNF, Pacman, Zypper, Snap, and AUR

**Data Structure**:
- `applications.json` contains the application database with platform-specific installation commands
- Each application maps to different package managers across platforms
- Categories system for organizing applications (Development, Browsers, Media, Productivity, Utilities)

### File Structure Patterns

- **Components**: React components in `src/components/`, with step components in `steps/` subdirectory
- **Types**: Centralized TypeScript interfaces in `src/lib/types.ts`
- **Business Logic**: Core script generation logic isolated in `src/lib/scriptGenerator.ts`
- **Data**: Application and distribution data in JSON format in `src/lib/`
- **Pages**: Astro pages in `src/pages/` (single-page app with index.astro)
- **API Routes**: Server-side endpoints in `src/pages/api/`
  - `/api/generate-script` - POST endpoint to create and store temporary scripts
  - `/api/script/[id]` - GET endpoint to serve scripts via curl commands
- **Database**: Supabase client configuration in `src/lib/supabase.ts`

### Configuration

- **ESLint**: Configured for TypeScript and Astro files with recommended rules
- **Astro Config**: Static output with React integration and Tailwind CSS via Vite
- **Deployment**: Configured for Vercel with static site generation

When adding new applications, update the `applications.json` file with platform-specific package manager mappings. When modifying script generation logic, ensure cross-platform compatibility testing.

### Quick Install Command Feature

The **Quick Install Command** feature allows users to generate shareable one-line terminal commands similar to popular installation methods:

**User Flow**:
1. User completes script configuration (macOS/Linux only)
2. Clicks "Generate Quick Command" in preview step
3. System generates script, stores in Supabase with 10-minute expiration
4. Returns curl command: `sh -c "$(curl -fsSL https://yourapp.com/api/script/abc123)"`
5. Users can share this command with others for instant installation

**Security Features**:
- Scripts automatically expire after 10 minutes
- Unique random IDs prevent enumeration attacks
- Row-level security policies in Supabase
- Automatic cleanup of expired scripts

**Deployment Notes**:
- Requires Supabase database setup with provided schema
- Uses Vercel serverless functions for API routes
- Environment variables needed: `SUPABASE_URL`, `SUPABASE_ANON_KEY`