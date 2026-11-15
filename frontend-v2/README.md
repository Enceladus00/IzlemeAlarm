# frontend-v2: React interface

The browser interface of IzlemeAlarm (shown to users as Sentinel). It is a
client of the FastAPI backend and holds no business rules of its own: every
permission, validation and calculation that matters happens in the API. For
the system as a whole see [../PROJECT_GUIDE.md](../PROJECT_GUIDE.md); section
14 lists the screens.

## Running

Start the API first (see the root README), then:

```powershell
npm install
npm run dev        # http://localhost:5173
```

The dev server listens on port 5173 only (`strictPort`) and forwards `/api/*`
to `VITE_API_PROXY_TARGET` (default `http://127.0.0.1:8000`) with the prefix
removed. To use another API, copy `.env.example` to `.env` and change the
target.

| Script | Does |
| --- | --- |
| `npm run dev` | Development server with hot reload |
| `npm run build` | Type check, then production build into `dist/` |
| `npm run preview` | Serve the production build, with the same `/api` proxy |
| `npm test` | All tests once (Vitest) |
| `npm run test:watch` | Tests in watch mode |
| `npm run typecheck` | `tsc -b --noEmit` |
| `npm run lint` | ESLint |
| `npm run format` | Prettier over `src/` |

CI runs `npm ci`, `tsc -b`, `npm run lint` and `vitest run` on Node 22 for
every push.

## Container

From the repository root:

```powershell
docker build -f Dockerfile.frontend-v2 -t izlemealarm-ui .
docker run -p 8080:8080 -e API_UPSTREAM=http://host.docker.internal:8000 izlemealarm-ui
```

The image builds with Node 22 and serves `dist/` from nginx 1.27
(`nginx.conf.template`, filled from the environment at start-up):

- `/api/*` goes to `API_UPSTREAM` (default `http://backend:8000`) without the
  prefix. The upstream name is resolved again every 30 seconds, and an `https`
  upstream must present a valid certificate.
- nginx sends the caller's address as `X-Client-Address` with
  `X-Proxy-Secret` (`PROXY_SHARED_SECRET`), so the API's rate limits count the
  real client. Set the same secret on both sides.
- Request bodies up to 6 MB, read timeout 120 seconds.
- Unknown paths serve `index.html`, which is never cached; hashed files under
  `/assets/` are cached for a year.
- Every response carries `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY` and `Referrer-Policy: same-origin`.

In production the image runs as the ECS Express service
`izlemealarm-frontend`, deployed by `.github/workflows/deploy-frontend.yml`
(guide, section 18).

## Stack

| Concern | Library |
| --- | --- |
| Build | Vite 8, TypeScript 5.9 (strict) |
| UI | React 19, Tailwind CSS 4, Radix UI (dialog, popover), lucide icons, IBM Plex fonts |
| Routing | React Router 7 |
| Server data | TanStack Query 5 |
| API validation | zod 4 |
| Forms | react-hook-form |
| Text | i18next, Turkish and English |
| Tests | Vitest 5, Testing Library, MSW 2, axe-core, jsdom |

## Code layout

```text
src/
  app/         shell, routes, navigation and guards, providers, query client, session countdown
  api/         fetch client (ApiError, 401 handling) and one zod schema per response
  auth/        AuthProvider, session storage, login page, permission names
  features/    one folder per screen: page, api.ts (query hooks), components, tests
  components/  shared UI kit (ui/) and charts (charts/)
  i18n/        i18next setup; locales/tr.ts and locales/en.ts
  theme/       light and dark theme provider
  utils/       formatting, errors, CSV templates
  test/        Vitest setup, MSW server and handlers, render helpers
```

The `@/` import alias points at `src/`.

## Conventions

**Authorisation.** The API is the authorisation boundary.
`src/app/navigation.ts` lists every screen with the permissions needed to open
it and to edit on it. The menu, the route guards and the landing page (the
first screen the user may open) all read that list. It only hides what would
fail anyway; a 403 from the API is still shown as a permission error.

**API boundary.** `src/api/client.ts` calls only same-origin `/api/...`. Every
response is parsed with its zod schema in `src/api/schemas/`, so a contract
change fails loudly instead of rendering wrong data. Change the schema in the
same commit as the backend response model (`backend/api/responses.py`).

**Server data.** TanStack Query treats responses as fresh for 30 seconds by
default, dashboards for 60 seconds, and rule codes and customer profiles for 5
minutes. Customer profiles also do not refetch on window focus, so revisiting
a tab does not add view-log rows. Only transient failures are retried, never
4xx answers or mutations. After a decision or a rule change the affected queries are
invalidated. Lists keep the previous page visible, dimmed, while the next one
loads.

**Money and numbers.** The API sends decimals as strings. Parse them with the
`decimal` helper in `src/api/schemas/common.ts` and sum money in integer cents
(BigInt), never as floats. Numbers and dates are formatted with `Intl` in the
active language. API timestamps have no time zone and are shown as recorded.

**Session.** The token is kept in memory and copied to `sessionStorage`:
refreshing the page keeps the session, closing the tab ends it. Tokens last 30
minutes and cannot be refreshed. The shell shows a countdown, and the app
signs out on expiry or on any 401.

**Text.** Every visible string lives in `src/i18n/locales/`. `tr.ts` is the
source of truth; `en.ts` must have the same shape, which `tsc` enforces.
Turkish is the default, and the choice is stored per browser under
`sentinel.lang`. API error messages arrive in English and are translated
through `errors.detail` in the locale files; the backend test
`tests/test_error_translations.py` fails when a message has no translation.

**Theme.** Light by default, dark on request, stored under `sentinel.theme`.
Colours are semantic CSS variables in `src/index.css`; chart colours come from
a palette checked for contrast in both themes.

**Personal data.** The interface shows what the API sends and never unmasks
anything. Masked labels and signed `account_ref` handles (network graph) come
from the server.

**Placeholders.** `components/ui/Placeholder.tsx` marks a value the design
calls for but the API does not provide yet: dashed purple, labelled
"Placeholder", so it cannot be mistaken for data. No screen uses it at
present.

## Tests

Tests run against a mocked API (MSW). The handlers in `src/test/` apply the
same filters and paging as the real endpoints, so a test checks the request
the screen sends as well as what it renders. A request without a handler fails
the test.

`src/app/a11y.test.tsx` runs axe-core (WCAG 2.1 A and AA) on every screen.
jsdom cannot measure colour contrast; that is covered by the chart palette and
by manual review in both themes.

## Known API limits the interface works around

- Alert list filters (`status`, `severity`, `rule_code`) take one value each;
  there is no multi-select.
- The flow diagram on the transaction screen shows at most the top 200 routes
  by amount, with masked account labels; counterparty names are not sent (K12).
- Transaction lists load 50 rows at a time and only once a customer or account
  is chosen; without a choice the screen shows per-currency totals.
