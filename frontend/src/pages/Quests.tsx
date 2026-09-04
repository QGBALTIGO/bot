import { AnimatePresence, m } from 'framer-motion';
import { CheckCircle2, ClipboardList, Lock, Target } from 'lucide-react';
import { useState } from 'react';
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
import { cn, formatNumber } from '../utils';

interface Quest {
  id: string;
  name: string;
  description: string;
  icon: string;
  reward_xp: number;
  reward_shards: number;
  progress: number;
  target: number;
  claimed: boolean;
  locked?: boolean;
}

interface QuestItemProps {
  quest: Quest;
  onClaim: (questId: string) => void;
  claiming: string | null;
}

const QuestItem = ({ quest, onClaim, claiming }: QuestItemProps) => {
  const isComplete = quest.progress >= quest.target;
  const isClaiming = claiming === quest.id;

  return (
    <m.div layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
      <Card
        variant="default"
        className={cn(
          'p-4 transition-all',
          quest.locked && 'opacity-40 grayscale',
          quest.claimed && 'border-emerald-500/10',
        )}
      >
        <div className="flex justify-between items-start mb-4 gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2.5 mb-1.5">
              <div
                className={cn(
                  'w-8 h-8 rounded flex items-center justify-center shrink-0 border transition-colors',
                  isComplete
                    ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-500'
                    : 'bg-zinc-900 border-white/5 text-brand-accent',
                )}
              >
                <Target size={14} />
              </div>
              <h3 className="text-sm font-bold text-zinc-100 uppercase tracking-tight truncate">
                {quest.name}
              </h3>
            </div>
            <p className="text-[10px] text-zinc-500 font-bold uppercase tracking-widest line-clamp-1 pl-0.5">
              {quest.description}
            </p>
          </div>
          <div className="flex flex-col items-end shrink-0">
            <div className="flex items-center gap-1.5 h-6 px-2 rounded bg-zinc-900 border border-white/5">
              <span className="text-[10px] font-mono font-bold text-zinc-100 leading-none">
                {formatNumber(quest.reward_shards)}
              </span>
              <span className="text-[8px] font-bold text-amber-500 uppercase tracking-widest leading-none">
                Coins
              </span>
            </div>
            <div className="text-[9px] font-mono font-bold text-zinc-600 uppercase mt-1 px-1">
              +{quest.reward_xp} XP
            </div>
          </div>
        </div>

        <div className="flex items-center gap-5">
          <div className="flex-1">
            <ProgressBar
              current={quest.progress}
              total={quest.target}
              compact
              label="Progress"
              variant={quest.claimed ? 'success' : 'default'}
            />
          </div>

          <div className="shrink-0 pt-2">
            {quest.claimed ? (
              <div className="w-8 h-8 rounded bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-500">
                <CheckCircle2 size={16} strokeWidth={3} />
              </div>
            ) : (
              <Button
                variant={isComplete ? 'accent' : 'outline'}
                size="sm"
                onClick={() => onClaim(quest.id)}
                disabled={quest.locked || !isComplete || isClaiming}
                className="h-9 px-4"
                isLoading={isClaiming}
              >
                {isComplete ? 'Claim' : <Lock size={14} />}
              </Button>
            )}
          </div>
        </div>
      </Card>
    </m.div>
  );
};

interface QuestsResponse {
  daily: Quest[];
  weekly: Quest[];
  pass: Quest[];
  pass_type: string;
}

export const Quests = () => {
  const {
    data: questsData,
    loading,
    error,
    execute: fetchQuests,
  } = useApi<QuestsResponse>('/quests');
  const { addToast } = useToast();
  const { triggerRefresh } = useUser();
  const [claiming, setClaiming] = useState<string | null>(null);

  const handleClaim = async (questId: string) => {
    setClaiming(questId);
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    try {
      const res = await apiFetch(`/quests/claim/${questId}`, { method: 'POST' });
      addToast(`Mission complete: +${res.reward_shards} Coins`, 'success');
      triggerRefresh();
      fetchQuests().catch(() => undefined);
    } catch (err: any) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setClaiming(null);
    }
  };

  if (loading && !questsData)
    return (
      <div className="pt-6 adaptive-px max-w-2xl mx-auto space-y-6">
        <Skeleton className="h-8 w-40 rounded-md" />
        <Skeleton className="h-4 w-60 rounded-md opacity-50 mb-6" />
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-28 rounded-md" />
        ))}
      </div>
    );

  if (error && !questsData)
    return (
      <div className="pt-6 max-w-2xl mx-auto adaptive-px">
        <ErrorState message={error} onAction={fetchQuests} />
      </div>
    );

  const renderQuestSection = (title: string, quests: Quest[]) => (
    <section className="space-y-4">
      <div className="flex items-center justify-between px-1">
        <h2 className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest">{title}</h2>
        <Badge variant="secondary" size="xs" className="opacity-60">
          {quests.filter((q) => q.claimed).length} / {quests.length}
        </Badge>
      </div>
      {quests.length > 0 ? (
        <div className="space-y-3">
          <AnimatePresence mode="popLayout">
            {quests.map((quest) => (
              <QuestItem key={quest.id} quest={quest} onClaim={handleClaim} claiming={claiming} />
            ))}
          </AnimatePresence>
        </div>
      ) : (
        <div className="py-12 border border-dashed border-white/5 rounded-lg bg-zinc-950/50 text-center flex flex-col items-center justify-center space-y-2">
          <p className="text-[9px] font-bold text-zinc-700 uppercase tracking-widest">
            No Missions Available
          </p>
        </div>
      )}
    </section>
  );

  return (
    <div className="pt-6 max-w-2xl mx-auto adaptive-px space-y-10">
      <header className="space-y-1">
        <div className="flex items-center gap-2.5">
          <ClipboardList className="text-brand-accent" size={20} />
          <h1 className="text-xl font-bold text-zinc-100 uppercase tracking-tight">Missions</h1>
        </div>
        <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest opacity-60">
          Operational objectives & bounties
        </p>
      </header>

      <div className="space-y-10">
        {renderQuestSection('DAILY OPERATIONS', questsData?.daily || [])}
        {renderQuestSection('STRATEGIC WEEKLY', questsData?.weekly || [])}
        {renderQuestSection('PASS CLEARANCE', questsData?.pass || [])}
      </div>
    </div>
  );
};
