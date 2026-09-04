import { AnimatePresence, m } from 'framer-motion';
import { Lock, Trophy } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { haptics } from '../../utils';
import type { Reward } from './types';

export const RewardModal = ({ rewards, onClose }: { rewards: Reward; onClose: () => void }) => {
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    haptics.notification('success');
  }, []);

  return (
    <m.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="fixed inset-0 z-[200] bg-black/90 backdrop-blur-2xl flex items-center justify-center p-6"
    >
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-brand-accent/10 blur-[120px] rounded-full" />
      </div>

      <AnimatePresence mode="wait">
        {!revealed && rewards.character ? (
          <m.div
            key="box"
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 1.2, opacity: 0, filter: 'brightness(2) blur(10px)' }}
            className="relative flex flex-col items-center gap-8"
          >
            <m.div
              animate={{
                y: [0, -10, 0],
                rotate: [0, 1, -1, 0],
              }}
              transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
              className="w-48 h-48 relative"
            >
              <div className="absolute inset-0 bg-brand-accent/20 rounded-3xl blur-2xl animate-pulse" />
              <div className="absolute inset-0 bg-zinc-900 border border-white/10 rounded-3xl flex items-center justify-center overflow-hidden shadow-2xl">
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(59,130,246,0.1)_0%,transparent_70%)]" />
                <Lock size={64} className="text-brand-accent" />
                <div className="absolute bottom-0 left-0 w-full h-1 bg-brand-accent shadow-[0_0_20px_rgba(59,130,246,0.5)]" />
              </div>
            </m.div>

            <div className="text-center space-y-2">
              <h3 className="text-xl font-bold text-white uppercase tracking-[0.3em]">
                Mystery Prize
              </h3>
              <p className="text-[9px] text-zinc-500 uppercase tracking-widest">
                Tap to reveal what you won
              </p>
            </div>

            <Button
              onClick={() => {
                haptics.heavy();
                setRevealed(true);
              }}
              className="w-64 bg-white text-black font-bold uppercase tracking-widest text-[10px] py-4 rounded-xl"
            >
              Reveal Prize
            </Button>
          </m.div>
        ) : (
          <m.div
            key="content"
            initial={{ scale: 0.9, opacity: 0, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            className="w-full max-w-sm bg-zinc-950/50 border border-white/10 rounded-3xl overflow-hidden shadow-2xl relative"
          >
            <div className="p-8 text-center space-y-8">
              <div className="space-y-2">
                <div className="flex justify-center mb-4">
                  <div className="w-12 h-12 rounded-xl bg-brand-accent/10 flex items-center justify-center border border-brand-accent/20">
                    <Trophy size={24} className="text-brand-accent" />
                  </div>
                </div>
                <h3 className="text-xl font-bold text-zinc-100 uppercase tracking-wider">
                  You won!
                </h3>
                <p className="text-[10px] text-zinc-500 uppercase tracking-[0.2em]">
                  Operational rewards allocated
                </p>
              </div>

              {rewards.character && (
                <m.div
                  initial={{ y: 20, opacity: 0 }}
                  animate={{ y: 0, opacity: 1 }}
                  transition={{ delay: 0.2 }}
                  className="relative group"
                >
                  <div className="absolute -inset-4 bg-purple-500/10 blur-2xl rounded-full opacity-50" />
                  <div className="relative aspect-[3/4] rounded-2xl overflow-hidden border-2 border-purple-500/30 shadow-2xl">
                    <img
                      src={rewards.character.img_url}
                      alt={rewards.character.name}
                      referrerPolicy="no-referrer"
                      className="w-full h-full object-cover"
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-black via-transparent to-transparent" />
                    <div className="absolute bottom-0 left-0 w-full p-4 text-left">
                      <Badge className="bg-purple-500/20 text-purple-300 border-purple-500/30 mb-2 uppercase tracking-widest text-[8px]">
                        {rewards.character.rarity}
                      </Badge>
                      <div className="text-lg font-bold text-white leading-tight">
                        {rewards.character.name}
                      </div>
                      <div className="text-[10px] text-zinc-400 font-medium">
                        {rewards.character.anime}
                      </div>
                    </div>
                  </div>
                </m.div>
              )}

              <div className="grid grid-cols-2 gap-4">
                <div className="p-4 rounded-2xl bg-zinc-900/50 border border-white/[0.05] flex flex-col items-center gap-1">
                  <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest">
                    Coins
                  </span>
                  <span className="text-2xl font-mono font-bold text-zinc-100">
                    +{rewards.shards}
                  </span>
                </div>
                <div className="p-4 rounded-2xl bg-zinc-900/50 border border-white/[0.05] flex flex-col items-center gap-1">
                  <span className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest">
                    Exp
                  </span>
                  <span className="text-2xl font-mono font-bold text-zinc-100">+{rewards.xp}</span>
                </div>
              </div>

              <Button
                onClick={onClose}
                className="w-full bg-zinc-100 text-zinc-950 font-bold uppercase tracking-widest text-[10px] py-4 rounded-xl"
              >
                Confirm & Close
              </Button>
            </div>
          </m.div>
        )}
      </AnimatePresence>
    </m.div>
  );
};
