import { AnimatePresence, m } from 'framer-motion';
import { ShieldCheck, Terminal, Zap } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Character } from '../../context/UserContext';
import { cleanRarityLabel, FALLBACK_IMAGE } from '../../utils';
import { Badge } from './Badge';
import { Button } from './Button';

interface GachaRevealProps {
  character: Character | null;
  onClose: () => void;
}

export const GachaReveal = ({ character, onClose }: GachaRevealProps) => {
  const [imgError, setImgError] = useState(false);

  useEffect(() => {
    setImgError(false);
    if (character) {
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred('success');
    }
  }, [character]);

  if (!character) return null;

  const rarityLabel = cleanRarityLabel(character.rarity).toUpperCase();

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-[2000] flex items-center justify-center bg-black select-none overflow-hidden p-6">
        <m.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(59,130,246,0.1),transparent_70%)]"
        />

        <m.div
          initial={{ opacity: 0, scale: 0.9, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ type: 'spring', damping: 25, stiffness: 200 }}
          className="relative w-full max-w-[380px] max-h-[78svh] aspect-[3/4.5] flex flex-col items-center"
        >
          <div className="w-full h-full rounded-2xl border border-white/20 bg-zinc-950 shadow-2xl overflow-hidden relative">
            <img
              src={imgError ? FALLBACK_IMAGE : character.img_url}
              onError={() => setImgError(true)}
              alt={character.name}
              referrerPolicy="no-referrer"
              className="absolute inset-0 w-full h-full object-cover"
            />

            <div className="absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-black via-black/80 to-transparent" />

            <div className="absolute top-6 right-6">
              <div className="w-10 h-10 rounded-full bg-black/40 backdrop-blur-md border border-white/10 flex items-center justify-center">
                <ShieldCheck size={20} className="text-emerald-500" />
              </div>
            </div>

            <div className="absolute bottom-0 inset-x-0 p-8 flex flex-col items-center text-center space-y-6">
              <div className="space-y-3">
                <Badge
                  variant="primary"
                  className="px-6 h-7 text-[10px] font-bold tracking-widest bg-brand-accent text-white border-none uppercase"
                >
                  {rarityLabel}
                </Badge>

                <div className="space-y-1">
                  <h2 className="text-3xl font-bold text-white uppercase tracking-tight">
                    {character.name}
                  </h2>
                  <div className="flex items-center justify-center gap-2 opacity-50">
                    <Zap size={12} className="text-brand-accent" />
                    <p className="text-[10px] font-bold text-white uppercase tracking-widest">
                      {character.anime}
                    </p>
                  </div>
                </div>
              </div>

              <Button
                onClick={onClose}
                className="w-full h-14 bg-white text-black font-bold uppercase text-[11px] tracking-widest"
              >
                Continuar
              </Button>
            </div>
          </div>

          <m.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.2 }}
            transition={{ delay: 0.8 }}
            className="mt-8 flex items-center gap-4"
          >
            <Terminal size={16} className="text-brand-accent" />
          </m.div>
        </m.div>
      </div>
    </AnimatePresence>
  );
};
