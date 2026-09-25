import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { apiFetch, getErrorMessage, invalidateQueries } from '../../api/client';
import { useToast } from '../../components/ui/Toast';
import { useUser } from '../../context/UserContext';

export interface CollectionCard {
  id: number;
  name: string;
  anime: string;
  image: string;
  quantity: number;
  protected?: boolean;
  favorite?: boolean;
  reserved?: boolean;
  wished?: boolean;
  available?: boolean;
}
export interface CardPage {
  items: CollectionCard[];
  has_more: boolean;
}
export const featureFetch = <T = any>(path: string, init: RequestInit = {}): Promise<T> =>
  apiFetch(`/collecting${path}`, init);
export function useFeatureQuery<T>(path: string, enabled = true) {
  const { user } = useUser();
  return useQuery<T>({
    queryKey: ['collecting', user?.id, path],
    queryFn: ({ signal }) => featureFetch<T>(path, { signal }),
    enabled: Boolean(user) && enabled,
    staleTime: 30000,
    retry: false,
  });
}
export function useFeatureAction() {
  const busy = useRef(false),
    retry = useRef<{ signature: string; id: string } | null>(null);
  const [pending, setPending] = useState(false);
  const cache = useQueryClient(),
    { user, refreshUser } = useUser(),
    { addToast } = useToast();
  const perform = async <T = any>(
    path: string,
    payload: Record<string, unknown> = {},
    options: { method?: string; economic?: boolean; idempotent?: boolean; success?: string } = {},
  ): Promise<T | undefined> => {
    if (busy.current) return undefined;
    busy.current = true;
    setPending(true);
    const signature = JSON.stringify([path, payload]);
    if (retry.current?.signature !== signature)
      retry.current = { signature, id: crypto.randomUUID() };
    try {
      const result = await featureFetch<T>(path, {
        method: options.method || 'POST',
        body: JSON.stringify({
          ...payload,
          ...(options.idempotent ? { request_id: retry.current.id } : {}),
        }),
      });
      retry.current = null;
      if (options.success) addToast(options.success, 'success');
      void cache.invalidateQueries({
        predicate: (q) => q.queryKey[0] === 'collecting' && q.queryKey[1] === user?.id,
      });
      if (options.economic) {
        invalidateQueries(['/harem', '/source-shop', '/trade/offers', '/economy', '/dado/state']);
        void cache.invalidateQueries({
          predicate: (q) => q.queryKey[0] === 'source' && q.queryKey[1] === user?.id,
        });
        void refreshUser();
      }
      return result;
    } catch (error) {
      addToast(getErrorMessage(error), 'error');
      // Retain the same request ID after a lost response; the server can replay its receipt.
      return undefined;
    } finally {
      busy.current = false;
      setPending(false);
    }
  };
  return { pending, perform };
}
