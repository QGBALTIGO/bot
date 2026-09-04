import { AlertCircle, BadgePercent, Coins, Gem, RefreshCw, Repeat2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import { apiFetch, getErrorMessage, invalidateQueries } from '../api/client';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { ErrorState } from '../components/ui/ErrorState';
import { Input } from '../components/ui/Input';
import { Skeleton } from '../components/ui/Skeleton';
import { useToast } from '../components/ui/Toast';
import { useUser } from '../context/UserContext';
import { useApi } from '../hooks/useApi';
import { cn, formatNumber } from '../utils';

type ExchangeMode = 'shards_to_zenith' | 'zenith_to_shards';

interface ExchangeData {
  balance: number;
  zenith: number;
  rate: number;
  minimum_shards: number;
  minimum_zenith: number;
}

const getModeCopy = (mode: ExchangeMode) => {
  if (mode === 'shards_to_zenith') {
    return {
      inputLabel: 'COINS',
      outputLabel: 'PRISMS',
    };
  }

  return {
    inputLabel: 'PRISMS',
    outputLabel: 'COINS',
  };
};

const toPositiveNumber = (value: unknown, fallback: number) => {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) && numberValue > 0 ? numberValue : fallback;
};

export const Exchange = () => {
  const { user, refreshUser } = useUser();
  const { addToast } = useToast();
  const { data, loading, error, execute: fetchExchange } = useApi<ExchangeData>('/shop/exchange');
  const [mode, setMode] = useState<ExchangeMode>('shards_to_zenith');
  const [amount, setAmount] = useState('10000');
  const [exchanging, setExchanging] = useState(false);

  const shardBalance = Math.max(0, Math.floor(Number(data?.balance ?? user?.balance ?? 0) || 0));
  const zenithBalance = Math.max(
    0,
    Math.floor(Number(data?.zenith ?? user?.stats?.zenith ?? user?.zenith ?? 0) || 0),
  );
  const rate = Math.floor(toPositiveNumber(data?.rate, 10000));
  const minimumShards = Math.floor(toPositiveNumber(data?.minimum_shards, rate));
  const minimumZenith = Math.floor(toPositiveNumber(data?.minimum_zenith, 1));
  const rawAmount = amount.trim();
  const parsedAmount = Number(rawAmount);
  const hasValidAmount =
    rawAmount.length > 0 &&
    Number.isFinite(parsedAmount) &&
    parsedAmount > 0 &&
    Number.isInteger(parsedAmount);
  const amountNumber = hasValidAmount ? parsedAmount : 0;
  const copy = getModeCopy(mode);
  const isShardMode = mode === 'shards_to_zenith';
  const outputAmount = isShardMode ? Math.floor(amountNumber / rate) : amountNumber * rate;
  const minimumInputAmount = isShardMode ? minimumShards : minimumZenith;
  const maxInputAmount = isShardMode ? Math.floor(shardBalance / rate) * rate : zenithBalance;
  const canUseMax = maxInputAmount >= minimumInputAmount;

  const validationMessage = useMemo(() => {
    if (!rawAmount) return 'Enter amount';
    if (!hasValidAmount) return 'Positive integers only';

    if (isShardMode) {
      if (amountNumber < minimumShards) return `Min: ${formatNumber(minimumShards)} Coins`;
      if (amountNumber % rate !== 0) return `Use ${formatNumber(rate)} increments`;
      if (shardBalance < amountNumber) return 'Insufficient Coins';
      return null;
    }

    if (amountNumber < minimumZenith) return `Min: ${formatNumber(minimumZenith)} Prisms`;
    if (zenithBalance < amountNumber) return 'Insufficient Prisms';
    return null;
  }, [
    amountNumber,
    hasValidAmount,
    isShardMode,
    minimumShards,
    minimumZenith,
    rate,
    rawAmount,
    shardBalance,
    zenithBalance,
  ]);

  const canExchange = !validationMessage && outputAmount > 0;
  const presetOptions = useMemo(() => {
    const baseOptions = isShardMode
      ? [
          { label: '1 Prism', amount: rate },
          { label: '5 Prisms', amount: rate * 5 },
          { label: '10 Prisms', amount: rate * 10 },
        ]
      : [
          { label: '1 Prism', amount: 1 },
          { label: '5 Prisms', amount: 5 },
          { label: '10 Prisms', amount: 10 },
        ];
    const options = [...baseOptions, { label: 'Max', amount: maxInputAmount }];
    const seen = new Set<number>();

    return options
      .map((option) => ({ ...option, amount: Math.floor(option.amount) }))
      .filter((option) => {
        if (!Number.isFinite(option.amount) || option.amount <= 0 || seen.has(option.amount))
          return false;
        seen.add(option.amount);
        return true;
      });
  }, [isShardMode, maxInputAmount, rate]);

  const handleRefresh = async () => {
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    await Promise.allSettled([fetchExchange(), refreshUser()]);
  };

  const handleSwapMode = () => {
    const nextMode = isShardMode ? 'zenith_to_shards' : 'shards_to_zenith';
    setMode(nextMode);
    setAmount(nextMode === 'shards_to_zenith' ? String(rate) : String(minimumZenith));
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
  };

  const handleExchange = async () => {
    if (!canExchange || exchanging) return;

    setExchanging(true);
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    try {
      const result = await apiFetch(`/shop/exchange/${mode}?amount=${amountNumber}`, {
        method: 'POST',
      });
      addToast(result.message || 'Exchange successful.', 'success');
      await Promise.allSettled([fetchExchange(), refreshUser()]);
      invalidateQueries(['/shop/characters', '/shop/hub']);
    } catch (err: any) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setExchanging(false);
    }
  };

  if (loading && !data)
    return (
      <div className="pt-6 adaptive-px max-w-2xl mx-auto space-y-8">
        <div className="flex flex-col gap-1.5">
          <Skeleton className="h-8 w-40 rounded-md" />
          <Skeleton className="h-4 w-56 rounded-md opacity-50" />
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-16 rounded-md" />
          ))}
        </div>
        <Skeleton className="h-80 w-full rounded-md" />
      </div>
    );

  if (error && !data)
    return (
      <div className="pt-6 max-w-2xl mx-auto adaptive-px">
        <ErrorState message={error} onAction={handleRefresh} />
      </div>
    );

  return (
    <div className="pt-6 max-w-2xl mx-auto adaptive-px space-y-8">
      <header className="space-y-6">
        <div className="flex items-start justify-between gap-6">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5">
              <Repeat2 size={20} className="text-brand-accent" />
              <h1 className="text-xl font-bold text-zinc-100 uppercase tracking-tight">Currency</h1>
            </div>
            <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest opacity-60">
              Currency exchange
            </p>
          </div>

          <Button
            variant="secondary"
            size="sm"
            onClick={handleRefresh}
            isLoading={loading}
            className="w-9 h-9 p-0"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </Button>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {[
            { icon: Coins, label: 'Coins', value: formatNumber(shardBalance), variant: 'default' },
            { icon: Gem, label: 'Prisms', value: formatNumber(zenithBalance), variant: 'primary' },
            {
              icon: BadgePercent,
              label: 'Rate',
              value: `${formatNumber(rate)}:1`,
              variant: 'success',
            },
          ].map((metric, i) => (
            <Card key={i} variant="default" className="p-3.5">
              <div className="flex items-center gap-2 mb-2">
                <metric.icon
                  size={11}
                  className={cn(
                    metric.variant === 'primary'
                      ? 'text-brand-accent'
                      : metric.variant === 'success'
                        ? 'text-emerald-500'
                        : 'text-zinc-600',
                  )}
                />
                <span className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest">
                  {metric.label}
                </span>
              </div>
              <p className="text-sm font-mono font-bold text-zinc-100 tabular-nums">
                {metric.value}
              </p>
            </Card>
          ))}
        </div>
      </header>

      <section className="space-y-6">
        <Card variant="surface" className="p-6 sm:p-8 space-y-8">
          <div className="flex items-center justify-between gap-4 p-1 bg-zinc-950 rounded-md border border-white/5">
            {[
              { id: 'shards_to_zenith', label: 'Coins → Prisms' },
              { id: 'zenith_to_shards', label: 'Prisms → Coins' },
            ].map((m) => (
              <button
                key={m.id}
                onClick={() => {
                  setMode(m.id as ExchangeMode);
                  setAmount(m.id === 'shards_to_zenith' ? String(rate) : String(minimumZenith));
                  window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
                }}
                className={cn(
                  'flex-1 h-9 rounded text-[10px] font-bold uppercase tracking-widest transition-all',
                  mode === m.id ? 'bg-zinc-100 text-zinc-950' : 'text-zinc-500 hover:text-zinc-300',
                )}
              >
                {m.label}
              </button>
            ))}
          </div>

          <div className="flex flex-col sm:flex-row items-center gap-6">
            <div className="flex-1 w-full space-y-2">
              <p className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest">
                {copy.inputLabel}
              </p>
              <div className="h-16 flex items-center px-4 bg-zinc-950 border border-white/5 rounded-md font-mono text-xl font-bold text-zinc-100">
                {formatNumber(amountNumber)}
              </div>
            </div>

            <button
              type="button"
              aria-label="Swap exchange direction"
              onClick={handleSwapMode}
              className="w-10 h-10 rounded-full border border-white/10 flex items-center justify-center text-zinc-500 hover:text-zinc-100 hover:border-white/20 transition-all active:scale-90"
            >
              <Repeat2 size={18} />
            </button>

            <div className="flex-1 w-full space-y-2">
              <p className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest">
                {copy.outputLabel}
              </p>
              <div className="h-16 flex items-center px-4 bg-zinc-900 border border-brand-accent/20 rounded-md font-mono text-xl font-bold text-brand-accent">
                {formatNumber(outputAmount)}
              </div>
            </div>
          </div>

          <div className="space-y-4">
            <div className="flex justify-between items-end px-1">
              <label className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest">
                Amount
              </label>
              <button
                onClick={() => {
                  setAmount(String(maxInputAmount));
                  window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
                }}
                disabled={!canUseMax}
                className="text-[9px] font-bold text-brand-accent uppercase tracking-widest disabled:opacity-20"
              >
                Use Max
              </button>
            </div>
            <Input
              type="text"
              value={amount}
              onChange={(e) => setAmount(e.target.value.replace(/\D/g, ''))}
              className="h-12 font-mono text-base"
              inputMode="numeric"
              placeholder="0"
            />
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {presetOptions.map(({ label, amount: pAmount }) => {
              const isDisabled =
                pAmount < minimumInputAmount ||
                (label === 'Max' ? !canUseMax : pAmount > maxInputAmount);
              const isActive = pAmount === amountNumber;

              return (
                <button
                  key={pAmount}
                  onClick={() => {
                    setAmount(String(pAmount));
                    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
                  }}
                  disabled={isDisabled}
                  className={cn(
                    'h-12 px-3 rounded border text-left transition-all disabled:opacity-20',
                    isActive
                      ? 'border-brand-accent bg-brand-accent/5'
                      : 'border-white/5 hover:border-white/20 bg-zinc-950',
                  )}
                >
                  <span
                    className={cn(
                      'block text-[8px] font-bold uppercase mb-0.5',
                      isActive ? 'text-brand-accent' : 'text-zinc-600',
                    )}
                  >
                    {label}
                  </span>
                  <span className="block truncate text-[11px] font-mono font-bold text-zinc-100">
                    {formatNumber(pAmount)}
                  </span>
                </button>
              );
            })}
          </div>

          <div className="pt-4 border-t border-white/5 space-y-4">
            <Button
              onClick={handleExchange}
              disabled={!canExchange || exchanging}
              variant="accent"
              className="w-full h-14"
              isLoading={exchanging}
              leftIcon={<Repeat2 size={16} />}
            >
              Authorize Exchange
            </Button>

            <div
              className={cn(
                'flex items-center gap-3 px-4 py-3 rounded-md border text-[10px] font-bold uppercase tracking-widest transition-colors',
                validationMessage
                  ? 'border-amber-500/20 bg-amber-500/5 text-amber-500'
                  : 'border-emerald-500/20 bg-emerald-500/5 text-emerald-500',
              )}
            >
              <AlertCircle size={14} className="shrink-0" />
              <span>{validationMessage || 'Transaction ready for processing'}</span>
            </div>
          </div>
        </Card>
      </section>
    </div>
  );
};
