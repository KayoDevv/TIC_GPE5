# Frontend P0

Minimal browser extension P0.

**Tech:** Vue 3 + WXT (TypeScript, Tailwind). Playwright for E2E tests.

**Code Guidelines:** Extension for Google Chrome and Microsoft Edge complying with Manifest V3. Uses the Shadow DOM to isolate CSS styles. The automated E2E tests run via Playwright (located in the e2e-tests sub-folder) must simulate the user journey of downloading various files from the webmail.

**Business Context:** The end-user interface. Must handle the visual states: Green (Allowed), Red (Blocked), Orange (Warning with a side panel).

**Responsibility:** In this P0 scope, upload and analyze files from the popup (no content-script download interception yet).

## What It Does

- Exposes a popup UI (browser action).
- Lets the user drag-and-drop a file (or click to pick one).
- Automatically resolves JWT from the active authenticated browser tab session.
- Sends file to backend `POST /api/v1/analyze` with Bearer JWT.
- Waits for verdict on `WS /api/v1/ws/{job_id}?token=<JWT>`.
- Displays final state:
  - `allowed`
  - `blocked`
  - `warning`
  - timeout

No content scripts, no download interception, no provider-specific parsing.

## Settings

Stored in `chrome.storage.local` from popup fields:

- `apiBaseUrl`
- `cachedJwtToken` (auto-discovered)

## Automatic Token Resolution

The backend specification requires an SSO-issued JWT and does not issue tokens itself.
The popup therefore auto-discovers a JWT from the active tab context (session/local storage, cookie string, URL),
caches it, and reuses it while valid.

If no valid token is found:
- Open an authenticated corporate SSO/webmail tab
- Re-open popup and retry

## Run

```bash
cd apps/frontend
npm install
npm run dev
```

## Build

```bash
npm run build
```

## Quality Checks

```bash
npm run typecheck
npm run test:unit
```
**Kafka Events (Consumed/Produced):** N/A (communicates with the Backend via REST API / WebSockets).
