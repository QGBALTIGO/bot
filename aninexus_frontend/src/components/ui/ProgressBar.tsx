import 'react';
import { m } from 'framer-motion';
import { cn, formatNumber } from '../../utils';

interface ProgressBarProps {
  current: number;
  total: number;
  label?: string;
  compact?: boolean;
  showValue?: boolean;
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'premium' | 'epic';
}

export const ProgressBar = ({
  current,
  total,
  label,
  compact,
  showValue = true,
  variant = 'default',
}: ProgressBarProps) => {
  const percentage = total > 0 ? Math.min(100, Math.max(0, (current / total) * 100)) : 0;

  const variants = {
    default: 'bg-brand-accent',
    success: 'bg-emerald-500',
    warning: 'bg-amber-500',
    danger: 'bg-red-500',
    premium: 'bg-amber-400',
    epic: 'bg-purple-500',
  };

  return (
    <div className={`w-full ${compact ? 'space-y-1' : 'space-y-2'}`}>
      {(label || showValue) && (
        <div className="flex justify-between items-end px-0.5">
          {label && (
            <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest leading-none">
              {label}
            </span>
          )}
          {showValue && (
            <span className="text-[10px] font-mono font-medium text-zinc-400 tabular-nums leading-none">
              {formatNumber(current)}
              <span className="mx-0.5 opacity-30">/</span>
              {formatNumber(total)}
            </span>
          )}
        </div>
      )}
      <div
        className={cn(
          'w-full bg-zinc-900 rounded-full overflow-hidden border border-white/[0.04] p-[1.5px]',
          compact ? 'h-1.5' : 'h-2.5',
        )}
      >
        <m.div
          initial={{ width: 0 }}
          animate={{ width: `${percentage}%` }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
          className={cn('h-full rounded-full relative overflow-hidden', variants[variant])}
        >
          <div className="absolute inset-0 bg-gradient-to-b from-white/10 to-transparent" />
        </m.div>
      </div>
    </div>
  );
};
