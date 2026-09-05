import { AnimatePresence, m } from 'framer-motion';
import {
  BookOpen,
  Brain,
  ChartNoAxesColumnIncreasing,
  Coins,
  Radio,
  TrendingUp,
  Trophy,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Avatar } from '../components/Avatar';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { ErrorState } from '../components/ui/ErrorState';
import { Skeleton } from '../components/ui/Skeleton';
import { useApi } from '../hooks/useApi';
import { cn, formatNumber } from '../utils';

interface LeaderboardUser {
  id: number | string;
  rank?: number;
  first_name?: string;
  last_name?: string;
  full_name?: string;
  username?: string;
  avatar?: string | null;
  value: number;
}

const getDisplayName = (user: LeaderboardUser, index: number) => {
  const name = (user.full_name || user.first_name || '').trim();
  if (name && name.toLowerCase() !== 'user') return name;
  if (user.username) return user.username;
  return `Usuário ${String(user.id || index + 1)
    .slice(-4)
    .toUpperCase()}`;
};

const getInitials = (name: string) => {
  const parts = name.replace(/^@/, '').split(/\s+/).filter(Boolean);
  if (parts.length === 0) return 'U';
  return parts
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase();
};

export const Leaderboard = () => {
  const [metric, setMetric] = useState('collection');
  const [visible, setVisible] = useState(50);
  const {
    data,
    loading,
    error,
    execute: fetchLeaderboard,
  } = useApi<LeaderboardUser[]>(`/leaderboard?metric=${metric}`, {}, [metric]);

  useEffect(() => {
    setVisible(50);
  }, []);

  // Atualização automática sem depender de WebSocket no runtime atual.
  const fetchRef = useRef(fetchLeaderboard);
  fetchRef.current = fetchLeaderboard;

  useEffect(() => {
    const timer = window.setInterval(() => {
      void fetchRef.current();
    }, 30000);
    return () => window.clearInterval(timer);
  }, []);

  const METRICS = [
    { id: 'collection', label: 'Coleção', icon: BookOpen },
    { id: 'coins', label: 'Coins', icon: Coins },
    { id: 'level', label: 'Nível', icon: TrendingUp },
    { id: 'termo', label: 'Termo', icon: Brain },
    { id: 'memory', label: 'Memória', icon: ChartNoAxesColumnIncreasing },
  ];
  const activeMetric = METRICS.find((m) => m.id === metric);

  return (
    <div className="pt-6 max-w-2xl mx-auto adaptive-px space-y-8">
      <header className="space-y-1">
        <div className="flex items-center gap-2.5">
          <Trophy className="text-amber-500" size={20} />
          <h1 className="text-xl font-bold text-zinc-100 uppercase tracking-tight">Ranking</h1>
        </div>
        <div className="flex items-center gap-2 opacity-60">
          <Radio size={10} className="text-zinc-500" />
          <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
            Melhores jogadores do AniNexus
          </p>
          <span
            className="w-1.5 h-1.5 rounded-full bg-emerald-500"
            title="Atualização automática a cada 30 segundos"
          />
        </div>
      </header>

      <div className="flex gap-2 overflow-x-auto no-scrollbar -mx-5 px-5">
        {METRICS.map((m) => {
          const isActive = metric === m.id;
          return (
            <button
              key={m.id}
              onClick={() => {
                window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
                setMetric(m.id);
              }}
              className={cn(
                'h-10 px-4 rounded-md flex items-center gap-2 border transition-all whitespace-nowrap text-[10px] font-bold uppercase tracking-widest shrink-0',
                isActive
                  ? 'bg-zinc-100 text-zinc-950 border-zinc-100'
                  : 'bg-zinc-900 border-white/5 text-zinc-500 hover:text-zinc-200 hover:border-white/10',
              )}
            >
              <m.icon size={14} className={isActive ? 'text-zinc-950' : 'text-zinc-600'} />
              <span>{m.label}</span>
            </button>
          );
        })}
      </div>

      <div className="space-y-3">
        <AnimatePresence mode="wait">
          {error && !data ? (
            <div className="py-12">
              <ErrorState message={error} onAction={fetchLeaderboard} />
            </div>
          ) : loading ? (
            <div className="space-y-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-16 w-full rounded-md" />
              ))}
            </div>
          ) : data && data.length > 0 ? (
            <m.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-2">
              {data.slice(0, visible).map((user, i) => {
                const displayName = getDisplayName(user, i);
                const rank = user.rank || i + 1;

                return (
                  <Card
                    key={user.id}
                    variant="default"
                    className={cn(
                      'p-3 flex items-center justify-between transition-all',
                      rank === 1
                        ? 'border-amber-500/30 bg-amber-500/[0.02]'
                        : rank === 2
                          ? 'border-zinc-400/20'
                          : rank === 3
                            ? 'border-amber-700/20'
                            : '',
                    )}
                  >
                    <div className="flex items-center gap-4 min-w-0">
                      <div
                        className={cn(
                          'w-9 h-9 rounded flex items-center justify-center text-xs font-mono font-bold shrink-0 border transition-colors',
                          rank === 1
                            ? 'bg-amber-500/20 text-amber-500 border-amber-500/30'
                            : rank === 2
                              ? 'bg-zinc-400/20 text-zinc-300 border-zinc-400/30'
                              : rank === 3
                                ? 'bg-amber-700/20 text-amber-600 border-amber-700/30'
                                : 'bg-zinc-900 text-zinc-600 border-white/5',
                        )}
                      >
                        {rank}
                      </div>
                      <div className="flex items-center gap-3 min-w-0">
                        <Avatar
                          src={user.avatar}
                          alt={displayName}
                          fallbackText={getInitials(displayName)}
                          className="w-10 h-10 rounded-md bg-zinc-900 border border-white/5"
                        />
                        <div className="min-w-0 space-y-0.5">
                          <p className="text-[13px] font-bold text-zinc-100 uppercase tracking-tight truncate">
                            {displayName}
                          </p>
                          <p className="text-[9px] font-bold text-zinc-600 truncate uppercase tracking-widest leading-none">
                            {user.username
                              ? `@${user.username}`
                              : `ID ${String(user.id).slice(0, 8)}`}
                          </p>
                        </div>
                      </div>
                    </div>
                    <div className="text-right shrink-0 pl-4 space-y-1">
                      <div className="flex items-center justify-end gap-2 h-7 px-2.5 rounded bg-zinc-900 border border-white/5">
                        <span className="text-[11px] font-mono font-bold text-zinc-100 tabular-nums">
                          {formatNumber(user.value)}
                        </span>
                        {activeMetric && (
                          <activeMetric.icon
                            size={11}
                            className={cn(
                              rank === 1
                                ? 'text-amber-500'
                                : rank === 2
                                  ? 'text-zinc-400'
                                  : rank === 3
                                    ? 'text-amber-700'
                                    : 'text-zinc-600',
                            )}
                          />
                        )}
                      </div>
                      <p className="text-[8px] font-bold text-zinc-700 uppercase tracking-widest">
                        {activeMetric?.label || metric}
                      </p>
                    </div>
                  </Card>
                );
              })}

              {data && visible < data.length && (
                <div className="flex justify-center pt-2">
                  <Button variant="outline" size="sm" onClick={() => setVisible((v) => v + 50)}>
                    Carregar mais ({data.length - visible} ocultos)
                  </Button>
                </div>
              )}
            </m.div>
          ) : (
            <div className="py-20 border border-dashed border-white/5 rounded-lg bg-zinc-950/50 text-center flex flex-col items-center justify-center space-y-3">
              <div className="w-12 h-12 rounded-full border border-white/5 flex items-center justify-center opacity-10">
                <ChartNoAxesColumnIncreasing size={24} />
              </div>
              <p className="text-[9px] font-bold text-zinc-700 uppercase tracking-widest">
                Sem dados de ranking
              </p>
            </div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
};
