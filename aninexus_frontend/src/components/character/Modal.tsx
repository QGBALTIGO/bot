import { AnimatePresence, m } from 'framer-motion';
import { Gem, Info, Package, ShieldCheck, Target, Terminal, X } from 'lucide-react';
import { type ReactNode, useEffect, useRef, useState } from 'react';
import { Character } from '../../context/UserContext';
import { cn, FALLBACK_IMAGE, formatNumber } from '../../utils';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';

interface ModalProps {
  character: Character | null;
  onClose: () => void;
  actions?: ReactNode;
}

export const Modal = ({ character, onClose, actions }: ModalProps) => {
  const dialogRef = useRef<HTMLDivElement>(null);
  const [imgError, setImgError] = useState(false);
  const characterId = character?.id;

  // biome-ignore lint/correctness/useExhaustiveDependencies: id is the reset trigger, not a body dep
  useEffect(() => {
    setImgError(false);
  }, [characterId]);
  useEffect(() => {
    if (character) {
      document.body.style.overflow = 'hidden';
      return () => {
        document.body.style.overflow = 'unset';
      };
    }
    return undefined;
  }, [character]);

  useEffect(() => {
    if (!character) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      // Trap Tab focus inside the open modal.
      if (e.key === 'Tab' && dialogRef.current) {
        const focusables = dialogRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        );
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (!first || !last) return;
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener('keydown', onKey);
    dialogRef.current?.focus();
    return () => window.removeEventListener('keydown', onKey);
  }, [character, onClose]);

  if (!character) return null;

  const rarityLabel = character.rarity
    .replace(
      /[\u2700-\u27bf]|[\u2190-\u21ff]|[\u2000-\u206f]|[\u2600-\u26ff]|[\u2b00-\u2bff]|[\u00a0-\u00bf]|\u2013|\u2014/g,
      '',
    )
    .trim()
    .toUpperCase();
  const stockLimit = typeof character.stock_limit === 'number' ? character.stock_limit : null;
  const stockRemaining =
    typeof character.stock_remaining === 'number'
      ? character.stock_remaining
      : stockLimit !== null && typeof character.sold_count === 'number'
        ? Math.max(0, stockLimit - character.sold_count)
        : null;
  const hasStock = stockLimit !== null && stockRemaining !== null;
  const soldOut = character.sold_out || (hasStock && stockRemaining <= 0);
  const hasPrice = typeof character.zenith_price === 'number' && character.zenith_price > 0;
  const characterIdStr = String(character.id || '');

  const getRarityVariant = (rarity: string) => {
    const r = rarity.toLowerCase();
    if (r.includes('common')) return 'secondary';
    if (r.includes('uncommon')) return 'success';
    if (r.includes('rare')) return 'rare';
    if (r.includes('epic')) return 'epic';
    if (r.includes('legendary') || r.includes('limited')) return 'premium';
    if (
      r.includes('mythical') ||
      r.includes('celestial') ||
      r.includes('divine') ||
      r.includes('astral') ||
      r.includes('prestige') ||
      r.includes('cinematic') ||
      r.includes('seraph')
    )
      return 'mythic';
    return 'primary';
  };

  const rarityVariant = getRarityVariant(rarityLabel);

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-[1000] flex items-end sm:items-center justify-center p-0 sm:p-6">
        <m.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="absolute inset-0 bg-black/60 backdrop-blur-md"
          onClick={onClose}
        />

        <m.div
          initial={{ y: '100%' }}
          animate={{ y: 0 }}
          exit={{ y: '100%' }}
          transition={{ type: 'spring', damping: 25, stiffness: 200 }}
          className="relative w-full max-w-[440px] max-h-[92svh] bg-zinc-950 rounded-t-xl sm:rounded-xl flex flex-col overflow-hidden shadow-2xl border-t sm:border border-white/5"
          ref={dialogRef}
          role="dialog"
          aria-modal="true"
          aria-label={character.name}
          tabIndex={-1}
        >
          {/* Header Controls */}
          <div className="absolute right-4 top-4 z-20">
            <Button
              variant="ghost"
              size="sm"
              onClick={onClose}
              className="w-8 h-8 p-0 rounded-full bg-black/20 backdrop-blur-md border border-white/5 hover:bg-black/40"
              aria-label="Close"
            >
              <X size={16} />
            </Button>
          </div>

          {/* Image Section */}
          <div className="relative aspect-[4/3] flex-shrink-0 bg-zinc-900/50 flex items-center justify-center overflow-hidden">
            <div className="absolute inset-0 bg-gradient-to-t from-zinc-950 via-transparent to-transparent" />

            <m.img
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ delay: 0.1, duration: 0.4 }}
              src={imgError ? FALLBACK_IMAGE : character.img_url}
              onError={() => setImgError(true)}
              referrerPolicy="no-referrer"
              className="relative z-10 w-full h-full object-contain p-6"
              alt={character.name}
            />

            <div className="absolute bottom-4 left-4 z-20 flex gap-2">
              <Badge variant={rarityVariant} size="sm">
                {rarityLabel || 'STANDARD'}
              </Badge>
              {character.owned && (
                <Badge variant="success" size="sm">
                  OWNED
                </Badge>
              )}
            </div>
          </div>

          {/* Content Section — scrolls when the sheet is taller than the viewport */}
          <div className="flex-1 p-6 sm:p-6 pb-4 sm:pb-6 space-y-4 sm:space-y-6 overflow-y-auto overscroll-contain max-sm:pb-[max(1.5rem,var(--sab))]">
            <div className="space-y-1">
              <div className="flex items-center gap-1.5">
                <Target size={11} className="text-zinc-500" />
                <span className="text-[9px] font-mono font-bold uppercase text-zinc-500 tracking-widest">
                  ID: #{characterIdStr}
                </span>
              </div>
              <h2 className="text-2xl font-bold text-zinc-100 uppercase tracking-tight">
                {character.name}
              </h2>
              <div className="flex items-center gap-1.5 opacity-60">
                <Info size={11} className="text-zinc-500" />
                <p className="text-[11px] font-bold text-zinc-500 uppercase tracking-widest leading-none">
                  {character.anime}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2">
              {[
                {
                  icon: ShieldCheck,
                  label: 'STATUS',
                  value: character.owned ? 'OWNED' : 'NOT OWNED',
                  variant: character.owned ? 'success' : 'secondary',
                },
                {
                  icon: Package,
                  label: 'SUPPLY',
                  value: hasStock
                    ? soldOut
                      ? 'DEPLETED'
                      : `${stockRemaining}/${stockLimit}`
                    : character.count > 0
                      ? `x${character.count}`
                      : 'UNLIMITED',
                  variant: soldOut ? 'danger' : 'default',
                },
                {
                  icon: Gem,
                  label: 'PRICE',
                  value: hasPrice ? formatNumber(character.zenith_price) : '0',
                  variant: 'primary',
                },
              ].map((stat, i) => (
                <Card
                  key={i}
                  variant="default"
                  className="p-2 flex flex-col justify-between border-white/[0.04] bg-zinc-900/50"
                >
                  <stat.icon
                    size={11}
                    className={cn(
                      stat.variant === 'success' && 'text-emerald-500',
                      stat.variant === 'danger' && 'text-red-500',
                      stat.variant === 'primary' && 'text-brand-accent',
                      stat.variant === 'default' && 'text-zinc-500',
                      stat.variant === 'secondary' && 'text-zinc-700',
                    )}
                  />
                  <div className="mt-1.5">
                    <span className="block text-[8px] font-bold text-zinc-600 uppercase tracking-widest mb-0.5">
                      {stat.label}
                    </span>
                    <span
                      className={cn(
                        'block truncate text-[10px] font-mono font-bold uppercase tracking-tight tabular-nums leading-none',
                        stat.variant === 'success'
                          ? 'text-emerald-500'
                          : stat.variant === 'danger'
                            ? 'text-red-500'
                            : 'text-zinc-100',
                      )}
                    >
                      {stat.value}
                    </span>
                  </div>
                </Card>
              ))}
            </div>

            {actions && (
              <div className="pt-4 sm:pt-6 border-t border-white/5 flex flex-col gap-3 sm:gap-4">
                {actions}
              </div>
            )}

            <div className="flex items-center justify-center gap-2 py-0 opacity-20">
              <Terminal size={10} className="text-brand-accent" />
              <span className="text-[8px] font-bold uppercase text-zinc-100 tracking-widest">
                End of Data
              </span>
            </div>
          </div>

          {/* Safe Area Padding */}
          <div className="h-[calc(var(--sab,8px)+4px)] sm:hidden" />
        </m.div>
      </div>
    </AnimatePresence>
  );
};
