import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { dashboardFixture, latestAlertsFixture, systemOverviewFixture } from './fixtures';

export const API = 'http://localhost:3000/api';

export const ADMIN_PERMISSIONS = [
  'alert:update',
  'alert:view',
  'audit:view',
  'customer:view',
  'dashboard:view',
  'role:manage',
  'rule:edit',
  'rule:view',
  'upload:create',
  'upload:view',
  'user:manage',
];
export const ANALYST_PERMISSIONS = ['alert:update', 'alert:view', 'dashboard:view'];

/** Users accepted by the mock /auth/login. Password is always "secret". */
export const MOCK_USERS: Record<string, { role_code: string; permissions: string[] }> = {
  admin: { role_code: 'admin', permissions: ADMIN_PERMISSIONS },
  'ayse.karaca': { role_code: 'analyst', permissions: ANALYST_PERMISSIONS },
  nobody: { role_code: 'analyst', permissions: [] },
  viewer: { role_code: 'auditor', permissions: ['dashboard:view'] },
};

/** Token format used by the mocks: "token-<username>". */
export function tokenFor(username: string): string {
  return `token-${username}`;
}

function userFromRequest(request: Request): string | null {
  const header = request.headers.get('Authorization') ?? '';
  const match = /^Bearer token-(.+)$/.exec(header);
  return match && match[1]! in MOCK_USERS ? match[1]! : null;
}

export const handlers = [
  http.post(`${API}/auth/login`, async ({ request }) => {
    const form = new URLSearchParams(await request.text());
    const username = form.get('username') ?? '';
    if (!(username in MOCK_USERS) || form.get('password') !== 'secret') {
      return HttpResponse.json({ detail: 'Incorrect username or password.' }, { status: 401 });
    }
    return HttpResponse.json({ access_token: tokenFor(username), token_type: 'bearer', expires_in: 1800 });
  }),
  http.get(`${API}/auth/me`, ({ request }) => {
    const username = userFromRequest(request);
    if (!username) {
      return HttpResponse.json({ detail: 'Invalid or expired authentication token.' }, { status: 401 });
    }
    return HttpResponse.json({ username, ...MOCK_USERS[username] });
  }),
  http.get(`${API}/health`, () => HttpResponse.json({ status: 'ok', database: 'connected' })),
  http.get(`${API}/dashboard/summary`, () => HttpResponse.json(dashboardFixture)),
  http.get(`${API}/alerts`, () => HttpResponse.json(latestAlertsFixture)),
  http.get(`${API}/admin/system-overview`, () => HttpResponse.json(systemOverviewFixture)),
];

export const server = setupServer(...handlers);
