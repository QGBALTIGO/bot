import { Activity, Coins, Shield, Swords, Timer, Trophy } from 'lucide-react';
import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { Skeleton } from '../components/ui/Skeleton';
import { useApi } from '../hooks/useApi';
import { cn, formatNumber } from '../utils';

interface BattleStats {
  total_battles: number;
  wins: number;
  losses: number;
  win_rate: number;
  friendly_wins: number;
  friendly_losses: number;
  wager_wins: number;
  wager_losses: number;
  surrendered: number;
  timeouts: number;
  cards_won: number;
  cards_lost: number;
  coins_spent: number;
  coins_refunded: number;
}

interface DuelHistoryItem {
  duel_id: number;
  opponent_id: number;
  opponent_name: string;
  mode: string;
  state: string;
  outcome: 'win' | 'loss' | 'draw' | 'active';
  resolution_reason?: string;
  rounds: number;
  reward_card_id?: number | null;
  reward_transfer_status?: string;
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}

const outcomeCopy: Record<DuelHistoryItem['outcome'], { label: string; className: string }> = {
  win: { label: 'Vitória', className: 'text-emerald-400' },
  loss: { label: 'Derrota', className: 'text-red-400' },
  draw: { label: 'Encerrado', className: 'text-zinc-400' },
  active: { label: 'Em andamento', className: 'text-brand-accent' },
};

const reasonLabel = (reason?: string) => {
  const labels: Record<string, string> = {
    all_cards_eliminated: 'Equipe eliminada',
    surrender: 'Desistência',
    round_timeout: 'Tempo da rodada esgotado',
    double_timeout: 'Tempo esgotado para os dois jogadores',
    challenge_timeout: 'Desafio expirado',
    prep_timeout: 'Preparação expirada',
    rejected: 'Desafio recusado',
    entry_fee_insufficient: 'Saldo insuficiente para o modo apostado',
  };
  return labels[String(reason || '')] || (reason ? reason.replace(/_/g, ' ') : '—');
};

const modeLabel = (mode: string) => (mode === 'wager' ? 'Apostado' : 'Amistoso');

export const Duels = () => {
  const {
    data: stats,
    loading: statsLoading,
    error: statsError,
    execute: reloadStats,
  } = useApi<BattleStats>('/battle/stats');
  const {
    data: history,
    loading: historyLoading,
    error: historyError,
    execute: reloadHistory,
  } = useApi<DuelHistoryItem[]>('/duels/history?limit=40', { initialData: [] });

  const loading = (statsLoading && !stats) || (historyLoading && !history);
  const reload = () => Promise.allSettled([reloadStats(), reloadHistory()]);

  if (loading) {
    return (
      <div className="pt-6 max-w-3xl mx-auto adaptive-px space-y-6">
        <Skeleton className="h-20 rounded-lg" />
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-24 rounded-lg" />
          ))}
        </div>
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-28 rounded-lg" />
        ))}
      </div>
    );
  }

  if ((statsError && !stats) || (historyError && !history)) {
    return (
      <div className="pt-6 max-w-3xl mx-auto adaptive-px">
        <ErrorState message={statsError || historyError || 'Não foi possível carregar os duelos.'} onAction={reload} />
      </div>
    );
  }

  const safeStats: BattleStats = stats || {
    total_battles: 0,
    wins: 0,
    losses: 0,
    win_rate: 0,
    friendly_wins: 0,
    friendly_losses: 0,
    wager_wins: 0,
    wager_losses: 0,
    surrendered: 0,
    timeouts: 0,
    cards_won: 0,
    cards_lost: 0,
    coins_spent: 0,
    coins_refunded: 0,
  };

  return (
    <div className="pt-6 max-w-3xl mx-auto adaptive-px space-y-8 select-none">
      <header className="space-y-1">
        <div className="flex items-center gap-2.5">
          <Swords size={21} className="text-red-400" />
          <h1 className="text-xl font-bold text-zinc-100 uppercase tracking-tight">Duelos</h1>
        </div>
        <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest opacity-70">
          Histórico e desempenho dos seus confrontos
        </p>
      </header>

      <section className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { icon: Swords, label: 'Duelos', value: safeStats.total_battles, className: 'text-zinc-300' },
          { icon: Trophy, label: 'Vitórias', value: safeStats.wins, className: 'text-emerald-400' },
          { icon: Shield, label: 'Derrotas', value: safeStats.losses, className: 'text-red-400' },
          { icon: Activity, label: 'Aproveitamento', value: `${Number(safeStats.win_rate || 0).toFixed(0)}%`, className: 'text-brand-accent' },
        ].map((item) => (
          <Card key={item.label} variant="default" className="p-4">
            <div className="flex items-center gap-2 mb-3">
              <item.icon size={13} className={item.className} />
              <span className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest">{item.label}</span>
            </div>
            <div className={cn('text-xl font-mono font-bold tabular-nums', item.className)}>
              {typeof item.value === 'number' ? formatNumber(item.value) : item.value}
            </div>
          </Card>
        ))}
      </section>

      <section className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Card variant="surface" className="p-5 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest">Amistosos</span>
            <Badge variant="secondary" size="xs">SEM APOSTA</Badge>
          </div>
          <div className="flex items-end gap-4 font-mono">
            <span className="text-lg font-bold text-emerald-400">{formatNumber(safeStats.friendly_wins)} V</span>
            <span className="text-lg font-bold text-red-400">{formatNumber(safeStats.friendly_losses)} D</span>
          </div>
        </Card>
        <Card variant="surface" className="p-5 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest">Apostados</span>
            <Badge variant="warning" size="xs">1 COIN</Badge>
          </div>
          <div className="flex items-end gap-4 font-mono">
            <span className="text-lg font-bold text-emerald-400">{formatNumber(safeStats.wager_wins)} V</span>
            <span className="text-lg font-bold text-red-400">{formatNumber(safeStats.wager_losses)} D</span>
          </div>
          <div className="flex items-center gap-2 text-[9px] font-bold text-zinc-600 uppercase tracking-widest">
            <Coins size={11} /> {formatNumber(safeStats.coins_spent)} gastos · {formatNumber(safeStats.coins_refunded)} devolvidos
          </div>
        </Card>
      </section>

      <section className="space-y-4">
        <div className="flex items-center justify-between px-1">
          <h2 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Últimos duelos</h2>
          <span className="text-[9px] font-mono text-zinc-700">{history?.length || 0}</span>
        </div>

        {history && history.length > 0 ? (
          <div className="space-y-3">
            {history.map((duel) => {
              const outcome = outcomeCopy[duel.outcome] || outcomeCopy.draw;
              const when = duel.finished_at || duel.started_at || duel.created_at;
              const date = when ? new Date(when) : null;
              return (
                <Card key={duel.duel_id} variant="default" className="p-4 space-y-3">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <p className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest mb-1">Adversário</p>
                      <p className="text-sm font-bold text-zinc-100 truncate uppercase tracking-tight">{duel.opponent_name}</p>
                      <p className="text-[9px] font-mono text-zinc-600 mt-1">ID {duel.opponent_id}</p>
                    </div>
                    <div className="text-right shrink-0">
                      <p className={cn('text-xs font-bold uppercase', outcome.className)}>{outcome.label}</p>
                      <p className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest mt-1">{modeLabel(duel.mode)}</p>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-2 pt-3 border-t border-white/5">
                    <Badge variant="secondary" size="xs" icon={Timer}>{Math.max(0, duel.rounds || 0)} rodadas</Badge>
                    <span className="text-[9px] text-zinc-500">{reasonLabel(duel.resolution_reason)}</span>
                    {date && Number.isFinite(date.getTime()) && (
                      <span className="ml-auto text-[8px] font-mono text-zinc-700">
                        {date.toLocaleDateString('pt-BR')}
                      </span>
                    )}
                  </div>
                </Card>
              );
            })}
          </div>
        ) : (
          <EmptyState
            icon={Swords}
            title="Nenhum duelo ainda"
            message="Para desafiar alguém, use /duelo respondendo à mensagem da pessoa em um grupo."
          />
        )}
      </section>
    </div>
  );
};
