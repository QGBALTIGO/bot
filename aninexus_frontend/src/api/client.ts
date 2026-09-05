const API_BASE = import.meta.env.VITE_API_URL
  ? `${import.meta.env.VITE_API_URL}/api/${import.meta.env.VITE_API_PREFIX ?? 'v1_7b82'}`
  : `/api/${import.meta.env.VITE_API_PREFIX ?? 'v1_7b82'}`;

const REQUEST_TIMEOUT_MS = 12000;

const getTg = () => window.Telegram?.WebApp;

let sessionToken = sessionStorage.getItem('auth_token');

export const setSessionToken = (token: string | null) => {
  sessionToken = token;
  if (token) {
    sessionStorage.setItem('auth_token', token);
  } else {
    sessionStorage.removeItem('auth_token');
  }
};

interface ApiErrorInit {
  message: string;
  status?: number | undefined;
  code?: string | undefined;
  requestId?: string | undefined;
  details?: unknown;
  retryable?: boolean | undefined;
  cause?: unknown;
}

interface ApiRequestInit extends RequestInit {
  timeoutMs?: number | undefined;
}

class ApiError extends Error {
  status?: number | undefined;
  code: string;
  requestId?: string | undefined;
  details?: unknown;
  retryable: boolean;

  constructor(init: ApiErrorInit) {
    super(init.message);
    this.name = 'ApiError';
    this.status = init.status;
    this.code = init.code ?? 'request_failed';
    this.requestId = init.requestId;
    this.details = init.details;
    this.retryable = init.retryable ?? false;
    if (init.cause !== undefined) {
      (this as Error & { cause?: unknown }).cause = init.cause;
    }
  }
}

export const getErrorMessage = (error: unknown) => {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error && error.message) return error.message;
  if (typeof error === 'string' && error.trim()) return error;
  return 'Algo deu errado. Tente novamente.';
};

// Query-cache invalidation bus — replaces the old string-typed window events
// (gallery-refresh / harem-refresh / shop-refresh). Keys mirror useApi's
// ['api', endpoint, body] and useInfiniteGrid's ['grid', endpoint, ...] shapes.
export const invalidateQueries = (endpoints: string[]) => {
  window.dispatchEvent(
    new CustomEvent('query-invalidate', { detail: Array.from(new Set(endpoints)) }),
  );
};

interface RefreshSubscriber {
  resolve: (value: unknown) => void;
  reject: (reason?: unknown) => void;
  endpoint: string;
  options: ApiRequestInit;
  retries: number;
}

let isRefreshing = false;
let refreshSubscribers: RefreshSubscriber[] = [];

function subscribeToRefresh(endpoint: string, options: ApiRequestInit, retries: number) {
  return new Promise((resolve, reject) => {
    refreshSubscribers.push({ resolve, reject, endpoint, options, retries });
  });
}

function flushRefreshSubscribers() {
  refreshSubscribers.forEach(({ resolve, endpoint, options, retries }) => {
    resolve(apiFetch(endpoint, options, retries));
  });
  refreshSubscribers = [];
}

function rejectRefreshSubscribers(err: Error) {
  refreshSubscribers.forEach(({ reject }) => reject(err));
  refreshSubscribers = [];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function readString(value: unknown) {
  return typeof value === 'string' && value.trim() ? value : undefined;
}

function mergeHeaders(headers?: HeadersInit) {
  const merged: Record<string, string> = { 'Content-Type': 'application/json' };
  if (!headers) return merged;

  new Headers(headers).forEach((value, key) => {
    if (key.toLowerCase() === 'content-type') {
      delete merged['Content-Type'];
    }
    merged[key] = value;
  });
  return merged;
}

function requestIdFrom(response: Response) {
  return response.headers.get('X-Request-ID') ?? undefined;
}

function isRetriableStatus(status: number) {
  return status === 408 || status >= 500;
}

function isIdempotentRequest(options: RequestInit) {
  const method = (options.method ?? 'GET').toUpperCase();
  return method === 'GET' || method === 'HEAD' || method === 'OPTIONS';
}

function createRequestSignal(externalSignal?: AbortSignal | null, timeoutMs = REQUEST_TIMEOUT_MS) {
  const controller = new AbortController();
  let timedOut = false;
  const timeoutId = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  const abortFromExternal = () => controller.abort();
  if (externalSignal) {
    if (externalSignal.aborted) {
      abortFromExternal();
    } else {
      externalSignal.addEventListener('abort', abortFromExternal, { once: true });
    }
  }

  return {
    signal: controller.signal,
    didTimeout: () => timedOut,
    cleanup: () => {
      window.clearTimeout(timeoutId);
      externalSignal?.removeEventListener('abort', abortFromExternal);
    },
  };
}

async function parseResponseBody(response: Response): Promise<unknown> {
  if (response.status === 204) return null;

  const text = await response.text();
  if (!text) return null;

  const contentType = response.headers.get('content-type') ?? '';
  if (!contentType.includes('application/json')) return text;

  try {
    return JSON.parse(text);
  } catch (error) {
    throw new ApiError({
      message: 'Resposta inválida do servidor.',
      status: response.status,
      code: 'invalid_json',
      requestId: requestIdFrom(response),
      retryable: isRetriableStatus(response.status),
      cause: error,
    });
  }
}

function buildApiError(response: Response, payload: unknown) {
  const status = response.status;
  const statusMessages: Record<number, string> = {
    400: 'Solicitação inválida.',
    401: 'Sessão expirada. Reabra a MiniApp.',
    403: 'Acesso negado.',
    404: 'Recurso não encontrado.',
    409: 'A operação não pôde ser concluída.',
    429: 'Muitas tentativas. Aguarde um pouco.',
    500: 'Erro interno no servidor.',
    502: 'Serviço temporariamente indisponível.',
    503: 'Serviço temporariamente indisponível.',
  };
  let message = statusMessages[status] || `Erro da API: ${status}`;
  let code = status === 401 ? 'unauthorized' : 'request_failed';
  let requestId = requestIdFrom(response);
  let details: unknown;

  if (isRecord(payload)) {
    const error = payload.error;
    const detail = payload.detail;

    if (isRecord(error)) {
      message = readString(error.message) ?? message;
      code = readString(error.code) ?? code;
      requestId = readString(error.request_id) ?? requestId;
      details = error.details;
    }

    message = readString(detail) ?? readString(payload.message) ?? message;
    if (details === undefined && detail !== message) {
      details = detail;
    }
  } else {
    message = readString(payload) ?? message;
  }

  if (message === 'Internal Server Error') message = 'Erro interno no servidor.';
  if (message === 'Bad Gateway') message = 'Serviço temporariamente indisponível.';
  if (message === 'Service Unavailable') message = 'Serviço temporariamente indisponível.';

  return new ApiError({
    message,
    status,
    code,
    requestId,
    details,
    retryable: isRetriableStatus(status),
  });
}

function normalizeFetchError(
  error: unknown,
  endpoint: string,
  options: RequestInit,
  timedOut: boolean,
) {
  if (error instanceof ApiError) return error;

  if (error instanceof DOMException && error.name === 'AbortError') {
    return new ApiError({
      message: timedOut ? 'A solicitação demorou demais. Tente novamente.' : 'Solicitação cancelada.',
      code: timedOut ? 'timeout' : 'cancelled',
      retryable: timedOut && isIdempotentRequest(options),
      cause: error,
    });
  }

  if (error instanceof TypeError) {
    return new ApiError({
      message: 'Falha de conexão. Verifique sua internet e tente novamente.',
      code: 'network_error',
      retryable: isIdempotentRequest(options),
      cause: error,
    });
  }

  if (error instanceof Error) {
    return new ApiError({
      message: error.message || `Request failed for ${endpoint}.`,
      code: 'request_failed',
      cause: error,
    });
  }

  return new ApiError({
    message: `Request failed for ${endpoint}.`,
    code: 'request_failed',
    details: error,
  });
}

function shouldRetry(error: ApiError, options: RequestInit, retries: number) {
  return retries > 0 && error.retryable && isIdempotentRequest(options);
}

function retryDelayMs(retriesLeft: number) {
  return 250 * (3 - Math.min(retriesLeft, 2));
}

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export async function apiFetch(
  endpoint: string,
  options: ApiRequestInit = {},
  retries = 2,
): Promise<any> {
  const url = `${API_BASE}${endpoint}`;
  const method = options.method || 'GET';
  const headers = mergeHeaders(options.headers);
  const { timeoutMs, ...fetchOptions } = options as ApiRequestInit;

  if (sessionToken) {
    headers.Authorization = `Bearer ${sessionToken}`;
  }

  const requestSignal = createRequestSignal(options.signal, timeoutMs);

  try {
    const response = await fetch(url, { ...fetchOptions, headers, signal: requestSignal.signal });
    const payload = await parseResponseBody(response);

    if (response.status === 401) {
      if (isRefreshing) {
        return subscribeToRefresh(endpoint, options, retries);
      }

      isRefreshing = true;
      try {
        const newToken = await secureInit();
        if (newToken) {
          isRefreshing = false;
          flushRefreshSubscribers();
          return apiFetch(endpoint, options, retries);
        }

        setSessionToken(null);
        const authError = new ApiError({
          message: 'Sessão expirada. Reabra a MiniApp.',
          status: 401,
          code: 'session_expired',
          requestId: requestIdFrom(response),
        });
        rejectRefreshSubscribers(authError);
        throw authError;
      } catch (error) {
        const authError = normalizeFetchError(error, endpoint, options, false);
        rejectRefreshSubscribers(authError);
        throw authError;
      } finally {
        isRefreshing = false;
      }
    }

    if (!response.ok) {
      throw buildApiError(response, payload);
    }

    return payload;
  } catch (error) {
    const normalized = normalizeFetchError(error, endpoint, options, requestSignal.didTimeout());
    if (shouldRetry(normalized, options, retries)) {
      console.warn(`Retrying [${endpoint}]... (${retries} left)`);
      await wait(retryDelayMs(retries));
      return apiFetch(endpoint, options, retries - 1);
    }

    console.error(`[API ERROR] ${method} ${endpoint}:`, normalized);
    throw normalized;
  } finally {
    requestSignal.cleanup();
  }
}

async function secureInit(): Promise<string | null> {
  const tg = getTg();
  const initData = tg?.initData;
  const storedToken = sessionStorage.getItem('auth_token');

  const payload = {
    initData: initData || null,
    token: storedToken || null,
  };

  const requestSignal = createRequestSignal();

  try {
    const response = await fetch(`${API_BASE}/secure_init`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: requestSignal.signal,
    });

    const data = await parseResponseBody(response);
    if (!response.ok) {
      throw buildApiError(response, data);
    }

    if (isRecord(data) && typeof data.token === 'string') {
      setSessionToken(data.token);
      return data.token;
    }

    return null;
  } catch (error) {
    const normalized = normalizeFetchError(
      error,
      '/secure_init',
      { method: 'POST' },
      requestSignal.didTimeout(),
    );
    console.error('Secure Init Error:', normalized);
    return null;
  } finally {
    requestSignal.cleanup();
  }
}
