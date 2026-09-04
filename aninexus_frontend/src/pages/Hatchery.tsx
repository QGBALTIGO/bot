import { AnimatePresence, m } from 'framer-motion';
import { Activity, ArrowRight, CheckCircle2, Droplets, Egg, Flame, Target, Timer, Zap } from 'lucide-react';
import { useEffect, useState } from 'react';
import { apiFetch, getErrorMessage } from '../api/client';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { useToast } from '../components/ui/Toast';
import { useUser } from '../context/UserContext';
import { cn } from '../utils';

function getRemainingMinutes(egg: any, now: number | null) {
  if (egg.hatch_time && now !== null) {
    const hatchAt = new Date(egg.hatch_time).getTime();
    if (Number.isFinite(hatchAt)) {
      return Math.max(0, Math.ceil((hatchAt - now) / 60000));
    }
  }
  return Math.max(0, Number(egg.remaining_mins || 0));
}

export const Hatchery = () => {
  const { user, triggerRefresh } = useUser();
  const { addToast } = useToast();
  const [actionId, setActionId] = useState<string | null>(null);
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 30000);
    return () => window.clearInterval(timer);
  }, []);

  const handleHatch = async (eggId: string) => {
    setActionId(eggId);
    try {
      const result = await apiFetch(`/eggs/hatch/${eggId}`, { method: 'POST' });
      addToast(
        result?.character?.name ? `Hatched: ${result.character.name}` : 'Egg hatched successfully.',
        'success',
      );
      triggerRefresh();
    } catch (err: any) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setActionId(null);
    }
  };

  const handleIncubate = async (eggId: string) => {
    setActionId(eggId);
    try {
      await apiFetch(`/eggs/incubate/${eggId}`, { method: 'POST' });
      addToast('Incubation started.', 'success');
      triggerRefresh();
    } catch (err: any) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setActionId(null);
    }
  };

  const handleSell = async (eggId: string) => {
    setActionId(eggId);
    try {
      const result = await apiFetch(`/eggs/sell/${eggId}`, { method: 'POST' });
      addToast(result?.message || 'Egg sold.', 'success');
      triggerRefresh();
    } catch (err: any) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setActionId(null);
    }
  };

  const handlePurify = async (eggId: string) => {
    setActionId(eggId);
    try {
      const result = await apiFetch(`/eggs/purify/${eggId}`, { method: 'POST' });
      addToast(result?.message || 'Egg purified.', 'success');
      triggerRefresh();
    } catch (err: any) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setActionId(null);
    }
  };

  const handleFuse = async (tier: string) => {
    setActionId(`fuse_${tier}`);
    try {
      const result = await apiFetch(`/eggs/fuse/${tier}`, { method: 'POST' });
      addToast(result?.message || 'Eggs fused.', 'success');
      triggerRefresh();
    } catch (err: any) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setActionId(null);
    }
  };

  const eggs = (user?.eggs || []).map((egg: any, index: number) => {
    const remainingMins = getRemainingMinutes(egg, now);
    const isIncubating = egg.status === 'incubating';
    const isReady = isIncubating && remainingMins <= 0;
    const isFresh = egg.status === 'fresh';
    return { ...egg, index, remainingMins, isIncubating, isReady, isFresh };
  });

  const readyEggs = eggs.filter((egg) => egg.isReady);
  const incubatingEggs = eggs.filter((egg) => egg.isIncubating && !egg.isReady);
  const freshEggs = eggs.filter((egg) => egg.isFresh);
  const otherEggs = eggs.filter((egg) => !egg.isReady && !egg.isIncubating && !egg.isFresh);
  const incubationSlots = Number(user?.stats?.incubation_slots || 1);
  const activeIncubations = incubatingEggs.length + readyEggs.length;
  const passType = user?.stats?.pass_type || 'free';

  const renderEgg = (egg: any) => {
    const hasEggId = Boolean(egg.id);
    const waitMin = Number(egg.wait_min || egg.incubation_minutes || 0);
    const baseWaitMin = Number(egg.base_wait_min || egg.incubation_base_minutes || waitMin);
    const isBoosted = waitMin > 0 && baseWaitMin > waitMin;
    const tierLabel = String(egg.tier || 'COMMON').toUpperCase();

    return (
      <m.div
        layout
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95 }}
        key={egg.id || egg.index}
      >
        <Card
          variant="default"
          className={cn(
            'p-4 flex items-center justify-between group transition-all',
            egg.isReady && 'border-emerald-500/30 bg-emerald-500/[0.02]',
          )}
        >
          <div className="flex items-center gap-4 min-w-0">
            <div
              className={cn(
                'w-12 h-12 rounded-md flex items-center justify-center border shrink-0 transition-colors',
                egg.isReady
                  ? 'bg-emerald-500/10 border-emerald-500/20'
                  : 'bg-zinc-900 border-white/5',
              )}
            >
              <Egg
                size={20}
                className={cn(
                  'transition-all',
                  egg.isReady ? 'text-emerald-500' : 'text-zinc-500 group-hover:text-zinc-400',
                )}
              />
            </div>
            <div className="min-w-0 space-y-1">
              <div className="flex items-center gap-2">
                <p className="text-sm font-bold text-zinc-100 uppercase tracking-tight truncate">
                  {egg.name}
                </p>
                <Badge variant="secondary" size="xs" className="font-mono">
                  {tierLabel}
                </Badge>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {egg.isIncubating && !egg.isReady && (
                  <Badge variant="primary" icon={Timer} size="xs" className="font-bold">
                    {egg.remainingMins}m remaining
                  </Badge>
                )}
                {egg.isReady && (
                  <Badge variant="success" icon={CheckCircle2} size="xs" className="font-bold">
                    READY
                  </Badge>
                )}
                {egg.isFresh && (
                  <Badge
                    variant="secondary"
                    icon={Target}
                    size="xs"
                    className="font-bold opacity-70"
                  >
                    {waitMin > 0 ? `${waitMin}m Cycle` : 'Standby'}
                  </Badge>
                )}
                {isBoosted && (
                  <Badge variant="epic" icon={Zap} size="xs" className="font-bold">
                    BOOSTED
                  </Badge>
                )}
                {egg.is_corrupted && (
                  <Badge variant="danger" icon={Flame} size="xs" className="font-bold">
                    CORRUPTED
                  </Badge>
                )}
              </div>
            </div>
          </div>

          <div className="shrink-0 ml-4 flex items-center gap-2">
            {egg.isFresh && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleIncubate(egg.id)}
                  isLoading={actionId === egg.id}
                  disabled={!hasEggId || activeIncubations >= incubationSlots}
                  className="h-9 px-4"
                >
                  Start <ArrowRight size={14} className="ml-1.5" />
                </Button>
                {egg.is_corrupted && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handlePurify(egg.id)}
                    isLoading={actionId === egg.id}
                    disabled={!hasEggId}
                    className="h-9 px-4 border-amber-500/30 text-amber-400 hover:bg-amber-500/10"
                  >
                    Purify <Droplets size={14} className="ml-1.5" />
                  </Button>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleSell(egg.id)}
                  isLoading={actionId === egg.id}
                  disabled={!hasEggId}
                  className="h-9 px-4 text-zinc-400 hover:text-zinc-200"
                >
                  Sell {egg.sell_price ? `${egg.sell_price.toLocaleString()}🪙` : ''}
                </Button>
              </>
            )}

            {egg.isIncubating && !egg.isReady && (
              <div className="w-8 h-8 rounded-full border-2 border-brand-accent/10 flex items-center justify-center relative">
                <div className="absolute inset-0 rounded-full border-t-2 border-brand-accent animate-spin" />
                <div className="w-1 h-1 rounded-full bg-brand-accent" />
              </div>
            )}

            {egg.isReady && (
              <Button
                variant="accent"
                size="sm"
                onClick={() => handleHatch(egg.id)}
                isLoading={actionId === egg.id}
                disabled={!hasEggId}
                className="bg-emerald-500 hover:bg-emerald-400 h-9 px-6 shadow-[0_4px_12px_rgba(16,185,129,0.2)]"
              >
                Hatch
              </Button>
            )}
          </div>
        </Card>
      </m.div>
    );
  };

  const fuseGroups = ['common', 'gold', 'void', 'rare', 'legendary'].map((tier) => {
    const count = freshEggs.filter((egg) => egg.tier === tier).length;
    return { tier, count, canFuse: count >= 3 };
  }).filter((g) => g.count > 0);

  const renderSection = (title: string, sectionEggs: any[]) =>
    sectionEggs.length > 0 ? (
      <section className="space-y-3">
        <div className="flex items-center gap-2 px-1">
          <h2 className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest">{title}</h2>
          <div className="h-px flex-1 bg-white/[0.03]" />
        </div>
        <div className="space-y-3">
          <AnimatePresence mode="popLayout">{sectionEggs.map(renderEgg)}</AnimatePresence>
        </div>
      </section>
    ) : null;

  return (
    <div className="pt-6 max-w-2xl mx-auto adaptive-px space-y-8">
      <header className="space-y-1">
        <div className="flex items-center gap-2.5">
          <Egg className="text-brand-accent" size={20} />
          <h1 className="text-xl font-bold text-zinc-100 uppercase tracking-tight">Hatchery</h1>
        </div>
        <div className="flex items-center gap-2 opacity-60">
          <Activity size={10} className="text-zinc-500" />
          <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
            Hatch, fuse and sell your eggs
          </p>
        </div>
      </header>

      <section className="grid grid-cols-3 gap-3">
        {[
          {
            label: 'Active Slots',
            value: `${activeIncubations} / ${incubationSlots}`,
            color: 'text-zinc-100',
          },
          {
            label: 'Ready',
            value: `${readyEggs.length}`,
            color: readyEggs.length > 0 ? 'text-emerald-500' : 'text-zinc-500',
          },
          { label: 'Access', value: `${passType.toUpperCase()}`, color: 'text-brand-accent' },
        ].map((stat, i) => (
          <Card key={i} variant="default" className="p-3.5">
            <p className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest mb-1.5">
              {stat.label}
            </p>
            <p className={cn('text-xs font-mono font-bold uppercase', stat.color)}>{stat.value}</p>
          </Card>
        ))}
      </section>

      {fuseGroups.length > 0 && (
        <section className="space-y-3">
          <div className="flex items-center gap-2 px-1">
            <h2 className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest">
              Fusion — 3× same tier → 1× next tier
            </h2>
            <div className="h-px flex-1 bg-white/[0.03]" />
          </div>
          <div className="space-y-2">
            {fuseGroups.map((g) => (
              <Card key={g.tier} variant="default" className="p-3.5 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Flame size={16} className={g.canFuse ? 'text-brand-accent' : 'text-zinc-600'} />
                  <p className="text-xs font-bold text-zinc-200 uppercase tracking-tight">
                    {g.tier} <span className="text-zinc-500 font-mono">({g.count}/3)</span>
                  </p>
                </div>
                <Button
                  variant="accent"
                  size="sm"
                  onClick={() => handleFuse(g.tier)}
                  isLoading={actionId === `fuse_${g.tier}` && actionId.startsWith('fuse_')}
                  disabled={!g.canFuse}
                  className="h-8 px-4"
                >
                  Fuse
                </Button>
              </Card>
            ))}
          </div>
        </section>
      )}

      {eggs.length > 0 ? (
        <div className="space-y-8">
          {renderSection('READY TO HATCH', readyEggs)}
          {renderSection('IN PROGRESS', incubatingEggs)}
          {renderSection('NOT INCUBATED', freshEggs)}
          {renderSection('OTHER', otherEggs)}
        </div>
      ) : (
        <div className="py-20 flex flex-col items-center justify-center text-center space-y-6 border border-dashed border-white/5 rounded-lg bg-zinc-950/50">
          <div className="w-16 h-16 rounded-full bg-zinc-900 flex items-center justify-center border border-white/5">
            <Egg size={24} className="text-zinc-700" />
          </div>
          <div className="space-y-1 px-6">
            <p className="text-zinc-300 font-bold uppercase tracking-widest text-sm">
              No eggs yet
            </p>
            <p className="text-[10px] font-medium text-zinc-500 uppercase tracking-widest max-w-[200px] mx-auto leading-relaxed">
              Go hunt with your pet to find eggs.
            </p>
          </div>
        </div>
      )}
    </div>
  );
};
