# Source Baltigo v2 staging

The `v2/seal-fusion` branch is deployed to a dedicated Railway web-only service for preview/testing.

- Production Telegram bot remains on the `main` service.
- Staging runs only `uvicorn webapp_entrypoint:app`; it never starts Telegram polling.
- The React/Vite Mini App is mounted at `/v2/`.
- Private compatibility APIs use Telegram-signed `initData` or a short-lived Source-signed session token.
- Character ownership stays keyed by the existing Source `character_id`.
- Database migrations in this branch are not automatically applied at web startup.

Staging domain: `https://source-v2-staging-production.up.railway.app`
