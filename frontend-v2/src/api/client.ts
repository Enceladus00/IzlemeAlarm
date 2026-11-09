import type { z } from 'zod';

/** All API calls go through the same-origin /api prefix (see vite.config.ts / nginx). */
export const API_BASE = '/api';

export type ApiErrorKind =
  | 'network'
  | 'unauthorized'
  | 'forbidden'
  | 'notFound'
  | 'conflict'
  | 'tooLarge'
  | 'rateLimited'
  | 'validation'
  | 'unavailable'
  | 'invalidResponse'
  | 'unexpected';

/** One field-level problem from a FastAPI 422 validation response. */
export interface ApiFieldError {
  location: string;
  message: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly kind: ApiErrorKind;
  /** Server-provided message (English) when the API returned one. */
  readonly detail: string | null;
  readonly fieldErrors: ApiFieldError[];
  /** POST /alerts/decisions names the alert that failed a check. */
  readonly alertId: number | null;
  /** 429 responses: seconds until the API accepts this request again. */
  readonly retryAfter: number | null;

  constructor(options: {
    status: number;
    kind: ApiErrorKind;
    detail?: string | null;
    fieldErrors?: ApiFieldError[];
    alertId?: number | null;
    retryAfter?: number | null;
  }) {
    super(options.detail ?? options.kind);
    this.name = 'ApiError';
    this.status = options.status;
    this.kind = options.kind;
    this.detail = options.detail ?? null;
    this.fieldErrors = options.fieldErrors ?? [];
    this.alertId = options.alertId ?? null;
    this.retryAfter = options.retryAfter ?? null;
  }
}

export function kindForStatus(status: number): ApiErrorKind {
  if (status === 401) return 'unauthorized';
  if (status === 403) return 'forbidden';
  if (status === 404) return 'notFound';
  if (status === 409) return 'conflict';
  if (status === 413) return 'tooLarge';
  if (status === 429) return 'rateLimited';
  if (status === 422 || status === 400) return 'validation';
  if (status === 503 || status === 502 || status === 504) return 'unavailable';
  return 'unexpected';
}

/** FastAPI returns `detail` as a string, or as a list of validation issues for 422. */
interface ParsedError {
  detail: string | null;
  fieldErrors: ApiFieldError[];
  alertId?: number | null;
}

function parseErrorBody(body: unknown): ParsedError {
  if (!body || typeof body !== 'object' || !('detail' in body)) {
    return { detail: null, fieldErrors: [] };
  }
  const alertId = (body as { alert_id?: unknown }).alert_id;
  if (typeof alertId === 'number') {
    return { ...parseErrorBody({ detail: (body as { detail: unknown }).detail }), alertId };
  }
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail === 'string') return { detail, fieldErrors: [] };
  if (Array.isArray(detail)) {
    const fieldErrors = detail.flatMap((item): ApiFieldError[] => {
      if (!item || typeof item !== 'object') return [];
      const { loc, msg } = item as { loc?: unknown; msg?: unknown };
      return [
        {
          location: Array.isArray(loc) ? loc.filter((part) => part !== 'body').join('.') : '',
          message: typeof msg === 'string' ? msg : String(msg),
        },
      ];
    });
    return {
      detail: fieldErrors.map((error) => `${error.location}: ${error.message}`).join('; ') || null,
      fieldErrors,
    };
  }
  return { detail: null, fieldErrors: [] };
}

// --- Session hooks, registered by AuthProvider -----------------------------

type TokenGetter = () => string | null;
type UnauthorizedHandler = () => void;

let getToken: TokenGetter = () => null;
let onUnauthorized: UnauthorizedHandler = () => {};

export function configureApiClient(options: {
  getToken: TokenGetter;
  onUnauthorized: UnauthorizedHandler;
}): void {
  getToken = options.getToken;
  onUnauthorized = options.onUnauthorized;
}

// --- Request ---------------------------------------------------------------

export type QueryValue = string | number | boolean | null | undefined;

export interface RequestOptions<T> {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  query?: Record<string, QueryValue>;
  /** JSON body. */
  json?: unknown;
  /** application/x-www-form-urlencoded body (used by /auth/login). */
  form?: Record<string, string>;
  /** multipart body (used by /uploads). */
  formData?: FormData;
  /** zod schema the response must satisfy. */
  schema?: z.ZodType<T>;
  signal?: AbortSignal;
  /** When false, a 401 does not end the session (used by the login call). */
  handleUnauthorized?: boolean;
}

export function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined || value === null || value === '') continue;
    params.append(key, String(value));
  }
  const search = params.toString();
  return `${API_BASE}${path}${search ? `?${search}` : ''}`;
}

export async function apiRequest<T = unknown>(
  path: string,
  options: RequestOptions<T> = {},
): Promise<T> {
  const { method = 'GET', query, json, form, formData, schema, signal } = options;
  const handleUnauthorized = options.handleUnauthorized ?? true;
  const headers: Record<string, string> = { Accept: 'application/json' };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let body: BodyInit | undefined;
  if (json !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(json);
  } else if (form) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded';
    body = new URLSearchParams(form).toString();
  } else if (formData) {
    body = formData; // The browser sets the multipart boundary.
  }

  let response: Response;
  try {
    const url = new URL(buildUrl(path, query), window.location.origin);
    response = await fetch(url, { method, headers, body, signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError({ status: 0, kind: 'network' });
  }

  if (!response.ok) {
    let parsed: ParsedError = {
      detail: null,
      fieldErrors: [],
    };
    try {
      parsed = parseErrorBody(await response.json());
    } catch {
      // Non-JSON error body; fall back to the status-based message.
    }
    if (response.status === 401 && handleUnauthorized) onUnauthorized();
    throw new ApiError({
      status: response.status,
      kind: kindForStatus(response.status),
      retryAfter: Number(response.headers.get('Retry-After')) || null,
      ...parsed,
    });
  }

  if (response.status === 204) return undefined as T;
  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new ApiError({ status: response.status, kind: 'invalidResponse' });
  }
  if (!schema) return data as T;
  const result = schema.safeParse(data);
  if (!result.success) {
    if (import.meta.env.DEV) {
      console.error(`Unexpected response shape from ${method} ${path}`, result.error.issues);
    }
    throw new ApiError({
      status: response.status,
      kind: 'invalidResponse',
      detail: result.error.issues
        .slice(0, 3)
        .map((issue) => `${issue.path.join('.')}: ${issue.message}`)
        .join('; '),
    });
  }
  return result.data;
}
