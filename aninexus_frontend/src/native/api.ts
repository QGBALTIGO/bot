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
  const { refreshUser, patchUser, user } = useUser();
  const cache = useQueryClient();
  const run = useCallback(
    async <T>(key: string, action: () => Promise<T>, success?: string): Promise<T | undefined> => {
      if (locked.current) return undefined;
      locked.current = true;
      setPending(key);
      try {
        const result = await action();
        if (success) addToast(success, 'success');
        if (key === 'favorite' && result && typeof result === 'object' && 'favorite' in result) {
          const favorite = (result as { favorite: any }).favorite;
          patchUser({ favorite });
          cache.setQueryData(['source', user?.id || 0, '/api/menu/profile'], (old: any) =>
            old ? { ...old, profile: { ...old.profile, favorite } } : old);
        }
        const preference = ['favorite', 'country', 'language', 'privacy', 'notifications'].includes(key);
        const profileEndpoints = ['/api/menu/profile', '/api/collection/state'];
        const affected = preference || key === 'nickname'
          ? profileEndpoints
          : key === 'sell'
            ? [...profileEndpoints, '/api/shop/sell/', '/api/collection/']
            : key.startsWith('request') || key.startsWith('submit')
              ? ['/api/pedido/', '/api/cards/contrib/']
              : [];
        // Updating a preference must not wait for a full /me, album and shop reload.
        // Exact user keys keep one person's private cache isolated from another.
        void cache.invalidateQueries({
          predicate: (query) => query.queryKey[0] === 'source' && query.queryKey[1] === (user?.id || 0)
            && affected.some((prefix) => String(query.queryKey[2]).startsWith(prefix)),
        });
        if (['sell', 'nickname', 'buy', 'buy-dado'].includes(key)) {
          invalidateQueries(['/source-shop', '/harem', '/gallery', '/dado/state']);
          void refreshUser();
        }
        return result;
      } catch (error) {
        addToast(getErrorMessage(error), 'error');
        return undefined;
      } finally {
        locked.current = false;
        setPending(null);
      }
    },
    [addToast, cache, refreshUser, patchUser, user?.id],
  );
  return { pending, run };
}
