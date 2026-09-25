# Source: one native MiniApp

All 25 historical HTML entry points now serve the exact same compiled React application as `/menu`. They are not iframes, embedded HTML, duplicated themes, or CSS overrides. The existing Header, NavigationDrawer, UserProvider, QueryClient, Card, Button, Input, Badge, Toast and typography tokens remain the shared implementation.

## Entry points and source

`aninexus_frontend/src/native/routes.json` is the single compatibility manifest. Vite emits this same file into the build. `webapp_routes/native_webapps.py` installs the native HTML routes **after** the legacy routers and removes only their explicit GET handlers. JSON APIs, health checks, webhook routes and static assets are not intercepted. Historical query parameters and Telegram's initialization fragment are retained on first load. New navigation uses History API and stays inside the existing application.

The bot's embedded HTTP server now imports `webapp_entrypoint` as well. Both the combined bot runtime and the dedicated Uvicorn service use the same entry point.

## Migrated capabilities

- Shop: original native daily XCards and dice shop, character sales with confirmation, and a nickname change form. Nickname validation, update, coin debit and transaction record run in one PostgreSQL transaction; a rejected update does not charge.
- Cards: works, character search, category browsing, pagination, native character detail dialogs, and image/work contribution links.
- Anime/manga catalogues: search, alphabetical filters, pagination, native detail dialog and explicit Telegram post links.
- Collection album: characters and copies, works, completion, owned/missing/all views and favorite selection.
- Requests: AniList-backed anime/manga search, existing/pending labels, daily allowance, submission confirmation and problem reports.
- Contributions: character lookup, 2:3 image URL and note, work suggestions and contribution rules.
- Memory: four difficulties, matching board, timer/moves, restart, result submission and saved records.
- Account: free first nickname, country/language, privacy, notifications, favorite selection, terms and typed-confirmation deletion. Deletion retires the client session and suppresses user refresh/recreation.
- Terms: original versioned policy text, language selection, required-channel verification, explicit privacy/terms consent, accept and decline.
- Subscription: server-configured plans, authenticated intent creation, and a separate user gesture to open the checkout. The pending page does **not** claim that payment was approved.

The legacy Python HTML builders remain in the repository for compatibility tests and low-risk rollback, but are not served by the production entrypoint.

## Authentication and mutation safety

Existing native APIs retain their Bearer-token client. Legacy JSON APIs are reached through the same client with `sourceEndpoint`; signed `X-Telegram-Init-Data` is forwarded. An unsigned `uid` is never treated as proof of identity. Source endpoints do not attempt an unrelated Bearer refresh loop after a signature error.

Repeated action clicks are locked while a mutation is pending. Sales, paid nickname changes and checkout intent creation require explicit confirmation. All mutation failures use the existing toast UI. The account-deletion flow has its own terminal state and does not invoke the ordinary post-mutation user refresh.

## Verification

- `bun run build` type-checks and compiles the complete application.
- `pytest tests/test_native_webapps.py tests/test_native_nickname_transactions.py tests/test_webapp_identity.py` checks route replacement, API preservation, authentication and nickname transaction behavior.
- `python scripts/verify_native_browser.py --test --output /tmp/native-proof` runs the real compiled UI in Chromium against an isolated fixture server. It tests all historical entries on mobile/desktop and the interactive browsing, sale, nickname, request, contribution, subscription, terms, memory and deletion flows. It captures screenshots, a trace and a JSON report.
- These browser fixtures deliberately contain synthetic artwork, accounts and purchase responses. They do not authenticate to Telegram, use production funds, or prove live provider/webhook availability.
- `aninexus_frontend/dist` must be copied into `aninexus_runtime` before release. Existing CI checks their byte-for-byte equality.
