import { AnimatePresence, m } from 'framer-motion';
import { CheckCircle2, Dice5, Gift, Lock, TicketCheck, Trophy } from 'lucide-react';
import { useCallback, useState } from 'react';
import { apiFetch, getErrorMessage } from '../api/client';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { ErrorState } from '../components/ui/ErrorState';
import { ProgressBar } from '../components/ui/ProgressBar';
import { Skeleton } from '../components/ui/Skeleton';
import { useToast } from '../components/ui/Toast';
import { useUser } from '../context/UserContext';
import { useApi } from '../hooks/useApi';
import { cn } from '../utils';

function rewardLabel(track: any) {
  const reward = track?.free;
  if (!reward) return 'Recompensa';
  if (reward.label) return String(reward.label);
  if (reward.type === 'shards' && Number(reward.amount || 0) > 0) {
    return `+${Number(reward.amount)} Coin${Number(reward.amount) === 1 ? '' : 's'}`;
  }
  return 'Recompensa';
}

export const Pass = () => {
  const { refreshUser } = useUser();
  const { addToast } = useToast();
  const {
    data: passData,
    loading,
    error,
    execute: fetchPassData,
  } = useApi<any>('/pass_data');
  const [claiming, setClaiming] = useState<number | null>(null);

  const refreshAll = useCallback(async () => {
    await Promise.allSettled([fetchPassData(), refreshUser()]);
  }, [fetchPassData, refreshUser]);

  const handleClaim = async (level: number) => {
    setClaiming(level);
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    try {
      const result = await apiFetch(`/claim_level/${level}`, { method: 'POST' });
      if (result.status === 'already_claimed') {
        addToast('Essa recompensa já foi resgatada.', 'info');
      } else {
        const parts = [];
        if (Number(result.shards || 0) > 0) parts.push(`+${result.shards} Coin`);
        if (Number(result.xp || 0) > 0) parts.push(`+${result.xp} XP`);
        if (Number(result.eggs || 0) > 0) parts.push(`+${result.eggs} Dado`);
        addToast(parts.length ? parts.join(' • ') : 'Recompensa resgatada.', 'success');
      }
      await refreshAll();
    } catch (err) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setClaiming(null);
    }
  };

  if (error && !passData) {
    return (
      <div className="pt-6 adaptive-px max-w-2xl mx-auto">
        <ErrorState message={error} onAction={fetchPassData} />
      </div>
    );
  }

  if (loading || !passData) {
    return (
      <div className="pt-6 adaptive-px max-w-2xl mx-auto space-y-8">
        <Skeleton className="h-10 w-56 rounded-md" />
        <Skeleton className="h-3 w-full rounded-full" />
        <Skeleton className="h-28 w-full rounded-md" />
        <Skeleton className="h-72 w-full rounded-md" />
      </div>
    );
  }

  const userLevel = Math.min(Number(passData.level || 1), Number(passData.max_level || 50));
  const maxLevel = Number(passData.max_level || 50);
  const claimedLevels: number[] = Array.isArray(passData.claimed_levels)
    ? passData.claimed_levels.map(Number)
    : [];
  const milestones: number[] = Array.isArray(passData.milestones)
    ? passData.milestones.map(Number)
    : [];

  return (
    <div className="pt-6 max-w-2xl mx-auto adaptive-px space-y-8 select-none">
      <header className="space-y-6">
        <div className="flex items-center justify-between gap-6">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5">
              <TicketCheck size={20} className="text-brand-accent" />
              <h1 className="text-xl font-bold text-zinc-100 uppercase tracking-tight">
                {passData.season_name || 'Temporada AniNexus'}
              </h1>
            </div>
            <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest opacity-60">
              Seu nível real do Source desbloqueia recompensas da temporada
            </p>
          </div>
          <div className="px-4 py-2 bg-zinc-900 border border-white/5 rounded-md text-center">
            <p className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest mb-0.5">NÍVEL</p>
            <p className="text-xl font-mono font-bold text-zinc-100 leading-none">{userLevel}</p>
          </div>
        </div>

        <ProgressBar current={userLevel} total={maxLevel} label="Progresso da temporada" compact />
      </header>

      <Card variant="surface" className="p-5 flex items-center gap-4">
        <div className="w-11 h-11 rounded-lg bg-brand-accent/10 border border-brand-accent/20 flex items-center justify-center shrink-0">
          <Trophy size={20} className="text-brand-accent" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest">Trilha gratuita</div>
          <div className="text-sm font-bold text-zinc-100 uppercase tracking-tight mt-1">
            {claimedLevels.length} recompensas resgatadas
          </div>
        </div>
        <Badge variant="secondary" size="xs">SOURCE XP</Badge>
      </Card>

      <section className="space-y-4">
        <div className="flex items-center justify-between px-1">
          <h2 className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest">Recompensas</h2>
          <Badge variant="secondary" size="xs">
            {claimedLevels.length} / {milestones.length}
          </Badge>
        </div>

        <div className="space-y-3">
          <AnimatePresence mode="popLayout">
            {milestones.map((level) => {
              const track = passData.tracks?.[level];
              if (!track) return null;
              const reached = userLevel >= level;
              const claimed = claimedLevels.includes(level);
              const label = rewardLabel(track);
              const isDice = label.toLowerCase().includes('dado');

              return (
                <m.div
                  layout
                  key={level}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                >
                  <Card
                    variant="default"
                    className={cn(
                      'p-4 flex items-center justify-between gap-4 transition-all',
                      !reached && 'opacity-35',
                      claimed && 'border-emerald-500/10',
                    )}
                  >
                    <div className="flex items-center gap-4 min-w-0">
                      <div
                        className={cn(
                          'w-11 h-11 rounded flex flex-col items-center justify-center border font-mono font-bold shrink-0',
                          reached
                            ? 'border-brand-accent/30 text-brand-accent bg-brand-accent/5'
                            : 'border-white/5 text-zinc-700 bg-zinc-950',
                        )}
                      >
                        <span className="text-[7px] opacity-50 leading-none">NÍV</span>
                        <span className="text-lg leading-none">{level}</span>
                      </div>

                      <div className="min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          {isDice ? <Dice5 size={13} className="text-purple-400" /> : <Gift size={13} className="text-amber-500" />}
                          <p className="text-xs font-bold text-zinc-100 uppercase tracking-tight truncate">{label}</p>
                        </div>
                        <p className="text-[9px] text-zinc-600 font-bold uppercase tracking-widest">
                          {claimed ? 'Resgatada' : reached ? 'Disponível' : `Alcance o nível ${level}`}
                        </p>
                      </div>
                    </div>

                    <div className="shrink-0">
                      {claimed ? (
                        <div className="w-9 h-9 rounded bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-500">
                          <CheckCircle2 size={16} />
                        </div>
                      ) : reached ? (
                        <Button
                          onClick={() => handleClaim(level)}
                          isLoading={claiming === level}
                          variant="outline"
                          size="sm"
                          className="h-9 px-4"
                        >
                          Resgatar
                        </Button>
                      ) : (
                        <Lock size={16} className="text-zinc-800" />
                      )}
                    </div>
                  </Card>
                </m.div>
              );
            })}
          </AnimatePresence>
        </div>
      </section>
    </div>
  );
};
