import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch, getErrorMessage, invalidateQueries, type ApiRequestInit } from '../api/client';
import { useToast } from '../components/ui/Toast';
import { useUser } from '../context/UserContext';

export const sourceFetch = <T = any>(endpoint: string, options: ApiRequestInit = {}): Promise<T> =>
  apiFetch(endpoint, { ...options, sourceEndpoint: true });
export const sourcePost = <T = any>(
  endpoint: string,
  body: Record<string, unknown> = {},
): Promise<T> => sourceFetch<T>(endpoint, { method: 'POST', body: JSON.stringify(body) });
export function queryUrl(endpoint: string, params: Record<string, string | number>) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => qs.set(key, String(value)));
  return `${endpoint}${endpoint.includes('?') ? '&' : '?'}${qs}`;
}
export function useSourceQuery<T = any>(endpoint: string, enabled = true) {
  const { user } = useUser();
  return useQuery<T>({
    queryKey: ['source', user?.id || 0, endpoint],
    queryFn: ({ signal }) => sourceFetch<T>(endpoint, { signal }),
    enabled,
    staleTime: 30000,
    retry: false,
  });
}
export function useSourcePages<T>(
  endpoint: string,
  params: Record<string, string | number>,
  enabled = true,
) {
  const { user } = useUser();
  return useInfiniteQuery<{ items: T[]; total: number; anime?: any }>({
    queryKey: ['source', user?.id || 0, endpoint, params],
    initialPageParam: 0,
    queryFn: ({ pageParam, signal }) =>
      sourceFetch(queryUrl(endpoint, { ...params, offset: Number(pageParam), limit: 40 }), {
        signal,
      }),
    getNextPageParam: (last, pages) => {
      const n = pages.reduce((sum, p) => sum + p.items.length, 0);
      return last.items.length > 0 && n < last.total ? n : undefined;
    },
    enabled,
    staleTime: 30000,
    retry: false,
  });
}
export function useDebounced(value: string, delay = 450) {
  const [result, setResult] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setResult(value.trim()), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return result;
}
export function useSourceAction() {
  const [pending, setPending] = useState<string | null>(null);
  const locked = useRef(false);
  const { addToast } = useToast();
  const { refreshUser } = useUser();
  const cache = useQueryClient();
  const run = useCallback(
    async <T>(key: string, action: () => Promise<T>, success?: string): Promise<T | undefined> => {
      if (locked.current) return undefined;
      locked.current = true;
      setPending(key);
      try {
        const result = await action();
        if (success) addToast(success, 'success');
        await cache.invalidateQueries({ queryKey: ['source'] });
        invalidateQueries(['/source-shop', '/harem', '/gallery', '/me', '/dado/state']);
        await refreshUser();
        return result;
      } catch (error) {
        addToast(getErrorMessage(error), 'error');
        return undefined;
      } finally {
        locked.current = false;
        setPending(null);
      }
    },
    [addToast, cache, refreshUser],
  );
  return { pending, run };
}
