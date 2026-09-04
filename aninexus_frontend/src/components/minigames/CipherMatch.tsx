import { m } from 'framer-motion';
import { Activity, Scan, ShieldAlert, Star } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Button } from '../ui/Button';
import { cn, haptics } from '../../utils';
import type { SessionData } from './types';

const MAX_MOVES = 24;

export const CipherMatch = ({
  session,
  onComplete,
  onCancel,
}: {
  session: SessionData;
  onComplete: (score: number) => void;
  onCancel: () => void;
}) => {
  const [cards, setCards] = useState<
    {
      id: string;
      img_url: string;
      name: string;
      isFlipped: boolean;
      isMatched: boolean;
      key: number;
    }[]
  >([]);
  const [flippedIndices, setFlippedIndices] = useState<number[]>([]);
  const [matches, setMatches] = useState(0);
  const [moves, setMoves] = useState(0);
  const [failed, setFailed] = useState(false);
  const matchesRef = useRef(0);
  const timeoutsRef = useRef<number[]>([]);

  // Cancel pending flip timeouts on unmount (e.g. user aborts mid-game) so
  // they can't fire setState/onComplete after the game is gone.
  useEffect(() => {
    return () => {
      for (const t of timeoutsRef.current) window.clearTimeout(t);
    };
  }, []);

  useEffect(() => {
    if (!session.cards) return;
    const doubled = [...session.cards, ...session.cards];
    // Fisher-Yates: sort(() => random) is not a uniform shuffle.
    for (let i = doubled.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      const a = doubled[i];
      const b = doubled[j];
      if (a && b) {
        doubled[i] = b;
        doubled[j] = a;
      }
    }
    matchesRef.current = 0;
    setMatches(0);
    setCards(
      doubled.map((card, index) => ({ ...card, isFlipped: false, isMatched: false, key: index })),
    );
  }, [session.cards]);

  const handleCardClick = (index: number) => {
    const clickedCard = cards[index];
    if (
      failed ||
      !clickedCard ||
      clickedCard.isFlipped ||
      clickedCard.isMatched ||
      flippedIndices.length === 2
    )
      return;

    haptics.light();
    const newCards = [...cards];
    const newCard = newCards[index];
    if (newCard) newCard.isFlipped = true;
    setCards(newCards);

    const newFlipped = [...flippedIndices, index];
    setFlippedIndices(newFlipped);

    if (newFlipped.length === 2) {
      const nextMoves = moves + 1;
      setMoves(nextMoves);
      const [first, second] = newFlipped;
      const firstCard = first !== undefined ? cards[first] : undefined;
      const secondCard = second !== undefined ? cards[second] : undefined;

      if (firstCard && secondCard && firstCard.id === secondCard.id) {
        haptics.notification('success');
        matchesRef.current += 1;
        const nextMatches = matchesRef.current;
        timeoutsRef.current.push(
          window.setTimeout(() => {
            setCards((prev) => {
              const updated = [...prev];
              if (first !== undefined && updated[first]) updated[first].isMatched = true;
              if (second !== undefined && updated[second]) updated[second].isMatched = true;
              return updated;
            });
            setMatches(nextMatches);
            setFlippedIndices([]);
            // Fire outside the state updater: React may invoke updaters more
            // than once, which would double-submit the reward.
            if (nextMatches === session.cards!.length) {
              onComplete(nextMatches);
            }
          }, 400),
        );
      } else {
        timeoutsRef.current.push(
          window.setTimeout(() => {
            if (nextMoves >= MAX_MOVES) {
              haptics.notification('error');
              setFailed(true);
            }
            setCards((prev) => {
              const updated = [...prev];
              if (first !== undefined && updated[first]) updated[first].isFlipped = false;
              if (second !== undefined && updated[second]) updated[second].isFlipped = false;
              return updated;
            });
            setFlippedIndices([]);
          }, 800),
        );
      }
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between px-2">
        <div className="flex items-center gap-6">
          <div className="relative">
            <span className="block text-[7px] font-bold text-zinc-500 uppercase tracking-[0.2em] mb-1">
              Grid Sync
            </span>
            <div className="flex items-center gap-2">
              <Activity size={10} className="text-brand-accent animate-pulse" />
              <span className="text-base font-mono font-bold text-zinc-100">
                {matches} <span className="text-zinc-600 text-xs">/ {session.cards?.length}</span>
              </span>
            </div>
          </div>
          <div className="w-px h-6 bg-white/5" />
          <div className="relative">
            <span className="block text-[7px] font-bold text-zinc-500 uppercase tracking-[0.2em] mb-1">
              Sync Capacity
            </span>
            <div className="flex items-center gap-2">
              <ShieldAlert
                size={10}
                className={cn(moves > MAX_MOVES * 0.7 ? 'text-red-500' : 'text-zinc-500')}
              />
              <span
                className={cn(
                  'text-base font-mono font-bold',
                  moves > MAX_MOVES * 0.7 ? 'text-red-400' : 'text-zinc-100',
                )}
              >
                {MAX_MOVES - moves}
                <span className="text-zinc-600 text-xs"> Left</span>
              </span>
            </div>
          </div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={onCancel}
          className="text-[9px] font-bold uppercase tracking-widest text-zinc-600 hover:text-red-400"
        >
          Abort
        </Button>
      </div>

      <div className="grid grid-cols-4 gap-2">
        {cards.map((card, idx) => (
          <div key={card.key} className="aspect-[3/4] perspective-1000">
            <m.div
              initial={false}
              animate={{ rotateY: card.isFlipped || card.isMatched ? 180 : 0 }}
              transition={{ type: 'spring', stiffness: 260, damping: 20 }}
              className="relative w-full h-full preserve-3d"
              onClick={() => handleCardClick(idx)}
            >
              {/* Front (Hidden) */}
              <div className="absolute inset-0 backface-hidden rounded-lg bg-zinc-900 border border-white/5 flex items-center justify-center cursor-pointer overflow-hidden group">
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(59,130,246,0.05)_0%,transparent_70%)] opacity-0 group-hover:opacity-100 transition-opacity" />
                <Scan
                  size={24}
                  className="text-zinc-800 group-hover:text-brand-accent/40 transition-colors"
                />
                <div className="absolute bottom-1 right-1">
                  <div className="w-1 h-1 bg-zinc-800 rounded-full" />
                </div>
              </div>

              {/* Back (Visible) */}
              <div className="absolute inset-0 backface-hidden rounded-lg bg-zinc-100 border border-white overflow-hidden rotateY-180">
                <img
                  src={card.img_url}
                  alt={card.name}
                  referrerPolicy="no-referrer"
                  className="w-full h-full object-cover"
                />
                {card.isMatched && (
                  <div className="absolute inset-0 bg-brand-accent/20 backdrop-blur-[1px] flex items-center justify-center">
                    <div className="w-8 h-8 rounded-full bg-white flex items-center justify-center shadow-lg">
                      <Star size={14} className="text-brand-accent fill-brand-accent" />
                    </div>
                  </div>
                )}
              </div>
            </m.div>
          </div>
        ))}
      </div>

      {failed && (
        <m.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="absolute inset-0 z-50 bg-black/80 backdrop-blur-sm flex flex-col items-center justify-center p-6 text-center"
        >
          <ShieldAlert size={48} className="text-red-500 mb-4" />
          <h3 className="text-xl font-bold text-white uppercase tracking-tighter mb-2">
            Sync Failure
          </h3>
          <p className="text-xs text-zinc-500 uppercase tracking-widest mb-6">
            Operational capacity exceeded
          </p>
          <div className="flex gap-3 w-full">
            <Button onClick={onCancel} variant="ghost" className="flex-1 text-zinc-400">
              Exit
            </Button>
            <Button
              onClick={() => onComplete(matches)}
              className="flex-1 bg-red-500 hover:bg-red-600 text-white"
            >
              Submit Progress
            </Button>
          </div>
        </m.div>
      )}
    </div>
  );
};
