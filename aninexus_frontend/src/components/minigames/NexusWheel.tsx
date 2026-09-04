import { m } from 'framer-motion';
import { CircleDashed } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Button } from '../ui/Button';
import { cn, haptics } from '../../utils';
import type { SessionData } from './types';

const WHEEL_PRIZES = [
  { label: '+3 XP', color: 'zinc' },
  { label: '+5 XP', color: 'zinc' },
  { label: '+1 Coin', color: 'brand' },
  { label: 'Personagem', color: 'epic' },
  { label: '+8 XP', color: 'zinc' },
  { label: '+1 Coin', color: 'rare' },
  { label: '+5 XP', color: 'zinc' },
  { label: '+15 XP', color: 'brand' },
];

export const NexusWheel = ({
  session,
  onComplete,
  _onCancel,
}: {
  session: SessionData;
  onComplete: (score: number) => void;
  _onCancel: () => void;
}) => {
  const [isSpinning, setIsSpinning] = useState(false);
  const [rotation, setRotation] = useState(0);
  const timersRef = useRef<number[]>([]);

  useEffect(() => {
    return () => {
      for (const timer of timersRef.current) window.clearTimeout(timer);
    };
  }, []);

  const spin = () => {
    if (isSpinning || session.prize_index === undefined) return;
    setIsSpinning(true);
    haptics.heavy();

    const sectorSize = 360 / WHEEL_PRIZES.length;
    const targetSector = session.prize_index;
    const extraRounds = 8;
    const finalRotation = extraRounds * 360 - (targetSector * sectorSize + sectorSize / 2);
    setRotation(finalRotation);

    const tickInterval = window.setInterval(() => haptics.light(), 150);
    timersRef.current.push(
      window.setTimeout(() => window.clearInterval(tickInterval), 3500),
      window.setTimeout(() => {
        setIsSpinning(false);
        haptics.notification('success');
        timersRef.current.push(window.setTimeout(() => onComplete(0), 1000));
      }, 4500),
    );
  };

  return (
    <div className="flex flex-col items-center py-4 space-y-12">
      <div className="w-full flex items-center justify-between px-6">
        <div className="space-y-1">
          <span className="block text-[7px] font-bold text-zinc-500 uppercase tracking-[0.2em]">
            Roleta AniNexus
          </span>
          <div className="flex items-center gap-2">
            <div className="w-1.5 h-1.5 rounded-full bg-brand-accent animate-pulse" />
            <span className="text-xs font-mono font-bold text-zinc-300">PRONTA</span>
          </div>
        </div>
        <div className="text-right space-y-1">
          <span className="block text-[7px] font-bold text-zinc-500 uppercase tracking-[0.2em]">
            Setores
          </span>
          <span className="text-xs font-mono font-bold text-brand-accent">08</span>
        </div>
      </div>

      <div className="relative w-72 h-72">
        <div className="absolute -inset-4 rounded-full border border-white/[0.02] flex items-center justify-center">
          <div className="absolute inset-0 rounded-full border border-dashed border-white/[0.05] animate-[spin_60s_linear_infinite]" />
        </div>

        <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 z-30">
          <div className="flex flex-col items-center">
            <div className="w-0.5 h-4 bg-brand-accent shadow-[0_0_10px_rgba(59,130,246,0.5)]" />
            <div className="w-0 h-0 border-l-[8px] border-l-transparent border-r-[8px] border-r-transparent border-t-[12px] border-t-brand-accent" />
          </div>
        </div>

        <div className="absolute inset-0 rounded-full border-[6px] border-zinc-900 shadow-[0_0_50px_rgba(0,0,0,0.8)] z-20 pointer-events-none" />

        <m.div
          animate={{ rotate: rotation }}
          transition={{ duration: 4.5, ease: [0.15, 0, 0.15, 1] }}
          className="w-full h-full rounded-full bg-zinc-950 overflow-hidden border border-white/10 relative z-10"
        >
          {WHEEL_PRIZES.map((prize, index) => (
            <div
              key={`${prize.label}-${index}`}
              className="absolute top-0 left-1/2 w-px h-1/2 bg-white/[0.03] origin-bottom"
              style={{ transform: `rotate(${index * (360 / WHEEL_PRIZES.length)}deg)` }}
            >
              <div
                className="absolute top-10 left-0 -translate-x-1/2 flex flex-col items-center gap-2"
                style={{ transform: `rotate(${180 / WHEEL_PRIZES.length}deg)` }}
              >
                <div
                  className={cn(
                    'w-1 h-1 rounded-full',
                    prize.color === 'brand'
                      ? 'bg-brand-accent'
                      : prize.color === 'epic'
                        ? 'bg-purple-500'
                        : prize.color === 'rare'
                          ? 'bg-cyan-500'
                          : 'bg-zinc-800',
                  )}
                />
                <span
                  className={cn(
                    'text-[8px] font-bold uppercase tracking-[0.15em] [writing-mode:vertical-lr] rotate-180',
                    prize.color === 'brand'
                      ? 'text-brand-accent'
                      : prize.color === 'epic'
                        ? 'text-purple-400'
                        : prize.color === 'rare'
                          ? 'text-cyan-400'
                          : 'text-zinc-500',
                  )}
                >
                  {prize.label}
                </span>
              </div>
            </div>
          ))}
        </m.div>

        <div className="absolute inset-0 m-auto w-16 h-16 rounded-full bg-zinc-950 border border-white/10 flex items-center justify-center z-30 shadow-2xl">
          <div className="absolute inset-0 rounded-full border border-white/5 animate-pulse" />
          <CircleDashed
            size={24}
            className={cn(
              'text-zinc-700 transition-all duration-1000',
              isSpinning ? 'animate-spin text-brand-accent' : '',
            )}
          />
        </div>
      </div>

      <div className="flex flex-col items-center gap-4 w-full px-8 pt-4">
        <div className="w-full flex justify-between text-[8px] font-bold text-zinc-600 uppercase tracking-widest mb-2">
          <span>Custo</span>
          <span className="text-zinc-400">1 energia</span>
        </div>
        <Button
          onClick={spin}
          disabled={isSpinning}
          className="w-full h-14 bg-zinc-100 text-zinc-950 font-bold uppercase tracking-[0.2em] text-[10px] rounded-xl relative overflow-hidden group shadow-[0_0_20px_rgba(255,255,255,0.1)]"
        >
          <span className="relative z-10">{isSpinning ? 'Girando...' : 'Girar a roleta'}</span>
          {!isSpinning && (
            <m.div
              initial={{ x: '-100%' }}
              animate={{ x: '100%' }}
              transition={{ repeat: Infinity, duration: 1.5, ease: 'linear' }}
              className="absolute inset-0 bg-gradient-to-r from-transparent via-black/[0.05] to-transparent"
            />
          )}
        </Button>
        <p className="text-[7px] text-zinc-600 font-bold uppercase tracking-widest">
          A recompensa é definida no servidor antes do giro
        </p>
      </div>
    </div>
  );
};
