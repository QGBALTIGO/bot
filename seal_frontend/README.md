# Seal WebApp Frontend

React 19 + Vite 8 Telegram Mini App frontend for Seal-Bot.

## Commands

```sh
bun install
bun run dev
bun run lint
bun run type-check
bun run build
```

## Frontend-only hosting

When deploying only this frontend to Vercel, Netlify, or Cloudflare Pages, configure:

```sh
VITE_API_URL=https://your-backend.example.com
VITE_API_PREFIX=v1_7b82
```

Use `frontend` as the Cloudflare project root directory, `npm run build` as the build command, `dist` as the output directory, and `npx wrangler pages deploy dist --project-name seal-bot-frontend` as the deploy command. The selected Cloudflare Build token must have `Account > Cloudflare Pages > Edit` permission.

Do not set the root directory to `dist`; Cloudflare checks that directory before the build runs. Do not use `npx wrangler deploy`; that command is for Workers, not Pages.

## Tooling

- Stable TypeScript via `tsc`
- Biome for linting and formatting (replaces ESLint)
- Tailwind CSS v4 through `@tailwindcss/vite`

To serve the app from FastAPI, copy the build output into `backend/backend/static` before building the image (see the *Development Commands* section of the root README).
