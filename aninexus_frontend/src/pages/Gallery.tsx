import {
  ArrowDown10,
  ArrowDownZA,
  ArrowUp01,
  ArrowUpAZ,
  BookOpen,
  ChevronDown,
  Database,
  Loader2,
  type LucideIcon,
  RefreshCw,
  Search,
  X,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useApi } from '../hooks/useApi';
import { Card as CharacterCard } from '../components/character/Card';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { Input } from '../components/ui/Input';
import { CardSkeleton } from '../components/ui/Skeleton';
import { Character } from '../context/UserContext';
import { useInfiniteGrid } from '../hooks/useInfiniteGrid';
import { cleanRarityLabel, cn } from '../utils';

interface GalleryProps {
  onCharClick: (character: Character) => void;
}

type CatalogSort = 'numeric' | 'alphabet';
type CatalogOrder = 'asc' | 'desc';

const SORT_OPTIONS: Array<{
  sort: CatalogSort;
  order: CatalogOrder;
  label: string;
  Icon: LucideIcon;
}> = [
  { sort: 'numeric', order: 'asc', label: 'ID crescente', Icon: ArrowUp01 },
  { sort: 'numeric', order: 'desc', label: 'ID decrescente', Icon: ArrowDown10 },
  { sort: 'alphabet', order: 'asc', label: 'A-Z', Icon: ArrowUpAZ },
  { sort: 'alphabet', order: 'desc', label: 'Z-A', Icon: ArrowDownZA },
];

export const Gallery = ({ onCharClick }: GalleryProps) => {
  const [sort, setSort] = useState<CatalogSort>('numeric');
  const [order, setOrder] = useState<CatalogOrder>('asc');
  const [sortOpen, setSortOpen] = useState(false);
  const ActiveSortIcon =
    SORT_OPTIONS.find((o) => o.sort === sort && o.order === order)?.Icon ?? ArrowUp01;
  const gridParams = useMemo(() => ({ sort, order }), [sort, order]);
  const { items, loading, search, setSearch, rarity, setRarity, lastElementRef, error, refresh } =
    useInfiniteGrid<Character>('/gallery', { params: gridParams, limit: 42 });

  const [availableRarities, setAvailableRarities] = useState<string[]>([]);
  const rarityOptions = useMemo(
    () => availableRarities.map((value) => ({ value, label: cleanRarityLabel(value) || value })),
    [availableRarities],
  );

  const { data: rarityData } = useApi<string[]>('/rarities');

  useEffect(() => {
    if (rarityData) setAvailableRarities(rarityData);
  }, [rarityData]);

  return (
    <div className="pt-6 max-w-5xl mx-auto adaptive-px space-y-8 select-none">
      <header className="space-y-6">
        <div className="flex items-center gap-2.5">
          <BookOpen className="text-brand-accent" size={20} />
          <div className="flex flex-col flex-1">
            <h1 className="text-xl font-bold text-zinc-100 uppercase tracking-tight">Catálogo</h1>
            <div className="flex items-center gap-1.5 opacity-60">
              <Database size={10} className="text-zinc-500" />
              <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                Todos os personagens disponíveis no AniNexus
              </p>
            </div>
          </div>
          <button
            type="button"
            aria-label="Atualizar catálogo"
            onClick={() => {
              window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
              refresh();
            }}
            className="w-9 h-9 flex items-center justify-center rounded-md bg-zinc-900 border border-white/5 text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 transition-all shrink-0"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>

        <div className="space-y-3 bg-zinc-950 border border-white/5 p-4 rounded-md">
          <div className="relative">
            <Input
              icon={Search}
              placeholder="Buscar personagens..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className={cn('h-10', search && 'pr-10')}
            />
            {search && (
              <button
                type="button"
                aria-label="Limpar busca"
                onClick={() => setSearch('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-zinc-500 hover:text-zinc-200 transition-colors"
              >
                <X size={14} />
              </button>
            )}
          </div>

          <div className="flex items-center gap-2">
            <div className="relative group flex-1 min-w-0">
              <select
                aria-label="Filtrar por raridade"
                value={rarity}
                onChange={(event) => setRarity(event.target.value)}
                className="w-full h-10 pl-3.5 pr-10 bg-zinc-900 border border-white/10 rounded-md text-[10px] font-bold text-zinc-400 uppercase tracking-widest outline-none focus:border-brand-accent appearance-none cursor-pointer hover:bg-zinc-800 transition-all truncate"
              >
                <option value="">TODAS AS RARIDADES</option>
                {rarityOptions.map(({ value, label }) => (
                  <option key={value} value={value}>
                    {label.toUpperCase()}
                  </option>
                ))}
              </select>
              <ChevronDown
                size={14}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-zinc-600 pointer-events-none group-focus-within:text-brand-accent transition-colors"
              />
            </div>

            <div className="relative shrink-0">
              <button
                type="button"
                aria-label="Opções de ordenação"
                aria-expanded={sortOpen}
                onClick={() => setSortOpen((v) => !v)}
                className="h-10 w-10 flex items-center justify-center rounded-md bg-zinc-900 border border-white/10 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-all"
              >
                <ActiveSortIcon size={16} className={sortOpen ? 'text-brand-accent' : undefined} />
              </button>

              {sortOpen && (
                <>
                  <div
                    className="fixed inset-0 z-[900]"
                    onClick={() => setSortOpen(false)}
                    aria-hidden="true"
                  />
                  <div className="absolute right-0 top-11 z-[901] w-36 rounded-md bg-zinc-900 border border-white/10 shadow-xl p-1.5 space-y-1">
                    {SORT_OPTIONS.map(({ sort: optionSort, order: optionOrder, label, Icon }) => {
                      const active = sort === optionSort && order === optionOrder;
                      return (
                        <button
                          key={`${optionSort}-${optionOrder}`}
                          type="button"
                          onClick={() => {
                            window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
                            setSort(optionSort);
                            setOrder(optionOrder);
                            setSortOpen(false);
                          }}
                          className={cn(
                            'flex items-center gap-2.5 w-full h-9 px-3 rounded text-[10px] font-bold uppercase tracking-widest transition-all',
                            active
                              ? 'bg-brand-accent text-white'
                              : 'text-zinc-400 hover:text-zinc-100 hover:bg-white/5',
                          )}
                        >
                          <Icon size={14} className="shrink-0" />
                          {label}
                        </button>
                      );
                    })}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </header>

      {!loading && !error && items.length > 0 && (
        <p className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest -mt-4">
          {items.length} personagem{items.length === 1 ? '' : 's'} encontrado{items.length === 1 ? '' : 's'}
        </p>
      )}

      {error && items.length === 0 ? (
        <div className="py-20">
          <ErrorState message={error} onAction={refresh} />
        </div>
      ) : items.length > 0 ? (
        <div className="grid grid-cols-2 xs:grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-3 sm:gap-4 px-0.5">
          {items.map((char, i) => (
            <CharacterCard
              key={char.id}
              ref={i === items.length - 1 ? lastElementRef : null}
              character={char}
              onClick={() => onCharClick(char)}
            />
          ))}
          {loading && Array.from({ length: 6 }).map((_, i) => <CardSkeleton key={`load-${i}`} />)}
        </div>
      ) : loading ? (
        <div className="grid grid-cols-2 xs:grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-3 sm:gap-4 px-0.5">
          {Array.from({ length: 18 }).map((_, i) => (
            <CardSkeleton key={`skeleton-${i}`} />
          ))}
        </div>
      ) : (
        <div className="py-20 border border-dashed border-white/5 rounded-lg bg-zinc-950/50">
          <EmptyState
            icon={Search}
            title="Nenhum personagem encontrado"
            message="Tente ajustar a busca ou os filtros."
          />
        </div>
      )}

      {loading && items.length > 0 && (
        <div className="flex justify-center py-20">
          <Loader2 size={24} className="animate-spin text-zinc-700" />
        </div>
      )}
    </div>
  );
};
