import { Coins, Dices, History, RefreshCw, Star, TrendingDown, TrendingUp } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { ErrorState } from '../components/ui/ErrorState';
import { Skeleton } from '../components/ui/Skeleton';
import { useApi } from '../hooks/useApi';
import { cn, formatNumber } from '../utils';

interface EconomyTransaction {
  id: number;
  type: string;
  amount: number;
  balance_after?: number | null;
  reference_id?: number | null;
  metadata?: Record<string, unknown>;
  created_at: string;
}

interface EconomyData {
  coins: number;
  dados: number;
  level: number;
  xp: number;
  received: number;
  spent: number;
  transactions: EconomyTransaction[];
}

const txLabel = (type: string) => {
  const labels: Record<string, string> = {
    sell_character: 'Venda de personagem',
    buyback_character: 'Recompra de personagem',
    buy_dado: 'Compra de Dado',
    buy_nickname: 'Alteração de nickname',
    buy_xcard_daily: 'Compra de XCard',
    aninexus_buy_dado: 'Compra de Dado',
    aninexus_referral_reward: 'Recompensa de indicação',
    duel_entry_refund: 'Reembolso de duelo',
    duel_entry_refund_account_deleted: 'Reembolso de duelo',
    message_refund_account_deleted: 'Reembolso de mensagem',
  };
  return labels[type] || type.replace(/_/g, ' ');
};

const formatDate = (raw: string) => {
  const date = new Date(raw);
  if (!Number.isFinite(date.getTime())) return '';
  return new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
};

export const Exchange = () => {
  const { data, loading, error, execute: refresh } = useApi<EconomyData>('/economy?limit=60');

  if (loading && !data) {
    return (
      <div className="pt-6 adaptive-px max-w-2xl mx-auto space-y-8">
        <Skeleton className="h-8 w-40 rounded-md" />
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20 rounded-md" />)}
        </div>
        <Skeleton className="h-80 rounded-md" />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="pt-6 max-w-2xl mx-auto adaptive-px">
        <ErrorState message={error} onAction={refresh} />
      </div>
    );
  }

  const transactions = data?.transactions || [];

  return (
    <div className="pt-6 max-w-2xl mx-auto adaptive-px space-y-8">
      <header className="flex items-start justify-between gap-6">
        <div className="space-y-1">
          <div className="flex items-center gap-2.5">
            <Coins size={20} className="text-brand-accent" />
            <h1 className="text-xl font-bold text-zinc-100 uppercase tracking-tight">Economia</h1>
          </div>
          <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest opacity-60">
            Saldo e movimentações da sua conta
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => refresh()}
          isLoading={loading}
          className="w-9 h-9 p-0"
          aria-label="Atualizar economia"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
        </Button>
      </header>

      <section className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { icon: Coins, label: 'Coins', value: data?.coins || 0, color: 'text-amber-500' },
          { icon: Dices, label: 'Dados', value: data?.dados || 0, color: 'text-brand-accent' },
          { icon: Star, label: 'Nível', value: data?.level || 1, color: 'text-purple-400' },
          { icon: TrendingUp, label: 'XP', value: data?.xp || 0, color: 'text-emerald-500' },
        ].map((stat) => (
          <Card key={stat.label} variant="default" className="p-4">
            <div className="flex items-center gap-2 mb-2">
              <stat.icon size={12} className={stat.color} />
              <span className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest">{stat.label}</span>
            </div>
            <p className="text-xl font-mono font-bold text-zinc-100 tabular-nums">{formatNumber(stat.value)}</p>
          </Card>
        ))}
      </section>

      <section className="grid grid-cols-2 gap-3">
        <Card variant="surface" className="p-4 border-emerald-500/10">
          <div className="flex items-center gap-2 mb-2 text-emerald-500">
            <TrendingUp size={13} />
            <span className="text-[9px] font-bold uppercase tracking-widest">Entradas registradas</span>
          </div>
          <p className="text-2xl font-mono font-bold text-zinc-100">+{formatNumber(data?.received || 0)}</p>
        </Card>
        <Card variant="surface" className="p-4 border-red-500/10">
          <div className="flex items-center gap-2 mb-2 text-red-400">
            <TrendingDown size={13} />
            <span className="text-[9px] font-bold uppercase tracking-widest">Saídas registradas</span>
          </div>
          <p className="text-2xl font-mono font-bold text-zinc-100">-{formatNumber(data?.spent || 0)}</p>
        </Card>
      </section>

      <section className="space-y-4">
        <div className="flex items-center gap-2 px-1">
          <History size={14} className="text-zinc-600" />
          <h2 className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest">Últimas movimentações</h2>
        </div>

        {transactions.length ? (
          <div className="space-y-2">
            {transactions.map((tx) => {
              const positive = Number(tx.amount) >= 0;
              return (
                <Card key={tx.id} variant="default" className="p-4 flex items-center justify-between gap-4">
                  <div className="min-w-0">
                    <p className="text-xs font-bold text-zinc-100 uppercase tracking-tight truncate">{txLabel(tx.type)}</p>
                    <p className="text-[9px] font-mono text-zinc-600 mt-1 uppercase">{formatDate(tx.created_at)}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className={cn('text-sm font-mono font-bold', positive ? 'text-emerald-500' : 'text-red-400')}>
                      {positive ? '+' : ''}{formatNumber(Number(tx.amount || 0))}
                    </p>
                    {tx.balance_after !== null && tx.balance_after !== undefined && (
                      <p className="text-[8px] font-mono text-zinc-700 mt-1">saldo {formatNumber(tx.balance_after)}</p>
                    )}
                  </div>
                </Card>
              );
            })}
          </div>
        ) : (
          <div className="py-16 border border-dashed border-white/5 rounded-lg bg-zinc-950/50 text-center">
            <p className="text-[9px] font-bold text-zinc-700 uppercase tracking-widest">Nenhuma movimentação registrada ainda</p>
          </div>
        )}
      </section>
    </div>
  );
};
