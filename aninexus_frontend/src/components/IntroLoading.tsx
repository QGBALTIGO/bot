import { Fingerprint, Terminal } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { cn } from '../utils';

export type IntroStatus = 'loading' | 'ready' | 'error';

// Steps map to the real boot phases: secure_init → token verify → /me fetch.
const LOADING_STEPS = ['INICIANDO', 'VERIFICANDO TELEGRAM', 'CARREGANDO PERFIL'];

// Minimum time the intro stays visible so it never flashes on fast networks.
const MIN_DISPLAY_MS = 900;

interface IntroLoadingProps {
  status: IntroStatus;
  onFinish: () => void;
}

export const IntroLoading = ({ status, onFinish }: IntroLoadingProps) => {
  const [progress, setProgress] = useState(0);
  const [fading, setFading] = useState(false);
  const startedAt = useRef(Date.now());
  const finishedRef = useRef(false);
  const onFinishRef = useRef(onFinish);
  onFinishRef.current = onFinish;

  // Ease progress toward its target: 90% while booting, 100% once resolved.
  useEffect(() => {
    const timer = setInterval(() => {
      setProgress((prev) => {
        const target = status === 'loading' ? 90 : 100;
        if (prev >= target) return prev;
        const rate = status === 'loading' ? 0.09 : 0.3;
        return Math.min(target, prev + Math.max(0.6, (target - prev) * rate));
      });
    }, 90);
    return () => clearInterval(timer);
  }, [status]);

  // Once complete: haptic tick, hold the end state briefly, fade out, unmount.
  useEffect(() => {
    if (status === 'loading' || progress < 100 || finishedRef.current) return;
    finishedRef.current = true;

    if (status === 'ready') {
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success');
    }

    const hold = Math.max(0, MIN_DISPLAY_MS - (Date.now() - startedAt.current)) + 400;
    const t1 = setTimeout(() => setFading(true), hold);
    const t2 = setTimeout(() => onFinishRef.current(), hold + 300);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [progress, status]);

  const failed = status === 'error';

  const currentStep = useMemo(() => {
    if (failed) return 'FALHA NA CONEXÃO';
    if (progress >= 100) return 'PRONTO';
    const index = Math.min(
      LOADING_STEPS.length - 1,
      Math.floor((progress / 90) * LOADING_STEPS.length),
    );
    return LOADING_STEPS[index];
  }, [progress, failed]);

  return (
    <div
      className={cn(
        'fixed inset-0 z-[999] flex flex-col items-center justify-center bg-zinc-950 px-8 select-none transition-opacity duration-300',
        fading ? 'opacity-0' : 'opacity-100',
      )}
    >      <div className="w-full max-w-xs space-y-16 relative z-10">
        {/* Visual Brand - Creative Minimalist Animation */}
        <div className="relative flex flex-col items-center justify-center gap-8">
          <div className="relative w-24 h-24 flex items-center justify-center">
            {/* Outer Ring */}
            <div className="absolute inset-0 rounded-full border border-dashed border-brand-accent/20 animate-[spin_4s_linear_infinite]" />

            {/* Middle Ring */}
            <div className="absolute inset-2 rounded-full border border-white/5 animate-[spin_8s_linear_infinite_reverse]" />

            {/* Core Brand Symbol */}
            <div
              className={cn(
                'relative w-12 h-12 rounded-lg border flex items-center justify-center shadow-[0_0_20px_rgba(255,255,255,0.02)] animate-[intro-pulse_2s_ease-in-out_infinite] transition-colors duration-500',
                failed ? 'bg-red-950/50 border-red-500/30' : 'bg-zinc-900 border-white/10',
              )}
            >
              <span
                className={cn(
                  'text-xl font-black tracking-tighter transition-colors duration-500',
                  failed ? 'text-red-400' : 'text-white',
                )}
              >
                A
              </span>
              <div
                className={cn(
                  'absolute inset-0 rounded-lg animate-[intro-pulse_2s_ease-in-out_infinite]',
                  failed ? 'bg-red-500/5' : 'bg-brand-accent/5',
                )}
              />
            </div>

            {/* Orbiting particles */}
            {[0, 120, 240].map((angle, i) => (
              <div
                key={i}
                className="absolute inset-0"
                style={{
                  transform: `rotate(${angle}deg)`,
                  animation: `spin ${3 + i}s linear infinite`,
                }}
              >
                <div
                  className="w-1 h-1 bg-brand-accent rounded-full absolute"
                  style={{
                    top: '0',
                    left: '50%',
                    transform: 'translate(-50%, -50%)',
                    opacity: progress > i * 30 ? 1 : 0.1,
                  }}
                />
              </div>
            ))}
          </div>

          <div className="flex flex-col items-center gap-1">
            <span className="text-2xl font-black text-white tracking-[0.2em] uppercase">ANINEXUS</span>
            <span className="text-[9px] font-bold text-zinc-600 tracking-[0.4em] uppercase">
              Colecionador de personagens
            </span>
          </div>
        </div>

        {/* Progress & Stats */}
        <div className="space-y-6">
          <div className="space-y-3" role="status" aria-live="polite">
            <div className="flex justify-between items-end px-1">
              <div
                key={currentStep}
                className="flex items-center gap-2 animate-[intro-step_0.3s_ease-out]"
              >
                <Terminal size={11} className={failed ? 'text-red-500' : 'text-brand-accent'} />
                <span
                  className={cn(
                    'text-[10px] font-bold tracking-widest uppercase',
                    failed ? 'text-red-400' : 'text-zinc-100',
                  )}
                >
                  {currentStep}
                </span>
              </div>
              <span className="text-[11px] font-mono text-zinc-500 font-bold tabular-nums">
                {Math.round(progress)}%
              </span>
            </div>

            <div className="h-1 w-full bg-zinc-900 rounded-full overflow-hidden">
              <div
                className={cn(
                  'relative h-full rounded-full transition-[width] duration-200 ease-out',
                  failed
                    ? 'bg-red-500'
                    : 'bg-gradient-to-r from-brand-accent/60 to-brand-accent',
                )}
                style={{ width: `${progress}%` }}
              >
                {!failed && progress < 100 && (
                  <div className="absolute inset-0 overflow-hidden rounded-full">
                    <div className="absolute inset-y-0 w-1/2 bg-gradient-to-r from-transparent via-white/25 to-transparent animate-shimmer" />
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between px-1">
            <div className="flex items-center gap-1.5">
              <Fingerprint size={9} className="text-zinc-600" />
              <span className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest">
                Conectado via Telegram
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <div
                className={cn(
                  'w-1.5 h-1.5 rounded-full transition-colors duration-500',
                  failed
                    ? 'bg-red-500'
                    : progress >= 100
                      ? 'bg-emerald-500'
                      : 'bg-zinc-800 animate-pulse',
                )}
              />
              <span
                className={cn(
                  'text-[8px] font-mono uppercase tracking-widest',
                  failed ? 'text-red-400' : 'text-zinc-600',
                )}
              >
                {failed ? 'FALHA' : progress >= 100 ? 'PRONTO' : 'SINCRONIZANDO'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Decorative Background Elements */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none opacity-20">
        <div className="absolute top-0 left-0 w-full h-full bg-[radial-gradient(circle_at_50%_50%,rgba(255,255,255,0.02)_0%,transparent_50%)]" />
      </div>
    </div>
  );
};
