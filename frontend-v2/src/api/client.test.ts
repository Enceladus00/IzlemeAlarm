import { http, HttpResponse } from 'msw';
import { z } from 'zod';
import { API, server } from '@/test/server';
import { ApiError, apiRequest, buildUrl, configureApiClient } from './client';

describe('buildUrl', () => {
  it('prefixes /api and drops empty query values', () => {
    expect(buildUrl('/alerts', { status: 'new', severity: '', rule_code: undefined, limit: 50, x: null })).toBe(
      '/api/alerts?status=new&limit=50',
    );
  });
});

describe('apiRequest', () => {
  let unauthorized: ReturnType<typeof vi.fn<() => void>>;

  beforeEach(() => {
    unauthorized = vi.fn<() => void>();
    configureApiClient({ getToken: () => 'abc', onUnauthorized: unauthorized });
  });

  it('sends the bearer token and parses JSON with a schema', async () => {
    server.use(
      http.get(`${API}/thing`, ({ request }) =>
        HttpResponse.json({ auth: request.headers.get('Authorization') }),
      ),
    );
    const result = await apiRequest('/thing', { schema: z.object({ auth: z.string() }) });
    expect(result.auth).toBe('Bearer abc');
  });

  it('encodes form bodies as application/x-www-form-urlencoded', async () => {
    server.use(
      http.post(`${API}/form`, async ({ request }) =>
        HttpResponse.json({ type: request.headers.get('Content-Type'), body: await request.text() }),
      ),
    );
    const result = await apiRequest<{ type: string; body: string }>('/form', {
      method: 'POST',
      form: { username: 'a b', password: 'p&w' },
    });
    expect(result.type).toBe('application/x-www-form-urlencoded');
    expect(result.body).toBe('username=a+b&password=p%26w');
  });

  it('ends the session on 401 unless told not to', async () => {
    server.use(http.get(`${API}/secure`, () => HttpResponse.json({ detail: 'expired' }, { status: 401 })));
    await expect(apiRequest('/secure')).rejects.toMatchObject({ kind: 'unauthorized', detail: 'expired' });
    expect(unauthorized).toHaveBeenCalledTimes(1);

    await expect(apiRequest('/secure', { handleUnauthorized: false })).rejects.toBeInstanceOf(ApiError);
    expect(unauthorized).toHaveBeenCalledTimes(1);
  });

  it('maps 403 and keeps the server detail', async () => {
    server.use(
      http.get(`${API}/forbidden`, () =>
        HttpResponse.json({ detail: 'Permission required: rule:edit.' }, { status: 403 }),
      ),
    );
    await expect(apiRequest('/forbidden')).rejects.toMatchObject({
      status: 403,
      kind: 'forbidden',
      detail: 'Permission required: rule:edit.',
    });
  });

  it('flattens FastAPI 422 validation arrays into field errors', async () => {
    server.use(
      http.patch(`${API}/alerts/1/status`, () =>
        HttpResponse.json(
          { detail: [{ loc: ['body', 'note'], msg: 'String should have at most 2000 characters', type: 'x' }] },
          { status: 422 },
        ),
      ),
    );
    const error = await apiRequest('/alerts/1/status', { method: 'PATCH', json: {} }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).fieldErrors).toEqual([
      { location: 'note', message: 'String should have at most 2000 characters' },
    ]);
  });

  it('reports network failures', async () => {
    server.use(http.get(`${API}/down`, () => HttpResponse.error()));
    await expect(apiRequest('/down')).rejects.toMatchObject({ status: 0, kind: 'network' });
  });

  it('rejects responses that do not match the schema', async () => {
    server.use(http.get(`${API}/shape`, () => HttpResponse.json({ total: 'many' })));
    vi.spyOn(console, 'error').mockImplementation(() => {});
    await expect(apiRequest('/shape', { schema: z.object({ total: z.number() }) })).rejects.toMatchObject({
      kind: 'invalidResponse',
    });
  });
});
