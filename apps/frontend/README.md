# Frontend

Browser extension popup for the Charon file-analysis flow.

**Tech:** Vue 3 + WXT (TypeScript). Styling is scoped SFC CSS on shared design tokens — no CSS
framework. Vitest for unit and component tests, Playwright for E2E.

**Code Guidelines:** Extension for Google Chrome and Microsoft Edge complying with Manifest V3.
Components injected into a page (future content-script scope) must use the Shadow DOM to isolate
styles; the popup is its own document and does not need it. The automated E2E tests run via
Playwright (located in the e2e-tests sub-folder) must simulate the user journey of downloading
various files from the webmail.

**Business Context:** The end-user interface. Must handle the visual states: Green (Allowed), Red
(Blocked), Orange (Warning with the explanation produced by the LLM layer).

**Responsibility:** In the current scope, upload and analyse files from the popup (no
content-script download interception yet).

## What It Does

- Exposes a popup UI (browser action) with `Analysis` / `History` tabs and a light/dark theme
  toggle (persisted).
- Lets the user drag-and-drop a file or click the drop zone to browse; the analysis starts as soon
  as a file is picked.
- Automatically resolves a JWT from the active authenticated browser tab session.
- Sends the file to `POST /api/v1/analyze` with a Bearer JWT. A manual upload has no email, so the
  `sender` field is the signed-in user (the JWT's `email`, `preferred_username` or `sub`) and the
  subject names the file. Real email context arrives with webmail attachment interception.
- Waits for the verdict on `WS /api/v1/ws/{job_id}?token=<JWT>` while showing the scanning state
  (pipeline layers + elapsed time against the analysis deadline).
- Renders the outcome:
  - `allowed` → Clean (green)
  - `warning` → Suspicious (orange)
  - `blocked` → Malicious (red)
  - timeout → Timed out, presented with the suspicious tone
  - failure → error panel with **Retry** / **Choose another file**, showing the backend's own
    reason when it gives one; a verdict channel that closes early fails at once instead of
    waiting out the deadline
- Folds the technical summary (risk score, indicators with their MITRE ATT&CK code, threat model and
  sandbox badges) behind **Show details**.
- Keeps the last 20 verdicts in the `History` tab.
- Mirrors the state on the toolbar icon (idle / analysing / allowed / warning / blocked). The
  background worker resets it to idle when the popup closes, since the analysis lives in the popup.

No content scripts, no download interception, no provider-specific parsing.

## UI Architecture

The design layer is isolated from the analysis layer. `src/p0/` is the working layer (transport,
JWT, settings, history and theme storage) and is **never** imported from a component: only the
`src/ui/use*.ts` composables talk to it.

```
entrypoints/
  background.ts               toolbar icon per state
  popup/App.vue               composition + phase routing only
  popup/style.css             reset, popup sizing
public/icons/eye/             toolbar icon PNGs, one per state and size
src/ui/
  theme.css                   design tokens (palette light/dark, fonts, spacing, motion)
  useAnalysisSession.ts       popup state machine over src/p0
  useTheme.ts                 light/dark preference
  charonState.ts              popup state -> lockup colour + toolbar icon
  verdictPresentation.ts      verdict payload -> tone, label, details
  fileSize.ts analysisTabs.ts pipelineLayers.ts extensionVersion.ts
  components/                 PopupShell, PopupHeader, AnalysisTabs, FileDropZone,
                              AnalysisProgress, VerdictPanel, AnalysisErrorPanel, HistoryPanel,
                              PopupButton, PopupFooter
  icons/                      CharonGlyph (inline SVG stroked with `currentColor`)
```

Rules:

- **Tokens over literals.** Colours, radii, spacing, motion and shadows come from `theme.css`.
  A component may only hand-tune a value that is genuinely local to it.
- **Components are presentational.** They take props and emit events; no network, no storage, no
  `chrome.*` access outside `src/ui/extensionVersion.ts`.
- **One phase, one panel.** `App.vue` maps the session phase to a single panel component.
- **No remote assets.** Fonts (Cinzel, Spectral, Space Mono) are bundled from `@fontsource`, icons
  are inline SVG or packaged PNGs.

The design comes from the Charon V5 mockup (a standalone MV3 prototype). Deviations are deliberate:

- All copy is English (`docs/CONTRIBUTING.md` §1); the mock is French.
- Only the popup is built. The mock's options page, in-page pin, demo (mock) verdicts, runtime
  backend URL and download interception are not: the API URL is fixed at build time and the
  prototype's verdicts were simulated from the file name.
- The mock's "reason" line (derived client-side from a guessed decision matrix) is replaced by the
  file name and size.
- Progress keeps the real analysis layers and the elapsed time against the analysis deadline.
- Result details are rendered only for the fields the verdict layer actually reported; indicators
  read the real IOC shape (`mitre_tactic`, `description`, falling back to `type`, `value`).

## Settings

Stored in `chrome.storage.local`:

- `apiBaseUrl` (from `VITE_API_BASE_URL`)
- `cachedJwtToken` (auto-discovered)
- `charonHistory` (last 20 verdicts: file name, decision, risk score, time)
- `theme` (`light` or `dark`)

## Automatic Token Resolution

The backend specification requires an SSO-issued JWT and does not issue tokens itself.
The popup auto-discovers a JWT from the active tab context (session/local storage, cookie string,
URL), caches it, and reuses it while valid.

The popup never refuses to call the API for lack of a token: the backend owns that decision. When
no token is found it sends the `anonymous` marker instead. The backend accepts it while
`AUTH_DEV_MODE` is on (SSO/JWKS not wired yet) and answers 401 once real JWT verification is
enforced, which the popup then shows as the error.

## Run

```bash
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

**Kafka Events (Consumed/Produced):** N/A (communicates with the Backend via REST API /
WebSockets).
