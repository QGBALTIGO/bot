import { AnimatePresence, m } from 'framer-motion';
import {
  Clover,
  Heart,
  History,
  PawPrint,
  ShieldCheck,
  Swords,
  Target,
  TrendingUp,
  Wind,
  X,
  Zap,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { apiFetch, getErrorMessage } from '../../api/client';
import { type Pet, type User, useUser } from '../../context/UserContext';
import { cn } from '../../utils';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { ProgressBar } from '../ui/ProgressBar';
import { useToast } from '../ui/Toast';

interface PetActionModalProps {
  selectedPet: Pet | null;
  setSelectedPet: (pet: Pet | null) => void;
  user: User | null;
}

export const PetActionModal = ({ selectedPet, setSelectedPet, user }: PetActionModalProps) => {
  const { addToast } = useToast();
  const { triggerRefresh } = useUser();
  const [actionStage, setActionStage] = useState<'idle' | 'loading'>('idle');
  const dialogRef = useRef<HTMLDivElement>(null);

  const isOwned = (user?.pets || []).some(
    (p: Pet) => String(p.petid || p.id) === String(selectedPet?.petid || selectedPet?.id),
  );
  const isActive =
    user?.current_pet &&
    String(user.current_pet.petid || user.current_pet.id) ===
      String(selectedPet?.petid || selectedPet?.id);

  useEffect(() => {
    if (selectedPet) {
      document.body.style.overflow = 'hidden';
      return () => {
        document.body.style.overflow = 'unset';
      };
    }
    return undefined;
  }, [selectedPet]);

  useEffect(() => {
    if (!selectedPet) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSelectedPet(null);
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
  }, [selectedPet, setSelectedPet]);

  if (!selectedPet) return null;

  const handleSetActive = async () => {
    // Never fall back to the display name: it is not a valid API identifier.
    const petRef = selectedPet.petid || selectedPet.id;
    if (!petRef) return;

    setActionStage('loading');
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    try {
      await apiFetch(`/pets/set_active/${encodeURIComponent(petRef)}`, { method: 'POST' });
      await triggerRefresh();
      addToast(`${selectedPet.name} activated.`, 'success');
      setSelectedPet(null);
    } catch (err: any) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setActionStage('idle');
    }
  };

  const imgUrl =
    selectedPet.img || selectedPet.img_url || selectedPet.image || selectedPet.photo_url || '';

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-[1000] flex items-end sm:items-center justify-center p-0 sm:p-6">
        <m.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="absolute inset-0 bg-black/60 backdrop-blur-md"
          onClick={() => {
            // Don't dismiss mid-request; the POST would keep running.
            if (actionStage !== 'loading') setSelectedPet(null);
          }}
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
          aria-label={selectedPet?.name}
          tabIndex={-1}
        >
          {/* Header Controls */}
          <div className="absolute right-4 top-4 z-20">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSelectedPet(null)}
              className="w-8 h-8 p-0 rounded-full bg-black/20 backdrop-blur-md border border-white/5 hover:bg-black/40"
              aria-label="Close"
            >
              <X size={16} />
            </Button>
          </div>

          {/* Media Section */}
          <div className="relative aspect-[16/9] flex-shrink-0 bg-zinc-900/50 flex items-center justify-center overflow-hidden">
            <div className="absolute inset-0 bg-gradient-to-t from-zinc-950 via-transparent to-transparent" />

            {imgUrl ? (
              <m.img
                initial={{ scale: 1.05, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ duration: 0.6 }}
                src={imgUrl}
                referrerPolicy="no-referrer"
                className="w-full h-full object-cover"
                alt={selectedPet.name}
              />
            ) : (
              <div className="flex flex-col items-center gap-3 opacity-20">
                <PawPrint size={48} className="text-zinc-500" />
                <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                  No Image
                </span>
              </div>
            )}

            <div className="absolute bottom-4 left-4 z-20 flex gap-2">
              <Badge variant="primary" size="sm">
                {selectedPet.rarity?.toUpperCase() || 'STANDARD'}
              </Badge>
              {isActive && (
                <Badge variant="success" size="sm">
                  ACTIVE
                </Badge>
              )}
            </div>
          </div>

          {/* Content Section — scrolls when the sheet is taller than the viewport */}
          <div className="flex-1 p-6 space-y-6 overflow-y-auto overscroll-contain max-sm:pb-[max(1.5rem,var(--sab))]">
            <div className="space-y-1.5">
              <div className="flex items-center gap-1.5">
                <Target size={11} className="text-zinc-500" />
                <span className="text-[9px] font-mono font-bold uppercase text-zinc-500 tracking-widest">
                  PET ID: {String(selectedPet.petid || selectedPet.id || 'TEMP').toUpperCase()}
                </span>
              </div>
              <h2 className="text-2xl font-bold text-zinc-100 uppercase tracking-tight">
                {selectedPet.name}
              </h2>
              <div className="flex items-center gap-1.5">
                <Zap size={12} className="text-brand-accent" />
                <p className="text-[11px] font-bold text-zinc-500 uppercase tracking-widest leading-none">
                  {selectedPet.ability || 'SYSTEM_SUPPORT_PERK'}
                </p>
              </div>
            </div>

            {selectedPet.desc && (
              <div className="bg-zinc-900 border border-white/5 p-4 rounded-md relative">
                <p className="text-[11px] font-medium text-zinc-400 uppercase tracking-widest leading-relaxed">
                  {selectedPet.desc}
                </p>
              </div>
            )}

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
              {[
                {
                  icon: Heart,
                  label: 'Vitality',
                  value: selectedPet.hp ?? 0,
                  color: 'text-emerald-500',
                },
                {
                  icon: Swords,
                  label: 'Strike',
                  value: selectedPet.atk ?? 0,
                  color: 'text-red-500',
                },
                {
                  icon: Wind,
                  label: 'Velocity',
                  value: selectedPet.spd ?? 0,
                  color: 'text-brand-accent',
                },
                {
                  icon: Clover,
                  label: 'Luck',
                  value: `${Math.round(Number(selectedPet.luck || 0) * 100)}%`,
                  color: 'text-amber-500',
                },
              ].map((stat, i) => (
                <div key={i} className="bg-zinc-900 border border-white/5 p-2.5 rounded-md">
                  <p className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest mb-1">
                    {stat.label}
                  </p>
                  <p
                    className={cn(
                      'text-[11px] font-mono font-bold tabular-nums leading-none',
                      stat.color,
                    )}
                  >
                    {stat.value}
                  </p>
                </div>
              ))}
            </div>

            {isOwned && (
              <div className="space-y-4 pt-2">
                <div className="flex items-center justify-between px-1">
                  <div className="flex items-center gap-2">
                    <TrendingUp size={12} className="text-zinc-600" />
                    <span className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest">
                      Progress
                    </span>
                  </div>
                  <Badge variant="secondary" size="xs" className="font-mono">
                    LVL {selectedPet.level || 1}
                  </Badge>
                </div>
                <ProgressBar
                  current={selectedPet.xp || 0}
                  total={selectedPet.xp_needed || 1000}
                  compact
                />
              </div>
            )}

            <div className="pt-6 border-t border-white/5 flex flex-col gap-4">
              {isOwned ? (
                <Button
                  onClick={handleSetActive}
                  disabled={isActive || actionStage === 'loading'}
                  variant={isActive ? 'secondary' : 'accent'}
                  className="w-full h-14"
                  isLoading={actionStage === 'loading'}
                  leftIcon={isActive ? <ShieldCheck size={18} /> : <History size={18} />}
                >
                  {isActive ? 'Active Sync' : 'Activate Companion'}
                </Button>
              ) : (
                <div className="bg-zinc-900 border border-white/5 p-4 rounded-md flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Zap size={16} className="text-zinc-600" />
                    <span className="text-sm font-bold text-zinc-500 uppercase tracking-widest">
                      Visit Breeder
                    </span>
                  </div>
                  <Badge variant="secondary" size="sm">
                    LOCKED
                  </Badge>
                </div>
              )}
            </div>
          </div>

          <div className="h-[calc(var(--sab,24px)+4px)] sm:hidden" />
        </m.div>
      </div>
    </AnimatePresence>
  );
};
