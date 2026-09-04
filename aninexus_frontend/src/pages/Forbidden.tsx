import { m } from 'framer-motion';
import { ArrowLeft, Home, Lock, Terminal } from 'lucide-react';
import { useEffect } from 'react';
import { Button } from '../components/ui/Button';

export const Forbidden = ({ onReset }: { onReset: () => void }) => {
  useEffect(() => {
    window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred('error');
  }, []);

  return (
    <div className="min-h-[80svh] flex flex-col items-center justify-center p-8 text-center select-none relative overflow-hidden">
      <m.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-sm flex flex-col items-center relative z-10"
      >
        <div className="w-20 h-20 rounded-2xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center mb-8">
          <Lock className="text-amber-500" size={32} />
        </div>

        <div className="space-y-2 mb-10">
          <h1 className="text-5xl font-bold text-zinc-100 tracking-tight">403</h1>
          <h2 className="text-lg font-bold text-zinc-100 uppercase tracking-widest">
            Access Denied
          </h2>
          <p className="text-[10px] font-bold text-amber-500 uppercase tracking-widest">
            Staff only
          </p>
          <p className="text-xs font-medium text-zinc-500 leading-relaxed max-w-[260px] mx-auto uppercase tracking-widest pt-4">
            This area is limited to the ANINEXUS team.
          </p>
        </div>

        <div className="w-full max-w-[220px] space-y-3">
          <Button
            onClick={() => {
              window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
              onReset();
            }}
            className="w-full h-14"
            variant="accent"
            leftIcon={<Home size={16} />}
          >
            Return to Nexus
          </Button>

          <button
            onClick={() => window.history.back()}
            className="w-full flex items-center justify-center gap-2 py-3 text-[10px] font-bold text-zinc-600 uppercase tracking-widest hover:text-zinc-200 transition-colors"
          >
            <ArrowLeft size={12} />
            <span>Go Back</span>
          </button>
        </div>
      </m.div>

      <div className="absolute bottom-10 left-1/2 -translate-x-1/2 flex items-center gap-2 opacity-20">
        <Terminal size={10} className="text-amber-500" />
        <span className="text-[7px] font-bold uppercase tracking-widest text-zinc-100">
          Security Breach Blocked
        </span>
      </div>
    </div>
  );
};
