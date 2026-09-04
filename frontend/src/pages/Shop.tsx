import {
  AlertCircle,
  Boxes,
  CheckCircle2,
  Clock,
  Coins,
  Gem,
  PackageOpen,
  RefreshCw,
  Store,
} from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Card as CharacterCard } from '../components/character/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { CardSkeleton, Skeleton } from '../components/ui/Skeleton';
import { Character, useUser } from '../context/UserContext';
import { useApi } from '../hooks/useApi';
import { cn, formatNumber } from '../utils';

interface ShopProps {
  onCharClick: (char: Character) => void;
}

interface ShopHub {
  balance: number;
  zenith: number;
  pass_type: string;
  characters_rarity: string;
  rotation_date: string;
  reset_at: string;
}

const getStockRemaining = (character: Character) => {
  if (typeof character.stock_remaining === 'number') return Math.max(0, character.stock_remaining);
  if (typeof character.stock_limit === 'number' && typeof character.sold_count === 'number') {
    return Math.max(0, character.stock_limit - character.sold_count);
  }
  return null;
};

const isSoldOut = (character: Character) => {
  const remaining = getStockRemaining(character);
  return Boolean(character.sold_out) || (remaining !== null && remaining <= 0);
};

const getCountdown = (resetAt: string | undefined, now: number) => {
  if (!resetAt) return '--:--';

  const resetTime = new Date(resetAt).getTime();
  if (!Number.isFinite(resetTime)) return '--:--';

  const diff = Math.max(0, resetTime - now);
  const hours = Math.floor(diff / (1000 * 60 * 60));
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
  const seconds = Math.floor((diff % (1000 * 60)) / 1000);

  if (hours <= 0 && minutes <= 0 && seconds <= 10) return 'RESETTING';
  if (hours <= 0) return `${minutes}m ${seconds}s`;
  return `${hours}h ${minutes}m`;
};

export const Shop = ({ onCharClick }: ShopProps) => {
  const { user, refreshUser } = useUser();
  const {
    data: shopData,
    loading,
    error,
    execute: fetchShop,
  } = useApi<Character[]>('/shop/characters');
  const {
    data: hubData,
    loading: hubLoading,
    error: hubError,
    execute: fetchHub,
  } = useApi<ShopHub>('/shop/hub');
  const [now, setNow] = useState(() => Date.now());
  const rotatedRef = useRef(false);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  // When the rotation reset time passes, refetch once so users see the new
  // rotation without a manual refresh.
  useEffect(() => {
    if (!hubData?.reset_at) {
      rotatedRef.current = false;
      return;
    }
    const resetTime = new Date(hubData.reset_at).getTime();
    if (!Number.isFinite(resetTime)) return;
    if (now >= resetTime && !rotatedRef.current) {
      rotatedRef.current = true;
      fetchShop().catch(() => undefined);
      fetchHub().catch(() => undefined);
    }
  }, [now, hubData?.reset_at, fetchShop, fetchHub]);

  const zenithBalance = Number(hubData?.zenith ?? user?.stats?.zenith ?? user?.zenith ?? 0);
  const shardBalance = Number(hubData?.balance ?? user?.balance ?? 0);

  const inventory = useMemo(() => {
    const ownedIds = new Set((user?.characters || []).map((char) => String(char.id)));

    return (shopData || [])
      .map((char) => {
        const owned = char.owned || ownedIds.has(String(char.id));
        const stockRemaining = getStockRemaining(char);
        const soldOut = isSoldOut(char);

        return {
          ...char,
          owned,
          stock_remaining: stockRemaining !== null ? stockRemaining : char.stock_remaining,
          sold_out: soldOut,
        };
      })
      .sort((a, b) => {
        const rank = (char: Character) => {
          if (char.owned) return 3;
          if (isSoldOut(char)) return 4;
          if (Number(char.zenith_price || 0) <= zenithBalance) return 1;
          return 2;
        };

        const rankDiff = rank(a) - rank(b);
        if (rankDiff !== 0) return rankDiff;
        return Number(a.zenith_price || 0) - Number(b.zenith_price || 0);
      });
  }, [shopData, user?.characters, zenithBalance]);

  const summary = useMemo(() => {
    const owned = inventory.filter((char) => char.owned).length;
    const available = inventory.filter((char) => !char.owned && !isSoldOut(char)).length;
    const affordable = inventory.filter(
      (char) => !char.owned && !isSoldOut(char) && Number(char.zenith_price || 0) <= zenithBalance,
    ).length;
    const soldOut = inventory.filter((char) => !char.owned && isSoldOut(char)).length;

    return { owned, available, affordable, soldOut };
  }, [inventory, zenithBalance]);

  const handleRefresh = async () => {
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    await Promise.allSettled([fetchShop(), fetchHub(), refreshUser()]);
  };

  if (loading && !shopData)
    return (
      <div className="pt-6 adaptive-px max-w-5xl mx-auto space-y-8">
        <div className="flex flex-col gap-2">
          <Skeleton className="h-8 w-48 rounded-md" />
          <Skeleton className="h-4 w-64 rounded-md opacity-50" />
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-20 rounded-md" />
          ))}
        </div>
        <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-4">
          {Array.from({ length: 12 }).map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      </div>
    );

  if (error && !shopData)
    return (
      <div className="pt-6 max-w-2xl mx-auto adaptive-px">
        <ErrorState message={error} onAction={handleRefresh} />
      </div>
    );

  return (
    <div className="pt-6 max-w-5xl mx-auto adaptive-px space-y-8">
      <header className="space-y-6">
        <div className="flex items-start justify-between gap-6">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5">
              <Store size={20} className="text-brand-accent" />
              <h1 className="text-xl font-bold text-zinc-100 uppercase tracking-tight">Market</h1>
            </div>
            <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest leading-relaxed">
              Characters rotate daily — stock resets with the timer
            </p>
          </div>

          <Button
            variant="secondary"
            size="sm"
            onClick={handleRefresh}
            isLoading={loading || hubLoading}
            className="w-9 h-9 p-0"
          >
            <RefreshCw size={16} className={loading || hubLoading ? 'animate-spin' : ''} />
          </Button>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          {[
            { icon: Coins, label: 'Coins', value: formatNumber(shardBalance), variant: 'warning' },
            { icon: Gem, label: 'Prisms', value: formatNumber(zenithBalance), variant: 'primary' },
            {
              icon: Clock,
              label: 'Reset In',
              value: getCountdown(hubData?.reset_at, now),
              variant: 'secondary',
            },
            {
              icon: PackageOpen,
              label: 'Available',
              value: `${summary.available}`,
              variant: 'success',
            },
            {
              icon: CheckCircle2,
              label: 'Collected',
              value: `${summary.owned}`,
              variant: 'secondary',
            },
          ].map((metric, i) => (
            <Card key={i} variant="default" className="p-3.5">
              <div className="flex items-center gap-2 mb-2">
                <metric.icon
                  size={11}
                  className={cn(
                    metric.variant === 'primary' && 'text-brand-accent',
                    metric.variant === 'success' && 'text-emerald-500',
                    metric.variant === 'warning' && 'text-amber-500',
                    metric.variant === 'secondary' && 'text-zinc-600',
                  )}
                />
                <span className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest truncate">
                  {metric.label}
                </span>
              </div>
              <p className="text-sm font-mono font-bold text-zinc-100 tabular-nums uppercase truncate">
                {metric.value}
              </p>
            </Card>
          ))}
        </div>

        {(error || hubError) && shopData && (
          <Badge
            variant="warning"
            icon={AlertCircle}
            className="w-full py-2.5 rounded-md justify-center border-amber-500/10"
          >
            CONNECTION UNSTABLE: USING LOCAL CACHE
          </Badge>
        )}
      </header>

      <section className="space-y-6">
        <div className="flex items-center justify-between gap-4 px-1">
          <div className="flex items-center gap-2">
            <Boxes size={14} className="text-brand-accent" />
            <h2 className="text-[10px] font-bold text-zinc-100 uppercase tracking-widest">
              Available Characters
            </h2>
          </div>
          <Badge variant="secondary" size="xs">
            {summary.affordable} READY
          </Badge>
        </div>

        {inventory.length > 0 ? (
          <div className="grid grid-cols-2 xs:grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-3 sm:gap-4 px-0.5">
            {inventory.map((char) => (
              <CharacterCard key={char.id} character={char} onClick={() => onCharClick(char)} />
            ))}
          </div>
        ) : (
          <div className="py-20 border border-dashed border-white/5 rounded-lg bg-zinc-950/50">
            <EmptyState
              icon={Store}
              title="Nexus Offline"
              message="No characters available in the current rotation."
            />
          </div>
        )}
      </section>
    </div>
  );
};
