import { type InfiniteData, useInfiniteQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiFetch, getErrorMessage } from '../api/client';

interface InfiniteGridOptions {
  limit?: number;
  params?: Record<string, any>;
}

interface GridPage<T> {
  items: T[];
  total?: number;
}

export const useInfiniteGrid = <T = any>(endpoint: string, options: InfiniteGridOptions = {}) => {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [rarity, setRarity] = useState('');

  // Debounced copies drive the query key; raw state stays controlled for inputs.
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [debouncedRarity, setDebouncedRarity] = useState('');

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search.trim());
      setDebouncedRarity(rarity.trim());
    }, 400);
    return () => clearTimeout(timer);
  }, [search, rarity]);

  const limit = options.limit || 24;
  const paramsKey = JSON.stringify(options.params || {});

  const queryKey = ['grid', endpoint, debouncedSearch, debouncedRarity, limit, paramsKey];

  const query = useInfiniteQuery<
    GridPage<T>,
    Error,
    InfiniteData<GridPage<T>>,
    typeof queryKey,
    number
  >({
    queryKey,
    initialPageParam: 1,
    queryFn: ({ pageParam, signal }) => {
      const queryParams = new URLSearchParams({
        page: pageParam.toString(),
        limit: limit.toString(),
        search: debouncedSearch,
        rarity: debouncedRarity,
        ...(JSON.parse(paramsKey) as Record<string, string>),
      });
      return apiFetch(`${endpoint}?${queryParams.toString()}`, { signal });
    },
    getNextPageParam: (lastPage, allPages, lastPageParam) => {
      const fetched = lastPage.items?.length ?? 0;
      if (fetched === 0) return undefined;
      const total = typeof lastPage.total === 'number' ? lastPage.total : null;
      const loaded = lastPageParam * limit;
      const more = total === null ? fetched === limit : loaded < total;
      return more ? lastPageParam + 1 : undefined;
    },
    // apiFetch already retries idempotent requests internally.
    retry: false,
  });

  const items = useMemo(
    () => (query.data ? query.data.pages.flatMap((p) => p.items ?? []) : []),
    [query.data],
  );

  const observer = useRef<IntersectionObserver | null>(null);
  const lastElementRef = useCallback(
    (node: HTMLElement | null) => {
      if (query.isFetching) return;
      if (observer.current) observer.current.disconnect();
      observer.current = new IntersectionObserver((entries) => {
        const entry = entries[0];
        if (entry && entry.isIntersecting && query.hasNextPage && !query.isFetching) {
          query.fetchNextPage();
        }
      });
      if (node) observer.current.observe(node);
    },
    [query.isFetching, query.hasNextPage, query.fetchNextPage],
  );

  // biome-ignore lint/correctness/useExhaustiveDependencies: queryKey values are listed individually
  const refresh = useCallback(() => {
    queryClient.resetQueries({ queryKey });
  }, [queryClient, ...queryKey]);

  return {
    items,
    loading: query.isPending || query.isFetching,
    hasMore: !!query.hasNextPage,
    error: query.error ? getErrorMessage(query.error) : null,
    page: query.data?.pages.length ?? 1,
    search,
    setSearch,
    rarity,
    setRarity,
    lastElementRef,
    refresh,
  };
};
