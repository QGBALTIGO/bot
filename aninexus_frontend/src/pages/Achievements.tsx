import 'react';
import { AnimatePresence, m } from 'framer-motion';
import {
  Activity,
  BadgeCheck,
  CheckCircle2,
  Loader2,
  Lock,
  Medal,
  Target,
  Trophy,
} from 'lucide-react';
import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { ErrorState } from '../components/ui/ErrorState';
import { ProgressBar } from '../components/ui/ProgressBar';
import { Skeleton } from '../components/ui/Skeleton';
import { useApi } from '../hooks/useApi';
import { cn } from '../utils';

interface Achievement {
  id: string;
  name: string;
  description: string;
  icon: string;
  reward_xp: number;
  unlocked: boolean;
}

export const Achievements = () => {
  const {
    data: achievements,
    loading,
    error,
    execute: fetchAchievements,
  } = useApi<Achievement[]>('/achievements/list');

  if (loading && !achievements)
    return (
      <div className="pt-6 adaptive-px max-w-2xl mx-auto space-y-8">
        <div className="flex items-center gap-3">
          <Skeleton className="w-10 h-10 rounded-md" />
          <div className="space-y-1.5">
            <Skeleton className="h-6 w-40 rounded-md" />
            <Skeleton className="h-3 w-56 rounded-md opacity-50" />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Skeleton className="h-24 rounded-md" />
          <Skeleton className="h-24 rounded-md" />
        </div>
        <div className="space-y-3">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-20 rounded-md" />
          ))}
        </div>
      </div>
    );

  if (error && !achievements)
    return (
      <div className="pt-6 adaptive-px max-w-2xl mx-auto">
        <ErrorState message={error} onAction={fetchAchievements} />
      </div>
    );

  const sortedAchievements = [...(achievements || [])].sort((a, b) => {
    if (a.unlocked === b.unlocked) return 0;
    return a.unlocked ? -1 : 1;
  });

  const unlockedCount = achievements?.filter((a) => a.unlocked).length || 0;
  const totalCount = achievements?.length || 0;
  const progressPercent = totalCount > 0 ? Math.round((unlockedCount / totalCount) * 100) : 0;

  return (
    <div className="pt-6 max-w-2xl mx-auto adaptive-px space-y-8 select-none">
      <header className="space-y-6">
        <div className="flex items-center gap-2.5">
          <BadgeCheck className="text-brand-accent" size={20} />
          <div className="flex flex-col">
            <h1 className="text-xl font-bold text-zinc-100 uppercase tracking-tight">Milestones</h1>
            <div className="flex items-center gap-1.5 opacity-60">
              <Target size={10} className="text-zinc-500" />
              <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                Bragging rights you've earned
              </p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Card variant="surface" className="p-4 flex flex-col justify-between">
            <div className="flex items-center justify-between mb-4">
              <span className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest">
                Progress
              </span>
              <span className="text-[10px] font-mono font-bold text-zinc-400 tabular-nums">
                {unlockedCount} / {totalCount}
              </span>
            </div>
            <div className="text-2xl font-mono font-bold text-zinc-100 leading-none mb-4">
              {progressPercent}%
            </div>
            <ProgressBar current={unlockedCount} total={totalCount} compact showValue={false} />
          </Card>

          <Card variant="default" className="p-4 flex flex-col justify-between">
            <div className="flex items-center justify-between mb-4">
              <span className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest">
                Rank
              </span>
              <Medal size={14} className="text-emerald-500" />
            </div>
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded bg-brand-accent/10 flex items-center justify-center shrink-0">
                <Activity size={16} className="text-brand-accent" />
              </div>
              <div className="flex flex-col">
                <span className="text-[10px] font-bold text-zinc-100 uppercase tracking-wider">
                  Collector
                </span>
                <span className="text-[8px] font-bold text-emerald-500 uppercase tracking-widest">
                  Keep hatching
                </span>
              </div>
            </div>
          </Card>
        </div>
      </header>

      <div className="space-y-3">
        <AnimatePresence mode="popLayout">
          {sortedAchievements.map((ach) => (
            <m.div
              layout
              key={ach.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <Card
                variant="default"
                className={cn(
                  'p-4 flex items-center gap-4 transition-all',
                  !ach.unlocked && 'opacity-40 grayscale',
                )}
              >
                <div
                  className={cn(
                    'w-12 h-12 rounded flex items-center justify-center border shrink-0 transition-colors',
                    ach.unlocked ? 'bg-zinc-900 border-white/10' : 'bg-zinc-950 border-white/5',
                  )}
                >
                  {ach.unlocked ? (
                    <Trophy size={20} className="text-zinc-100" />
                  ) : (
                    <Lock size={18} className="text-zinc-800" />
                  )}
                </div>

                <div className="flex-1 min-w-0 space-y-1">
                  <div className="flex items-center gap-2">
                    <h3 className="text-xs font-bold text-zinc-100 uppercase tracking-tight truncate">
                      {ach.name}
                    </h3>
                    {ach.unlocked && (
                      <Badge variant="success" size="xs">
                        CLEAR
                      </Badge>
                    )}
                  </div>
                  <p className="text-[10px] font-medium text-zinc-500 uppercase tracking-widest leading-snug line-clamp-1">
                    {ach.description}
                  </p>
                </div>

                <div className="shrink-0 flex items-center gap-3 pl-4 border-l border-white/5">
                  <div className="text-[10px] font-mono font-bold text-brand-accent">
                    +{ach.reward_xp} XP
                  </div>
                  {ach.unlocked && (
                    <div className="w-5 h-5 rounded bg-emerald-500/10 flex items-center justify-center text-emerald-500">
                      <CheckCircle2 size={12} strokeWidth={3} />
                    </div>
                  )}
                </div>
              </Card>
            </m.div>
          ))}
        </AnimatePresence>
      </div>

      {loading && achievements && (
        <div className="flex justify-center py-12">
          <Loader2 size={24} className="animate-spin text-zinc-700" />
        </div>
      )}
    </div>
  );
};
