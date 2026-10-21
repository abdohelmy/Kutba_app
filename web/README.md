# Khutba web app

An iPhone/iPad-friendly web counterpart to the native apps. It uses the existing FastAPI service and existing mosque accounts; it does not have a separate sermon database or OpenAI API key.

## Run locally

Node.js 22.13 or newer is required.

```sh
npm run install:ci
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Open `http://127.0.0.1:3000`. The API proxy’s fixed upstream is configured in `app/api/[...path]/route.ts`. Keep it HTTPS; never put model API keys in client code.

## Features

- Account-free reader: mosque search, date-grouped khutbas, English text, Arabic glossary links with English/Arabic/transliteration/definitions, source dialogs, PDF download, text sizing, search, sharing, reading position, device-local saved copies.
- Mosque accounts: register with permission password, sign in, upload PDF/DOCX, optional title, Copenhagen upcoming-Friday default, extracted Arabic review, translation progress/reconnect, translation editing/approval, preview, publish, hide/show/remove, profile/password changes, mosque glossary, optional shared definitions after publishing.
- Responsive review columns on iPad; single column on iPhone. Large form inputs avoid iOS input zoom. Safe-area padding, keyboard focus, reduced-motion support and RTL Arabic notes.
- Home Screen manifest and an offline shell. Only explicitly saved published reader content goes into localStorage. Auth/API responses and unpublished admin content are never stored in the service-worker cache.

## Authentication and privacy

The same-origin proxy keeps the backend JWT in an HttpOnly, SameSite=Strict cookie (Secure on HTTPS). Mutation requests require a matching Origin. The upstream and routes are allowlisted. The backend remains responsible for identity, permissions and translation validation. No client-side assertion grants admin authority.

Browser saves belong to this browser/device and can be cleared or evicted. A previously downloaded copy cannot be remotely revoked; saved copies are removed when a refreshed mosque list says a khutba is no longer published. Use PDF for durable retention. Online features remain subject to the existing VM schedule. This web app does not change that schedule.

## Checks

```sh
npx tsc --noEmit
node --test tests/proxy.test.mjs
node tests/mobile-smoke.mjs
# Optional Safari-engine tests after `npx playwright install webkit`:
TEST_BROWSER=webkit node tests/mobile-smoke.mjs
```

Browser tests use an installed Chrome (or `CHROME_PATH`) and intercept API requests with fixtures. They do not translate, publish or delete production sermons. Screenshots go into ignored `output/qa/`. `TEST_URL` selects a different local preview URL. Safari-engine emulation does not replace a final check on a physical iPhone and iPad, especially Home Screen installation and Files/PDF handling.

## Build and hosting

The Sites tooling preserves the Worker-compatible Vinext build. `.openai/hosting.json` identifies this site; do not register a new site for updates. Publish through the Sites source/build/archive workflow. The initial deployment is owner-private; make it public through the hosting access controls only when approved for readers.

`npm run build` generates `dist/`; `npm start -- --port 3001` previews the built Worker locally. Optional WebMCP navigation is feature-detected and never exposes publish/delete tools. Unsupported browsers work normally.
