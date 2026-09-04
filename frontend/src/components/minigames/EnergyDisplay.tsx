import { m } from 'framer-motion';
import { Timer, Zap } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Card } from '../ui/Card';

export const ENERGY_RECHARGE_MS = 20 * 60 * 1000; // 20 mins per energy unit

export const EnergyDisplay = ({
  energy,
  maxEnergy,
  lastRecharge,
  onRecharge,
}: {
  energy: number;
  maxEnergy: number;
  lastRecharge: string | null;
  onRecharge?: () => void;
}) => {
  const [timeLeft, setTimeLeft] = useState<string | null>(null);

  useEffect(() => {
    if (energy >= maxEnergy || !lastRecharge) {
      setTimeLeft(null);
      return;
    }

    const interval = setInterval(() => {
      const last = new Date(lastRecharge).getTime();
      const diff = last + ENERGY_RECHARGE_MS - Date.now();

      if (diff <= 0) {
        setTimeLeft('00:00');
        clearInterval(interval);
        // Energy should have refilled server-side; resync state.
        onRecharge?.();
        return;
      }

      const mins = Math.floor(diff / 60000);
      const secs = Math.floor((diff % 60000) / 1000);
      setTimeLeft(`${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`);
    }, 1000);

    return () => clearInterval(interval);
  }, [energy, maxEnergy, lastRecharge, onRecharge]);

  return (
    <Card className="p-4 bg-zinc-900/50 border-white/[0.04] mb-6 overflow-hidden relative">
      <div className="flex items-center justify-between relative z-10">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-brand-accent/10 flex items-center justify-center border border-brand-accent/20">
            <Zap size={20} className="text-brand-accent" fill="currentColor" />
          </div>
          <div>
            <h4 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-0.5">
              Energy
            </h4>
            <div className="flex items-end gap-1.5">
              <span className="text-xl font-mono font-bold text-zinc-100">{energy}</span>
              <span className="text-xs font-mono text-zinc-600 mb-1">/ {maxEnergy}</span>
            </div>
          </div>
        </div>
        {timeLeft && (
          <div className="text-right">
            <h4 className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest mb-1">
              Refills in
            </h4>
            <div className="flex items-center gap-1.5 text-zinc-400 font-mono text-sm">
              <Timer size={12} className="text-zinc-600" />
              {timeLeft}
            </div>
          </div>
        )}
      </div>

      {/* Visual Energy Bar */}
      <div className="absolute bottom-0 left-0 h-0.5 bg-zinc-800 w-full">
        <m.div
          initial={{ width: 0 }}
          animate={{ width: `${maxEnergy > 0 ? (energy / maxEnergy) * 100 : 0}%` }}
          className="h-full bg-brand-accent shadow-[0_0_10px_rgba(var(--brand-accent-rgb),0.5)]"
        />
      </div>
    </Card>
  );
};
