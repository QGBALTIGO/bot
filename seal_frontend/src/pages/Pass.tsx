import { AnimatePresence, m } from 'framer-motion';
import { Crown, Gift, Lock, Star, Target, TicketCheck, TrendingUp } from 'lucide-react';
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
import { cn, formatNumber } from '../utils';

const EGG_TIER_LABELS: Record<number, string> = {
  1: 'Common',
  2: 'Uncommon',
  3: 'Rare',
  4: 'Epic',
  5: 'Legendary',
};

const TIER_ORDER = ['free', 'premium', 'elite'];
const TIER_ICON = {
  free: TicketCheck,
  premium: Star,
  elite: Crown,
};

function formatReward(track: any, tier: string) {
  const reward = track?.[tier] ?? track?.free;
  if (!reward) return 'None';
  const extra = Number(track?.[`${tier}_extra_amount`] || 0);
  const base =
    reward.type === 'shards'
      ? `${formatNumber(reward.amount)} Coins`
      : `${EGG_TIER_LABELS[Number(reward.tier)] || `Tier ${reward.tier}`} Egg`;
  return extra > 0 ? `${base} + ${formatNumber(extra)} Coins` : base;
}

function bankSummary(bank: Record<string, number> = {}) {
  const shards = Number(bank.shards || 0);
  const eggs = Object.entries(bank)
    .filter(([key]) => key.startsWith('eggs_t'))
    .reduce((sum, [, value]) => sum + Number(value || 0), 0);
  return { shards, eggs, hasValue: shards > 0 || eggs > 0 };
}

function percentBonus(multiplier: number | undefined, invert = false) {
  const value = Number(multiplier || 1);
  if (invert) return `${Math.round((1 - value) * 100)}% Speed`;
  return `+${Math.round((value - 1) * 100)}%`;
}

export const Pass = () => {
  const { refreshUser } = useUser();
  const { addToast } = useToast();
  const {
    data: passData,
    loading: passLoading,
    error,
    execute: fetchPassData,
  } = useApi<any>('/pass_data');
  const [claiming, setClaiming] = useState<number | null>(null);
  const [claimingBank, setClaimingBank] = useState(false);
  const [upgrading, setUpgrading] = useState<string | null>(null);
  const [buyingLevels, setBuyingLevels] = useState(false);

  const refreshAll = useCallback(async () => {
    await fetchPassData();
    await refreshUser();
  }, [fetchPassData, refreshUser]);

  const handleClaim = async (level: number) => {
    setClaiming(level);
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    try {
      const res = await apiFetch(`/claim_level/${level}`, { method: 'POST' });
      if (res.status === 'success' || res.status === 'already_claimed') {
        addToast(
          res.status === 'already_claimed' ? 'Reward already claimed' : `Level ${level} claimed`,
          'success',
        );
        await refreshAll();
      }
    } catch (err: any) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setClaiming(null);
    }
  };

  const handleClaimBank = async () => {
    setClaimingBank(true);
    try {
      const res = await apiFetch('/claim_bank', { method: 'POST' });
      addToast(res.message || 'Vault claimed.', 'success');
      await refreshAll();
    } catch (err: any) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setClaimingBank(false);
    }
  };

  const handleBuyLevel = async () => {
    const cost = Number(passData?.level_buy_cost || 0);
    const tg = window.Telegram?.WebApp;
    const doBuy = async () => {
      setBuyingLevels(true);
      try {
        await apiFetch('/buy_level?levels=1', { method: 'POST' });
        addToast('Level purchased.', 'success');
        await refreshAll();
      } catch (err: any) {
        addToast(getErrorMessage(err), 'error');
      } finally {
        setBuyingLevels(false);
      }
    };
    // Call showConfirm bound to the WebApp object; detaching it can throw
    // "Illegal invocation" in some WebViews.
    if (tg?.showConfirm) {
      tg.showConfirm(`Buy 1 level for ${formatNumber(cost)} Coins?`, (ok) => {
        if (ok) doBuy();
      });
      return;
    }
    await doBuy();
  };

  const handleUpgrade = async (tier: string) => {
    const tg = window.Telegram?.WebApp;
    if (!tg?.openInvoice) {
      addToast('Open this inside Telegram to upgrade.', 'error');
      return;
    }

    setUpgrading(tier);
    try {
      const invoice = await apiFetch(`/shop/pass_invoice/${tier}`, { method: 'POST' });
      let settled = false;
      const settle = () => {
        if (settled) return;
        settled = true;
        setUpgrading(null);
      };
      // Safety net: some clients never fire the invoice callback, which would
      // otherwise leave the button stuck loading forever.
      const fallback = window.setTimeout(settle, 120000);
      tg.openInvoice(invoice.invoice_url, async (status: string) => {
        window.clearTimeout(fallback);
        if (status === 'paid') {
          addToast(`${tier.toUpperCase()} status activated`, 'success');
          window.setTimeout(refreshAll, 1200);
        } else {
          addToast('Payment not completed.', 'info');
        }
        settle();
      });
    } catch (err: any) {
      addToast(getErrorMessage(err), 'error');
      setUpgrading(null);
    }
  };

  if (error && !passData)
    return (
      <div className="pt-6 adaptive-px max-w-2xl mx-auto">
        <ErrorState message={error} onAction={fetchPassData} />
      </div>
    );

  if (passLoading || !passData)
    return (
      <div className="pt-6 adaptive-px max-w-2xl mx-auto space-y-8">
        <div className="flex justify-between items-center">
          <Skeleton className="h-10 w-48 rounded-md" />
          <Skeleton className="h-10 w-16 rounded-md" />
        </div>
        <Skeleton className="h-3 w-full rounded-full" />
        <div className="grid grid-cols-3 gap-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-20 rounded-md" />
          ))}
        </div>
        <Skeleton className="h-60 w-full rounded-md" />
      </div>
    );

  const userLevel = Math.min(Number(passData.level || 0), Number(passData.max_level || 100));
  const maxLevel = Number(passData.max_level || 100);
  const claimedLevels = Array.isArray(passData.claimed_levels) ? passData.claimed_levels : [];
  const milestones = Array.isArray(passData.milestones)
    ? passData.milestones
    : [5, 10, 20, 25, 30, 40, 50, 60, 75, 80, 90, 100];
  const currentTier = passData.pass_type || 'free';
  const bank = bankSummary(passData.pass_bank);
  const nextTier = currentTier === 'free' ? 'premium' : currentTier === 'premium' ? 'elite' : null;
  const nextBenefits = nextTier ? passData.benefits?.[nextTier] : null;

  return (
    <div className="pt-6 max-w-2xl mx-auto adaptive-px space-y-8 select-none">
      <header className="space-y-6">
        <div className="flex items-center justify-between gap-6">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5">
              <TicketCheck size={20} className="text-brand-accent" />
              <h1 className="text-xl font-bold text-zinc-100 uppercase tracking-tight truncate max-w-[200px]">
                {passData.season_name || 'Season Pass'}
              </h1>
            </div>
            <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest opacity-60">
              Level up, unlock rewards
            </p>
          </div>
          <div className="px-4 py-2 bg-zinc-900 border border-white/5 rounded-md text-center">
            <p className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest mb-0.5">
              LVL
            </p>
            <p className="text-xl font-mono font-bold text-zinc-100 leading-none">{userLevel}</p>
          </div>
        </div>

        <ProgressBar current={userLevel} total={maxLevel} label="Season progress" compact />
      </header>

      {userLevel < maxLevel && (
        <Card
          variant="default"
          className="p-4 flex items-center justify-between gap-4"
        >
          <div className="flex items-center gap-4 min-w-0">
            <div className="w-10 h-10 rounded bg-brand-accent/10 border border-brand-accent/20 flex items-center justify-center shrink-0">
              <TrendingUp size={18} className="text-brand-accent" />
            </div>
            <div className="min-w-0">
              <h2 className="text-[10px] font-bold text-zinc-100 uppercase tracking-widest mb-0.5">
                BUY LEVEL
              </h2>
              <p className="text-[9px] font-mono font-bold text-zinc-500 uppercase">
                {formatNumber(passData.level_buy_cost || 0)} COINS / LVL
              </p>
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="h-9 px-4 shrink-0"
            isLoading={buyingLevels}
            onClick={handleBuyLevel}
          >
            +1 LVL
          </Button>
        </Card>
      )}

      <section className="grid grid-cols-3 gap-3">
        {TIER_ORDER.map((tier) => {
          const Icon = TIER_ICON[tier as keyof typeof TIER_ICON];
          const active = currentTier === tier;
          const unlocked = TIER_ORDER.indexOf(currentTier) >= TIER_ORDER.indexOf(tier);
          return (
            <Card
              key={tier}
              variant="default"
              className={cn(
                'p-3.5 flex flex-col items-center justify-center text-center gap-2 transition-all',
                active
                  ? 'border-brand-accent/30 bg-brand-accent/5'
                  : unlocked
                    ? 'border-emerald-500/10'
                    : 'opacity-30',
              )}
            >
              <Icon
                size={16}
                className={
                  active ? 'text-brand-accent' : unlocked ? 'text-emerald-500' : 'text-zinc-700'
                }
              />
              <div className="space-y-1">
                <p className="text-[9px] font-bold text-zinc-100 uppercase tracking-widest leading-none">
                  {tier}
                </p>
                {!unlocked && (
                  <p className="text-[8px] font-mono font-bold text-zinc-600">
                    {passData.prices?.[tier] || 0} ★
                  </p>
                )}
              </div>
            </Card>
          );
        })}
      </section>

      {nextTier && (
        <Card variant="surface" className="p-6 space-y-6">
          <div className="flex items-start justify-between gap-6">
            <div className="space-y-1.5">
              <h2 className="text-lg font-bold text-zinc-100 uppercase tracking-tight">
                {nextTier.toUpperCase()} UPGRADE
              </h2>
              <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest leading-relaxed max-w-[220px]">
                {passData.tiers?.[nextTier]?.summary || 'Better hunt yields, more egg drops, faster incubation.'}
              </p>
            </div>
            <div className="text-right">
              <span className="text-xl font-mono font-bold text-zinc-100">
                {passData.upgrade_prices?.[nextTier]}
              </span>
              <span className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest block">
                STARS
              </span>
            </div>
          </div>

          {nextBenefits && (
            <div className="grid grid-cols-2 gap-3">
              {[
                {
                  label: 'Hunt Coins',
                  value: percentBonus(nextBenefits.hunt_multiplier),
                  color: 'text-amber-500',
                },
                {
                  label: 'Egg Drops',
                  value: percentBonus(nextBenefits.egg_drop_multiplier),
                  color: 'text-brand-accent',
                },
                {
                  label: 'Sync Speed',
                  value: percentBonus(nextBenefits.incubation_multiplier, true),
                  color: 'text-emerald-500',
                },
                {
                  label: 'Active Slots',
                  value: `${nextBenefits.incubation_slots}`,
                  color: 'text-purple-500',
                },
              ].map((benefit, i) => (
                <div key={i} className="bg-zinc-950 p-3 rounded border border-white/5">
                  <p className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest mb-1">
                    {benefit.label}
                  </p>
                  <p className={cn('text-[11px] font-mono font-bold uppercase', benefit.color)}>
                    {benefit.value}
                  </p>
                </div>
              ))}
            </div>
          )}

          <Button
            onClick={() => handleUpgrade(nextTier)}
            isLoading={upgrading === nextTier}
            variant="accent"
            className="w-full h-12"
          >
            Activate Clearance
          </Button>
        </Card>
      )}

      {currentTier !== 'free' && bank.hasValue && (
        <Card
          variant="default"
          className="p-4 border-amber-500/20 bg-amber-500/5 flex items-center justify-between gap-6"
        >
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded bg-amber-500/10 flex items-center justify-center text-amber-500 border border-amber-500/20">
              <Gift size={20} />
            </div>
            <div>
              <h2 className="text-[10px] font-bold text-amber-500 uppercase tracking-widest mb-0.5">
                REWARD VAULT
              </h2>
              <p className="text-[11px] font-mono font-bold text-zinc-100 uppercase">
                {formatNumber(bank.shards)} Coins {bank.eggs ? `+ ${bank.eggs} Eggs` : ''}
              </p>
            </div>
          </div>
          <Button
            variant="accent"
            size="sm"
            onClick={handleClaimBank}
            isLoading={claimingBank}
            className="bg-amber-500 hover:bg-amber-400 h-9 px-6 text-black border-none"
          >
            Claim
          </Button>
        </Card>
      )}

      <section className="space-y-4">
        <div className="flex items-center justify-between px-1">
          <h2 className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest">
            Pipeline Log
          </h2>
          <Badge variant="secondary" size="xs">
            {claimedLevels.length} / {maxLevel} CLAIMED
          </Badge>
        </div>

        <div className="space-y-4">
          <AnimatePresence mode="popLayout">
            {milestones.map((lvl: number) => {
              const track = passData.tracks?.[lvl];
              if (!track) return null;
              const isReached = userLevel >= lvl;
              const isClaimed = claimedLevels.includes(lvl);

              return (
                <m.div
                  layout
                  key={lvl}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                >
                  <Card
                    variant="default"
                    className={cn('p-4 space-y-4 transition-all', !isReached && 'opacity-30')}
                  >
                    <div className="flex items-center justify-between gap-6">
                      <div className="flex items-center gap-3">
                        <div
                          className={cn(
                            'w-10 h-10 rounded flex flex-col items-center justify-center border font-mono font-bold transition-all',
                            isReached
                              ? 'border-brand-accent/30 text-brand-accent bg-brand-accent/5'
                              : 'border-white/5 text-zinc-800 bg-zinc-950',
                          )}
                        >
                          <span className="text-[7px] opacity-40 leading-none">LVL</span>
                          <span className="text-lg leading-none">{lvl}</span>
                        </div>
                        <div>
                          <p className="text-xs font-bold text-zinc-100 uppercase tracking-tight mb-1">
                            Level {lvl}
                          </p>
                          <div className="flex items-center gap-2">
                            {isClaimed ? (
                              <Badge variant="success" size="xs">
                                Claimed
                              </Badge>
                            ) : isReached ? (
                              <Badge variant="primary" size="xs">
                                Available
                              </Badge>
                            ) : (
                              <Badge variant="secondary" size="xs">
                                Locked
                              </Badge>
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="shrink-0">
                        {isClaimed ? (
                          <div className="w-8 h-8 rounded bg-emerald-500/10 flex items-center justify-center text-emerald-500">
                            <Target size={16} />
                          </div>
                        ) : isReached ? (
                          <Button
                            onClick={() => handleClaim(lvl)}
                            isLoading={claiming === lvl}
                            variant="outline"
                            size="sm"
                            className="h-9 px-4"
                          >
                            Claim
                          </Button>
                        ) : (
                          <Lock size={16} className="text-zinc-800" />
                        )}
                      </div>
                    </div>

                    <div className="space-y-2">
                      {TIER_ORDER.map((tier) => {
                        const unlocked =
                          TIER_ORDER.indexOf(currentTier) >= TIER_ORDER.indexOf(tier);
                        const Icon = TIER_ICON[tier as keyof typeof TIER_ICON];
                        return (
                          <div
                            key={tier}
                            className={cn(
                              'flex items-center justify-between px-3 py-2 rounded border transition-colors',
                              unlocked
                                ? 'bg-zinc-900 border-white/5'
                                : 'bg-zinc-950 border-transparent opacity-20',
                            )}
                          >
                            <div className="flex items-center gap-2.5">
                              <Icon
                                size={12}
                                className={
                                  unlocked
                                    ? tier === 'elite'
                                      ? 'text-purple-500'
                                      : tier === 'premium'
                                        ? 'text-brand-accent'
                                        : 'text-zinc-500'
                                    : 'text-zinc-800'
                                }
                              />
                              <span className="text-[8px] font-bold text-zinc-500 uppercase tracking-widest">
                                {tier}
                              </span>
                            </div>
                            <span
                              className={cn(
                                'text-[10px] font-mono font-bold uppercase truncate ml-4',
                                unlocked ? 'text-zinc-200' : 'text-zinc-800',
                              )}
                            >
                              {formatReward(track, tier)}
                            </span>
                          </div>
                        );
                      })}
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
