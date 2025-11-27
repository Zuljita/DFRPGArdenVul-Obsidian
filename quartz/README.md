# Quartz Setup

This repository uses a simple two-folder layout:
- `vault/` — Obsidian content (notes, attachments, etc.)
- `quartz/` — Quartz project (static site generator)

Quartz reads the vault directly via a relative path. No symlinks are required.

## Prerequisites
- Node.js 18+ and Git installed.
- Recommended: `pnpm` (Quartz uses pnpm). Install with `npm i -g pnpm`.

## Install Quartz into this folder (one-time)
You can either clone Quartz here or add it as a submodule:
- Clone: from repo root, run `git clone https://github.com/jackyzha0/quartz.git quartz && cd quartz && pnpm install`
- Submodule: `git submodule add https://github.com/jackyzha0/quartz.git quartz && cd quartz && pnpm install`

If `quartz/` already exists, skip cloning and just run `pnpm install` inside it.

## Configure Quartz to read the vault
Set the content root to the sibling `../vault` in your Quartz config. Use `quartz/quartz.config.example.ts` as a reference and adapt to your Quartz version.

## Local preview and build
Run these inside `quartz/` after configuring the content path:
- Preview: `pnpm dev` (watches the vault and serves locally)
- Build: `pnpm build` → output in `quartz/public/`

To publish, deploy the `public/` directory to your static host (e.g., Azure Static Web Apps). If using Azure, set the app artifact folder to `quartz/public`.

## Tips
- Keep all editing in `vault/`. Do not edit generated files in `public/`.
- If links break, create stubs in the vault or fix page titles to match wikilinks.
- Avoid committing `public/`, `node_modules/`, or caches.
