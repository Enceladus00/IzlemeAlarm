# Sentinel — React interface (`frontend-v2`)

A React rewrite of the Streamlit UI. It is a pure client of the existing
FastAPI API: it does not change backend behaviour, and the Streamlit UI in
`frontend/` stays available.

## Run

Start the API first (see the root README), then:

```powershell
npm install
npm run dev        # http://localhost:5173
```

The dev server proxies `/api/*` to `VITE_API_PROXY_TARGET`
(default `http://127.0.0.1:8000`) and strips the `/api` prefix. Copy
`.env.example` to `.env` to point at a different API.

| Script | Purpose |
| --- | --- |
| `npm run dev` | Development server with hot reload |
| `npm run build` | Typecheck and production build into `dist/` |
| `npm run preview` | Serve the production build (same `/api` proxy) |
| `npm test` | Unit, component, and accessibility tests (Vitest, Testing Library, MSW, axe-core) |
| `npm run typecheck` / `npm run lint` | TypeScript and ESLint checks |

## Container

From the repository root:

```powershell
docker build -f Dockerfile.frontend-v2 -t sentinel-frontend-v2 .
docker run -p 8080:8080 -e API_UPSTREAM=http://host.docker.internal:8000 sentinel-frontend-v2
```

nginx serves the build on `PORT` (default 8080), falls back to `index.html`
for app routes, caches hashed assets for a year, and proxies `/api/*` to
`API_UPSTREAM` (default `http://backend:8000`) without the prefix.

## Tests

Tests run against a mocked API (MSW) whose handlers apply the same filters and
paging as the real endpoints, so they check the requests the UI sends as well
as what it renders. `src/app/a11y.test.tsx` runs axe-core (WCAG 2.1 A/AA) on
every screen; colour contrast is not measurable in jsdom and is covered by the
validated chart palette and manual review in both themes.

## Stack

Vite, React, TypeScript (strict), React Router, TanStack Query, zod (response
validation at the API boundary), react-hook-form, i18next, Tailwind CSS, and
Radix UI primitives.

## Conventions

- **Authorization:** the API is the authorization boundary. Navigation and
  route guards in `src/app/navigation.ts` mirror the Streamlit permission
  checks only to hide screens that would fail; every API call still enforces
  its own permission, and a 403 is shown as a permission error.
- **Session:** the access token is kept in memory and mirrored to
  `sessionStorage`. A refresh keeps the session; closing the tab ends it.
  Tokens last 30 minutes and cannot be refreshed. The UI signs out when the
  token expires or the API returns 401.
- **Language:** Turkish is the default. The choice is saved per browser in
  `localStorage` (`sentinel.lang`). `src/i18n/locales/tr.ts` is the source of
  truth, and `en.ts` must match its shape (enforced by `tsc`). Numbers and
  dates use `Intl` with the active locale. API timestamps have no timezone and
  are displayed as recorded.
- **Theme:** light by default, with a dark mode toggle saved in
  `localStorage` (`sentinel.theme`). Colours are semantic CSS variables in
  `src/index.css`.
- **Placeholders:** where a design calls for data the API does not provide,
  the value is rendered with `<Placeholder>`. It has a dashed purple style and
  a "Placeholder" label, so it is never mistaken for real data.

## Layout

```
src/
  app/         shell, routes, navigation config, guards, providers
  api/         fetch client (ApiError, 401 handling) and zod schemas
  auth/        AuthProvider, session storage, login page, permissions
  features/    one folder per screen (pages, hooks, components, tests)
  components/  shared UI kit
  i18n/        i18next setup and tr/en resources
  theme/       light/dark theme provider
  utils/       formatting and error helpers
  test/        Vitest setup, MSW server, render helpers
```

## Placeholders

These design elements have no data source in the API today. Each is shown
with the `<Placeholder>` marker; filling them would need API changes.

| Screen | Element | What the API would need to provide |
| --- | --- | --- |
| Alert queue | "Bugün kararlaştırdığım" (decided by me today) | Who changed an alert's status (actor on alert history) |
| Alert queue | "Bana geri gönderilen" (sent back to me) | An assignment / send-back workflow |
| Alert queue | "Son işlem yapan" (last actor) column | Actor on alert history |
| Alert queue | Customer type under each customer | `customer_type` in the alert summary |
| Alert detail | "İşlemi yapan" in the analyst history | Actor on alert history |
| System overview | Schema "Güncel" (up to date) | Whether the revision is the latest migration |

Other API limits the UI works around:

- Customer search in the alert queue matches the loaded alerts only; the API
  filters by exact customer number, not by name.
- Every alert filter takes one value (no multi-select).
- Upload reports are looked up by batch number; there is no upload history list.
- The audit log has no server-side filters; actor names are resolved through
  `/users` when the viewer has `user:manage`, otherwise the actor id is shown.
