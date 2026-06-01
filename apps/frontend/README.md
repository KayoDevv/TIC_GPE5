# Frontend

**Tech:** Vue 3 + WXT (TypeScript, Tailwind). Playwright for E2E tests.

**Code Guidelines:** Extension for Google Chrome and Microsoft Edge complying with Manifest V3. Uses the Shadow DOM to isolate CSS styles. The automated E2E tests run via Playwright (located in the e2e-tests sub-folder) must simulate the user journey of downloading various files from the webmail.

**Business Context:** The end-user interface. Must handle the visual states: Green (Allowed), Red (Blocked), Orange (Warning with a side panel).

**Responsibility:** Automatically intercept the download click via the content scripts.

**Kafka Events (Consumed/Produced):** N/A (communicates with the Backend via REST API / WebSockets).
