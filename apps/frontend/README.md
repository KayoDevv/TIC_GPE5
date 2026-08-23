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

- Exposes a popup UI (browser action) with `File` / `Hash` / `URL` tabs — only `File` is
  implemented, the others render a placeholder.
- Lets the user drag-and-drop a file or click the drop zone to browse.
- Shows the selected file (glyph, name, size) and waits for an explicit **Start analysis**.
- Automatically resolves a JWT from the active authenticated browser tab session.
- Sends the file to `POST /api/v1/analyze` with a Bearer JWT.
- Waits for the verdict on `WS /api/v1/ws/{job_id}?token=<JWT>` while showing the scanning state
  (pipeline layers + elapsed time against the analysis deadline).
- Renders the outcome:
  - `allowed` → Clean (green)
  - `warning` → Suspicious (orange)
  - `blocked` → Malicious (red)
  - timeout → Timed out, presented with the suspicious tone
  - failure → error panel with **Retry** / **Choose another file**

No content scripts, no download interception, no provider-specific parsing.

## UI Architecture

The design layer is isolated from the analysis layer. `src/p0/` is the working layer (transport,
JWT, settings) and is **never** imported from a component: only `src/ui/useAnalysisSession.ts`
talks to it.

```
entrypoints/popup/
  App.vue                     composition + phase routing only
  style.css                   reset, popup sizing, animated backdrop
src/ui/
  theme.css                   design tokens (colour, radius, spacing, motion, blur)
  useAnalysisSession.ts       popup state machine over src/p0
  verdictPresentation.ts      verdict payload -> tone, label, metrics
  fileSize.ts fileTypes.ts    file card formatting
  analysisTabs.ts pipelineLayers.ts extensionVersion.ts
  components/                 GlassShell, PopupHeader, AnalysisTabs, FileDropZone,
                              SelectedFileCard, GlassButton, ScanningOrb, AnalysisProgress,
                              VerdictPanel, AnalysisErrorPanel, ComingSoonPanel, PopupFooter
  icons/                      inline SVG components (stroked with `currentColor`)
```

Rules:

- **Tokens over literals.** Colours, radii, spacing, motion and shadows come from `theme.css`.
  A component may only hand-tune a value that is genuinely local to it.
- **Components are presentational.** They take props and emit events; no network, no storage, no
  `chrome.*` access outside `src/ui/extensionVersion.ts`.
- **One phase, one panel.** `App.vue` maps the session phase to a single panel component.
- **No remote assets.** Manifest V3 forbids remote code and stylesheets: fonts are system stacks,
  icons are inline SVG.

The design comes from the mock in `maquette/`. Deviations are deliberate:

- All copy is English (`docs/CONTRIBUTING.md` §1); the mock is French.
- The mock's third-party engine list and its simulated progress are replaced by the real analysis
  layers and by elapsed time against the analysis deadline.
- The mock's "full report" action is dropped — no such endpoint exists.
- Result metrics are rendered only for the fields the verdict layer actually reported.

## Settings

Stored in `chrome.storage.local`:

- `apiBaseUrl` (from `VITE_API_BASE_URL`)
- `cachedJwtToken` (auto-discovered)

## Automatic Token Resolution

The backend specification requires an SSO-issued JWT and does not issue tokens itself.
The popup therefore auto-discovers a JWT from the active tab context (session/local storage, cookie
string, URL), caches it, and reuses it while valid. The footer reports which source was used.

If no valid token is found:

- Open an authenticated corporate SSO/webmail tab
- Re-open the popup and retry

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
