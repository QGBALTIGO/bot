import {
  Activity,
  BookOpen,
  ChevronDown,
  Coins,
  Crown,
  Egg,
  Gem,
  Heart,
  Loader2,
  PawPrint,
  RefreshCw,
  Search,
  Swords,
  Ticket,
  Trophy,
  Zap,
} from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { apiFetch } from '../api/client';
import { useApi } from '../hooks/useApi';
import { Avatar } from '../components/Avatar';
import { Card as CharacterCard } from '../components/character/Card';
import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { Input } from '../components/ui/Input';
import { ProgressBar } from '../components/ui/ProgressBar';
import { CardSkeleton, Skeleton } from '../components/ui/Skeleton';
import { Character, useUser } from '../context/UserContext';
import { useInfiniteGrid } from '../hooks/useInfiniteGrid';
import { cleanRarityLabel, cn, formatNumber } from '../utils';

interface ProfileProps {
  onCharClick: (character: Character) => void;
  focusCollection?: boolean;
}

export const Profile = ({ onCharClick, focusCollection = false }: ProfileProps) => {
  const { user, loading: userLoading } = useUser();
  const collectionRef = useRef<HTMLElement | null>(null);
  const {
    items,
    loading,
    page,
    search,
    setSearch,
    rarity,
    setRarity,
    lastElementRef,
    error,
    refresh,
  } = useInfiniteGrid<Character>('/harem');

  const [availableRarities, setAvailableRarities] = useState<string[]>([]);
  const [marriage, setMarriage] = useState<{
    partner_id: number;
    partner_name: string;
    partner_avatar?: string | null;
    married_at: string;
  } | null>(null);
  const [battleStats, setBattleStats] = useState<{
    total_battles: number;
    wins: number;
    losses: number;
    win_rate: number;
  } | null>(null);
  const rarityOptions = useMemo(
    () =>
      (Array.isArray(availableRarities) ? availableRarities : []).map((value) => ({
        value,
        label: cleanRarityLabel(value) || value,
      })),
    [availableRarities],
  );

  const { data: rarityData } = useApi<string[]>('/rarities');

  useEffect(() => {
    if (rarityData) setAvailableRarities(rarityData);
  }, [rarityData]);
  useEffect(() => {
    apiFetch('/social/marriage').then(setMarriage).catch(() => setMarriage(null));
    apiFetch('/battle/stats').then(setBattleStats).catch(() => setBattleStats(null));
  }, []);

  useEffect(() => {
    if (!focusCollection || userLoading) return;

    const timeoutId = window.setTimeout(() => {
      collectionRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' });
    }, 150);

    return () => window.clearTimeout(timeoutId);
  }, [focusCollection, userLoading]);

  if (userLoading && (items?.length || 0) === 0)
    return (
      <div className="pt-6 adaptive-px max-w-5xl mx-auto space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Skeleton className="md:col-span-2 h-40 rounded-lg" />
          <Skeleton className="h-40 rounded-lg" />
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-24 rounded-lg" />
          ))}
        </div>
        <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-4">
          {Array.from({ length: 12 }).map((_, i) => (
            <CardSkeleton key={`prof-skeleton-${i}`} />
          ))}
        </div>
      </div>
    );

  if (!user) return null;

  const stats = user.stats;
  const passType = stats?.pass_type || 'free';
  const passLabel = passType === 'free' ? 'PASSE GRÁTIS' : passType === 'premium' ? 'PASSE PREMIUM' : 'PASSE ELITE';
  const collectionOwned = stats?.unique_characters ?? stats?.total_characters ?? 0;
  const collectionTotal = stats?.total_available_characters || Math.max(collectionOwned, 1);
  const collectionPercent =
    stats?.collection_percent ??
    (collectionTotal > 0 ? Math.round((collectionOwned / collectionTotal) * 1000) / 10 : 0);
  const rankLabel = stats?.rank ? `#${formatNumber(stats.rank)}` : 'N/A';
  const percentileLabel =
    typeof stats?.percentile === 'number' && stats.percentile > 0
      ? `TOP ${stats.percentile}%`
      : 'SEM POSIÇÃO';
  const currentTitle = user.titles?.current || 'USUÁRIO';
  const activePet = user.current_pet;
  const usernameLabel = user.username ? `@${user.username}` : `ID ${user.id}`;

  return (
    <div className="pt-6 max-w-5xl mx-auto adaptive-px space-y-6">
      {/* Profile & Registry Summary */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* User Profile Card */}
        <Card
          variant="surface"
          className="md:col-span-2 flex flex-col sm:flex-row items-center gap-6 p-6"
        >
          <div className="relative shrink-0">
            <Avatar
              src={user.avatar}
              alt="User"
              className="w-24 h-24 rounded-md border border-white/10 object-cover shadow-lg"
            />
            <div className="absolute -bottom-2 -right-2">
              <Badge
                variant="secondary"
                size="xs"
                className="bg-zinc-950 border-white/10 shadow-lg px-2 py-1"
              >
                LVL {stats?.level || 1}
              </Badge>
            </div>
          </div>

          <div className="flex-1 min-w-0 space-y-3 text-center sm:text-left">
            <div>
              <div className="flex flex-wrap items-center justify-center sm:justify-start gap-2.5 mb-1">
                <h1 className="text-xl font-bold text-zinc-100 tracking-tight uppercase truncate">
                  {[user.first_name, user.last_name].filter(Boolean).join(' ') || 'Usuário'}
                </h1>
                {user.role_tag && (
                  <Badge variant="primary" size="xs" className="font-bold">
                    {user.role_tag}
                  </Badge>
                )}
              </div>
              <p className="text-[10px] font-mono font-medium text-zinc-500 uppercase tracking-widest">
                {usernameLabel}
              </p>
            </div>

            <div className="flex flex-wrap items-center justify-center sm:justify-start gap-2">
              <Badge variant="epic" size="xs" icon={Crown} className="font-bold">
                {currentTitle}
              </Badge>
              <Badge variant="secondary" size="xs" icon={Ticket} className="font-bold">
                {passLabel}
              </Badge>
            </div>

            <div className="pt-2 w-full max-w-[280px] mx-auto sm:mx-0">
              <ProgressBar
                current={stats?.xp_current || 0}
                total={Math.max(1, stats?.xp_needed || 1000)}
                label="EXPERIÊNCIA"
                compact
              />
            </div>
          </div>
        </Card>

        {/* Collection Summary Card */}
        <Card variant="surface" className="p-6 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <BookOpen size={14} className="text-zinc-500" />
              <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                Coleção
              </span>
            </div>
            <Badge variant="secondary" size="xs">
              Registro
            </Badge>
          </div>

          <div className="mt-6 space-y-4">
            <div className="flex items-end justify-between">
              <div className="text-3xl font-mono font-bold text-zinc-100 tabular-nums leading-none">
                {collectionPercent}
                <span className="text-sm text-zinc-500 ml-1">%</span>
              </div>
              <div className="text-right">
                <div className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest mb-1">
                  COLECIONADOS
                </div>
                <div className="text-sm font-mono font-bold text-zinc-100 tabular-nums">
                  {formatNumber(collectionOwned)}
                  <span className="mx-1 opacity-20">/</span>
                  {formatNumber(collectionTotal)}
                </div>
              </div>
            </div>
            <ProgressBar
              current={collectionOwned}
              total={collectionTotal}
              variant="default"
              compact
              showValue={false}
            />
          </div>
        </Card>
      </section>

      {/* Stats Grid */}
      <section className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          {
            icon: Coins,
            label: 'Coins',
            value: formatNumber(stats?.points ?? user.balance ?? 0),
            variant: 'warning',
          },
          {
            icon: Gem,
            label: 'Dados',
            value: formatNumber(stats?.zenith || 0),
            variant: 'primary',
          },
          {
            icon: Trophy,
            label: 'Posição',
            value: rankLabel,
            subValue: percentileLabel,
            variant: 'success',
          },
          {
            icon: Activity,
            label: 'Sequência',
            value: `${formatNumber(stats?.streak || 0)} DIAS`,
            variant: 'rare',
          },
        ].map((stat, i) => (
          <Card key={i} variant="default" className="p-4 group">
            <div className="flex items-center gap-2 mb-3">
              <stat.icon
                size={14}
                className={cn(
                  stat.variant === 'primary' && 'text-brand-accent',
                  stat.variant === 'success' && 'text-emerald-500',
                  stat.variant === 'warning' && 'text-amber-500',
                  stat.variant === 'rare' && 'text-cyan-500',
                )}
              />
              <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest">
                {stat.label}
              </span>
            </div>
            <div className="flex flex-col">
              <div className="text-lg font-mono font-bold text-zinc-100 tabular-nums leading-none">
                {stat.value}
              </div>
              {stat.subValue && (
                <span className="text-[8px] font-bold text-zinc-600 uppercase tracking-wider mt-1">
                  {stat.subValue}
                </span>
              )}
            </div>
          </Card>
        ))}
      </section>

      {/* Sub-Systems Section */}
      <section className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Card
          variant="default"
          className="flex items-center gap-4 p-4 hover:bg-zinc-900 transition-colors cursor-pointer group"
        >
          <div className="w-10 h-10 rounded bg-zinc-900 border border-white/5 flex items-center justify-center shrink-0">
            <PawPrint
              size={18}
              className="text-zinc-400 group-hover:text-brand-accent transition-colors"
            />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[8px] font-bold text-zinc-500 uppercase tracking-widest mb-0.5">
              COMPANHEIRO
            </div>
            <div className="text-xs font-bold text-zinc-100 truncate uppercase tracking-tight">
              {activePet?.name || 'NENHUM ATIVO'}
            </div>
          </div>
          {activePet && (
            <Badge variant="secondary" size="xs" className="font-mono">
              LVL {activePet.level || 1}
            </Badge>
          )}
        </Card>

        <Card
          variant="default"
          className="flex items-center gap-4 p-4 hover:bg-zinc-900 transition-colors cursor-pointer group"
        >
          <div className="w-10 h-10 rounded bg-zinc-900 border border-white/5 flex items-center justify-center shrink-0">
            <Egg
              size={18}
              className="text-zinc-400 group-hover:text-emerald-500 transition-colors"
            />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[8px] font-bold text-zinc-500 uppercase tracking-widest mb-0.5">
              INCUBADORA
            </div>
            <div className="text-xs font-bold text-zinc-100 truncate uppercase tracking-tight">
              {stats?.active_incubations || 0} / {stats?.incubation_slots || 1} ATIVO
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-1 h-1 rounded-full bg-emerald-500" />
            <span className="text-[8px] font-bold text-zinc-600 uppercase">SISTEMA OK</span>
          </div>
        </Card>
      </section>

      {/* Bond & Combat Section */}
      {(marriage || (battleStats && battleStats.total_battles > 0)) && (
        <section className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {marriage && (
            <Card variant="default" className="flex items-center gap-4 p-4">
              <div className="w-10 h-10 rounded bg-pink-500/10 border border-pink-500/20 flex items-center justify-center shrink-0">
                <Heart size={18} className="text-pink-500" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-[8px] font-bold text-zinc-500 uppercase tracking-widest mb-0.5">
                  VÍNCULO COM
                </div>
                <div className="text-xs font-bold text-zinc-100 truncate uppercase tracking-tight">
                  {marriage.partner_name}
                </div>
              </div>
              <Badge variant="secondary" size="xs" className="font-mono shrink-0">
                {(() => {
                  const d = marriage.married_at ? new Date(marriage.married_at) : null;
                  return d && Number.isFinite(d.getTime())
                    ? d.toISOString().slice(0, 10)
                    : 'VINCULADO';
                })()}
              </Badge>
            </Card>
          )}
          {battleStats && battleStats.total_battles > 0 && (
            <Card variant="default" className="flex items-center gap-4 p-4">
              <div className="w-10 h-10 rounded bg-red-500/10 border border-red-500/20 flex items-center justify-center shrink-0">
                <Swords size={18} className="text-red-400" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-[8px] font-bold text-zinc-500 uppercase tracking-widest mb-0.5">
                  HISTÓRICO DE DUELOS
                </div>
                <div className="text-xs font-bold text-zinc-100 uppercase tracking-tight">
                  {formatNumber(battleStats.wins)} V / {formatNumber(battleStats.losses)} D
                </div>
              </div>
              <Badge variant="secondary" size="xs" className="font-mono shrink-0">
                {Number(battleStats.win_rate || 0).toFixed(0)}% VITÓRIAS
              </Badge>
            </Card>
          )}
        </section>
      )}

      {/* Collection Explorer Section */}
      <section ref={collectionRef} className="pt-4 space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 px-1">
          <div className="space-y-1">
            <h2 className="text-xl font-bold text-zinc-100 uppercase tracking-tight">
              Sua coleção
            </h2>
            <div className="flex items-center gap-1.5">
              <Zap size={10} className="text-brand-accent" />
              <p className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest">
                Todos os personagens que você já coletou
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              aria-label="Atualizar coleção"
              onClick={() => {
                window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
                refresh();
              }}
              className="w-10 h-10 flex items-center justify-center rounded-md bg-zinc-950 border border-white/10 text-zinc-500 hover:text-zinc-200 hover:bg-zinc-900 transition-all shrink-0"
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            </button>
            <div className="w-full sm:w-64">
              <Input
                icon={Search}
                placeholder="Buscar personagens..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="h-10"
              />
            </div>
            <div className="relative">
              <select
                aria-label="Filtrar por raridade"
                value={rarity}
                onChange={(event) => setRarity(event.target.value)}
                className="h-10 pl-3.5 pr-10 bg-zinc-950 border border-white/10 rounded-md text-[10px] font-bold text-zinc-400 uppercase tracking-widest outline-none focus:border-brand-accent appearance-none cursor-pointer hover:bg-zinc-900 transition-all"
              >
                <option value="">TODAS AS RARIDADES</option>
                {rarityOptions.map(({ value, label }) => (
                  <option key={value} value={value}>
                    {label.toUpperCase()}
                  </option>
                ))}
              </select>
              <ChevronDown
                size={12}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-zinc-600 pointer-events-none"
              />
            </div>
          </div>
        </div>

        {error && (items?.length || 0) === 0 ? (
          <div className="py-12">
            <ErrorState message={error} onAction={refresh} />
          </div>
        ) : (items?.length || 0) > 0 || (loading && page > 1) ? (
          <div className="grid grid-cols-2 xs:grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-3 sm:gap-4 px-0.5">
            {(items || []).map((char, i) => (
              <CharacterCard
                key={char.id}
                ref={i === items.length - 1 ? lastElementRef : null}
                character={char}
                onClick={onCharClick}
              />
            ))}
            {loading &&
              page > 1 &&
              Array.from({ length: 6 }).map((_, i) => <CardSkeleton key={`loading-${i}`} />)}
          </div>
        ) : loading && page === 1 ? (
          <div className="grid grid-cols-2 xs:grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-3 sm:gap-4 px-0.5">
            {Array.from({ length: 18 }).map((_, i) => (
              <CardSkeleton key={`loading-new-${i}`} />
            ))}
          </div>
        ) : (
          <div className="py-20 border border-dashed border-white/5 rounded-lg bg-zinc-950/50">
            <EmptyState
              icon={BookOpen}
              title="Nada por aqui ainda"
              message="Use o Dado, jogos e ovos para aumentar sua coleção."
            />
          </div>
        )}

        {loading && (items?.length || 0) > 0 && (
          <div className="flex justify-center py-12">
            <Loader2 className="animate-spin text-zinc-700" size={24} />
          </div>
        )}
      </section>
    </div>
  );
};
