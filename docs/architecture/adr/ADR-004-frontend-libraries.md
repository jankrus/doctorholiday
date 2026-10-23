# ADR-004: Frontend Libraries and Toolchain

## 1. Context
ADR-001 fixes React 18, Vite 5, ESLint 8 and Vitest for the frontend but leaves open the UI components, routing and
how the browser talks to the API. The frontend skeleton (#23) needs these decisions, and every later frontend
ticket (#24-#27) builds on them. Each added package becomes part of the SBOM and the SCA scan, so the dependency
set should stay small.

## 2. Considered Options

### 2.1. UI components
*   **Option A: Radix Themes**
    *   *Pros:* Complete, accessible component set (focus management, keyboard navigation, ARIA) with a consistent
        look out of the box. Styling ships as one prebuilt CSS file; no CSS-in-JS runtime injects `<style>` tags,
        which keeps a strict `style-src` CSP (#27) possible. One runtime package.
    *   *Cons:* Larger stylesheet (≈ 80 kB gzipped); styling is limited to the theme's tokens and props.
*   **Option B: Radix Primitives + Tailwind CSS (e.g. via shadcn/ui)**
    *   *Pros:* Full control over styling; component source is copied into the repo.
    *   *Cons:* More code to own and review, an additional build toolchain (Tailwind), and the scroll-lock helper
        of some primitives injects `<style>` tags at runtime.

### 2.2. API client
*   **Option A: `openapi-typescript` + `openapi-fetch`**
    *   *Pros:* Types are generated from `backend/openapi.yaml`, so request and response shapes cannot drift from
        the contract unnoticed. The runtime part is a thin `fetch` wrapper without dependencies.
    *   *Cons:* Generated file must be regenerated when the contract changes.
*   **Option B: Hand-written `fetch` calls with hand-written types**
    *   *Pros:* No dependency.
    *   *Cons:* Types duplicate the contract and drift silently.

### 2.3. Routing
*   **Option A: React Router 7 (data mode)**
    *   *Pros:* De-facto standard; loaders run before a page renders, so route guards redirect without
        flashing protected screens. Supports React 18.
    *   *Cons:* React Router 8 already requires React 19, so a React upgrade will bring a router migration.

### 2.4. QR code for MFA enrolment (added with #24)
The `otpauth://` URI contains the TOTP secret, so the QR code must be generated in the browser; a QR web
service would receive the secret.
*   **Option A: `uqr`**
    *   *Pros:* No dependencies, MIT, about 80 kB unpacked, TypeScript types. `encode()` returns the module
        matrix, which React renders as an SVG `<path>`: no `innerHTML`, no canvas, no data URL.
    *   *Cons:* Version 0.x from a small maintainer group (unjs).
*   **Option B: `qrcode` (node-qrcode)**
    *   *Pros:* Most widely used.
    *   *Cons:* Pulls in `pngjs`, `yargs` and `dijkstrajs` (CLI and PNG support the browser does not need).
*   **Option C: `qrcode-generator`**
    *   *Pros:* No dependencies, mature.
    *   *Cons:* About 550 kB unpacked, no own types.
*   **Option D: Own encoder**
    *   *Pros:* No dependency.
    *   *Cons:* Reed-Solomon coding and masking are easy to get subtly wrong; a broken code locks users out.

## 3. Decision Outcome
*   **UI:** Radix Themes (`@radix-ui/themes`), no Tailwind.
*   **Routing:** React Router 7 in data mode (`createBrowserRouter`); guards are loaders based on
    `GET /api/v1/auth/me` and are UX only, since the backend authorises every request.
*   **API client:** `openapi-typescript` (dev) generates `frontend/src/api/schema.d.ts`; `openapi-fetch` sends
    same-origin requests with `credentials: 'include'`. Error texts shown to users come from a fixed local map,
    never from the server's `message`.
*   **QR code:** `uqr`, pinned like every package; rendered as SVG in `frontend/src/components/QrCode.tsx`.
*   **Tooling:** TypeScript 5, ESLint 8 (flat config) with `typescript-eslint` and `eslint-plugin-react-hooks`,
    Prettier, Vitest with jsdom and Testing Library.

### 3.1. Deviation from ADR-001: Vite 8 and Vitest 5 instead of Vite 5 and Vitest 3
`npm audit` reports advisories against the latest Vite 5 (5.4.21) and Vitest 3 (3.2.7) that are fixed only in
newer majors, among them HIGH (Vite: path traversal, files outside `server.fs.allow` served) and CRITICAL
(Vitest/tinypool: prototype pollution to RCE). These packages are build and test tools and never reach the
nginx image, but they run on developer machines and in CI. Starting a security-focused project on known
vulnerable tooling contradicts the quality gate's intent (CVSS ≥ 7.0 blocks), so the frontend uses Vite 8,
`@vitejs/plugin-react` 6 and Vitest 5. React stays at 18 and ESLint at 8 as decided in ADR-001.

## 4. Consequences
*   **Security (Pros):** `npm audit` is clean at the time of writing. Only six direct runtime packages
    (`react`, `react-dom`, `react-router`, `@radix-ui/themes`, `openapi-fetch`, `uqr` and their transitive deps)
    end up in the bundle. ESLint forbids `dangerouslySetInnerHTML`, `eval` and similar escape hatches. No secrets or
    API keys exist in the frontend; the build reads no `VITE_*` variables.
*   **Development (Cons):** Node.js ≥ 22.13 is required (Vitest 5, jsdom 29). ESLint 8 is end of life; moving to
    ESLint 9+ needs a follow-up decision. The Radix Themes stylesheet is large; it can be split into its token,
    component and utility parts if bundle size becomes a problem.
