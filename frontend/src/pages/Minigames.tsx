import { AnimatePresence, m } from 'framer-motion';
import { Brain, ChevronRight, Gamepad2, Loader2, Target } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { apiFetch, getErrorMessage } from '../api/client';
import { CipherMatch } from '../components/minigames/CipherMatch';
import { EnergyDisplay } from '../components/minigames/EnergyDisplay';
import { NexusWheel } from '../components/minigames/NexusWheel';
import { RewardModal } from '../components/minigames/RewardModal';
import type { MinigameState, Reward, SessionData } from '../components/minigames/types';
import { Card } from '../components/ui/Card';
import { useToast } from '../components/ui/Toast';
import { useUser } from '../context/UserContext';
import { cn } from '../utils';

// --- Main Page ---

export const Minigames = () => {
  const { refreshUser } = useUser();
  const { addToast } = useToast();
  const [state, setState] = useState<MinigameState | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [activeGame, setActiveGame] = useState<'cipher_match' | 'nexus_wheel' | null>(null);
  const [session, setSession] = useState<SessionData | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [starting, setStarting] = useState(false);
  const [rewards, setRewards] = useState<Reward | null>(null);

  const fetchState = useCallback(async () => {
    try {
      const data = await apiFetch('/minigames/state');
      setState(data);
    } catch (err) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setIsLoading(false);
    }
  }, [addToast]);

  useEffect(() => {
    fetchState();
  }, [fetchState]);

  const handleStartGame = async (game: 'cipher_match' | 'nexus_wheel') => {
    // Guard against double-taps creating two sessions (double energy deduct).
    if (starting) return;
    if (!state || state.energy <= 0) {
      addToast('Insufficient energy reserve', 'error');
      return;
    }

    setStarting(true);
    try {
      setIsLoading(true);
      const data = await apiFetch(`/minigames/start/${game}`, { method: 'POST' });
      setSession(data.session);
      setActiveGame(game);
      // Optimization: update local energy state immediately
      setState((prev) => (prev ? { ...prev, energy: prev.energy - 1 } : null));
    } catch (err) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setIsLoading(false);
      setStarting(false);
    }
  };

  const handleSubmit = async (score: number) => {
    if (!activeGame) return;
    setSubmitting(true);
    try {
      const data = await apiFetch('/minigames/submit', {
        method: 'POST',
        body: JSON.stringify({ game_type: activeGame, score }),
      });
      setRewards(data.rewards);
      setActiveGame(null);
      refreshUser();
      fetchState();
    } catch (err) {
      addToast(getErrorMessage(err), 'error');
      setActiveGame(null);
      fetchState();
    } finally {
      setSubmitting(false);
    }
  };

  if (isLoading && !state) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh]">
        <Loader2 size={24} className="text-zinc-800 animate-spin" />
      </div>
    );
  }

  return (
    <div className="adaptive-px pt-6">
      <header className="mb-8 space-y-1">
        <div className="flex items-center gap-2.5">
          <Gamepad2 className="text-brand-accent" size={20} />
          <h1 className="text-xl font-bold text-zinc-100 uppercase tracking-tight">
            Nexus Games
          </h1>
        </div>
        <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest opacity-60">
          Operational training & testing
        </p>
      </header>

      {state && (
        <EnergyDisplay
          energy={state.energy}
          maxEnergy={state.max_energy}
          lastRecharge={state.last_energy_recharge}
          onRecharge={fetchState}
        />
      )}

      <AnimatePresence mode="wait">
        {!activeGame ? (
          <m.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="space-y-4"
          >
            <Card
              onClick={() => handleStartGame('cipher_match')}
              className={cn(
                'p-5 border-white/[0.04] bg-zinc-900/40 cursor-pointer group transition-all relative overflow-hidden',
                (state?.energy === 0 || starting) && 'opacity-50 grayscale pointer-events-none',
              )}
            >
              <div className="flex items-center justify-between relative z-10">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-xl bg-zinc-950 flex items-center justify-center border border-white/5 shadow-inner">
                    <Brain
                      size={20}
                      className="text-zinc-500 group-hover:text-brand-accent transition-colors"
                    />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-zinc-200 uppercase tracking-wider mb-0.5">
                      Cipher Match
                    </h3>
                    <p className="text-[10px] text-zinc-500 font-medium uppercase tracking-widest">
                      Memory sequence training
                    </p>
                  </div>
                </div>
                <ChevronRight
                  size={18}
                  className="text-zinc-700 group-hover:translate-x-1 transition-transform"
                />
              </div>
            </Card>

            <Card
              onClick={() => handleStartGame('nexus_wheel')}
              className={cn(
                'p-5 border-white/[0.04] bg-zinc-900/40 cursor-pointer group transition-all relative overflow-hidden',
                (state?.energy === 0 || starting) && 'opacity-50 grayscale pointer-events-none',
              )}
            >
              <div className="flex items-center justify-between relative z-10">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-xl bg-zinc-950 flex items-center justify-center border border-white/5 shadow-inner">
                    <Target
                      size={20}
                      className="text-zinc-500 group-hover:text-purple-400 transition-colors"
                    />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-zinc-200 uppercase tracking-wider mb-0.5">
                      Nexus Wheel
                    </h3>
                    <p className="text-[10px] text-zinc-500 font-medium uppercase tracking-widest">
                      Random resource allocation
                    </p>
                  </div>
                </div>
                <ChevronRight
                  size={18}
                  className="text-zinc-700 group-hover:translate-x-1 transition-transform"
                />
              </div>
            </Card>
          </m.div>
        ) : (
          <m.div
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.98 }}
            className="min-h-[400px] flex flex-col justify-center relative"
          >
            {activeGame === 'cipher_match' && session && (
              <CipherMatch
                session={session}
                onComplete={handleSubmit}
                onCancel={() => setActiveGame(null)}
              />
            )}
            {activeGame === 'nexus_wheel' && session && (
              <NexusWheel
                session={session}
                onComplete={() => handleSubmit(0)}
                _onCancel={() => setActiveGame(null)}
              />
            )}
          </m.div>
        )}
      </AnimatePresence>

      {submitting && (
        <div className="fixed inset-0 z-[250] bg-black/60 backdrop-blur-sm flex items-center justify-center">
          <div className="flex flex-col items-center gap-4">
            <Loader2 size={32} className="text-brand-accent animate-spin" />
            <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-[0.3em]">
              Processing Rewards
            </span>
          </div>
        </div>
      )}

      {rewards && <RewardModal rewards={rewards} onClose={() => setRewards(null)} />}
    </div>
  );
};
