import { AnimatePresence, m } from 'framer-motion';
import { Beef, Clover, Dumbbell, Heart, PawPrint, RefreshCw, Swords, Wind } from 'lucide-react';
import React, { useEffect, useMemo, useState } from 'react';
import { apiFetch, getErrorMessage } from '../api/client';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { ProgressBar } from '../components/ui/ProgressBar';
import { useToast } from '../components/ui/Toast';
import { Pet, useUser } from '../context/UserContext';
import { cn } from '../utils';

interface MyPetsProps {
  onPetClick?: (pet: Pet) => void;
}

const getPetKey = (pet?: Pet | null) => String(pet?.petid || pet?.id || pet?.name || '');

const getPetImageSrc = (pet?: Pet | null) => {
  const src = String(pet?.img || pet?.img_url || pet?.image || pet?.photo_url || '').trim();
  return /^https?:\/\//i.test(src) || src.startsWith('/') ? src : '';
};

const samePet = (a?: Pet | null, b?: Pet | null) => {
  if (!a || !b) return false;
  const aKeys = new Set([a.petid, a.id, a.name].filter(Boolean).map(String));
  return [b.petid, b.id, b.name].filter(Boolean).some((key) => aKeys.has(String(key)));
};

const PetImage = ({
  pet,
  iconSize,
  className,
}: {
  pet: Pet;
  iconSize: number;
  className?: string;
}) => {
  const src = getPetImageSrc(pet);
  const [imageFailed, setImageFailed] = useState(false);

  // Reset when the src changes: this component instance can be reused for a
  // different pet on list reorder/switch.
  // biome-ignore lint/correctness/useExhaustiveDependencies: reset when image source changes
  useEffect(() => {
    setImageFailed(false);
  }, [src]);

  return (
    <div className={cn('overflow-hidden bg-zinc-900 relative', className)}>
      {src && !imageFailed ? (
        <img
          key={src}
          src={src}
          alt={pet.name}
          className="h-full w-full object-cover"
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setImageFailed(true)}
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center text-zinc-800">
          <PawPrint size={iconSize} />
        </div>
      )}
      <div className="absolute inset-0 bg-gradient-to-t from-black/40 to-transparent" />
    </div>
  );
};

const InlineStat = ({
  icon: Icon,
  label,
  value,
  color = 'text-zinc-500',
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  color?: string;
}) => (
  <div className="min-w-0">
    <div className="mb-0.5 flex items-center gap-1 text-[8px] font-bold uppercase tracking-widest text-zinc-600">
      <Icon size={10} className={color} />
      <span className="truncate">{label}</span>
    </div>
    <p className="truncate text-[11px] font-mono font-bold text-zinc-100 tabular-nums">{value}</p>
  </div>
);

const ActivePetCard = ({
  pet,
  onOpen,
  onFeed,
  onTrain,
  careBusy,
}: {
  pet: Pet;
  onOpen?: (pet: Pet) => void;
  onFeed?: () => void;
  onTrain?: () => void;
  careBusy?: 'feed' | 'train' | null;
}) => (
  <m.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
    <Card
      variant="surface"
      className="p-5 flex flex-col sm:flex-row gap-6 cursor-pointer group"
      onClick={() => onOpen?.(pet)}
    >
      <PetImage
        pet={pet}
        iconSize={32}
        className="w-24 h-24 sm:w-32 sm:h-32 rounded-md border border-white/10 shrink-0 mx-auto sm:mx-0"
      />

      <div className="flex-1 min-w-0 space-y-4">
        <div className="space-y-1 text-center sm:text-left">
          <div className="flex items-center justify-center sm:justify-start gap-2.5">
            <h2 className="text-xl font-bold text-zinc-100 uppercase tracking-tight truncate">
              {pet.name}
            </h2>
            <Badge variant="primary" size="xs">
              ACTIVE
            </Badge>
          </div>
          <p className="text-[10px] font-medium text-zinc-500 uppercase tracking-widest leading-relaxed line-clamp-2">
            {pet.desc || pet.ability || 'Loyal companion'}
          </p>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 py-4 border-y border-white/5">
          <InlineStat icon={Heart} label="Vitality" value={pet.hp ?? 0} color="text-emerald-500" />
          <InlineStat icon={Swords} label="Strike" value={pet.atk ?? 0} color="text-red-500" />
          <InlineStat icon={Wind} label="Velocity" value={pet.spd ?? 0} color="text-brand-accent" />
          <InlineStat
            icon={Clover}
            label="Luck"
            value={`${Math.round(Number(pet.luck || 0) * 100)}%`}
            color="text-amber-500"
          />
        </div>

        <div className="flex flex-wrap items-center justify-center sm:justify-start gap-3">
          <Badge variant="secondary" size="xs" className="font-mono">
            LVL {pet.level || 1}
          </Badge>
          <Badge variant="secondary" size="xs" className="font-mono">
            SYNC: {pet.affection ?? 0}%
          </Badge>
        </div>

        <ProgressBar
          current={pet.xp || 0}
          total={Math.max(1, pet.xp_needed || 100)}
          label="XP to next level"
          compact
        />

        <div className="flex flex-wrap items-center justify-center sm:justify-start gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={onFeed}
            isLoading={careBusy === 'feed'}
            disabled={careBusy !== null}
            className="h-8 px-4"
          >
            <Beef size={13} className="mr-1.5" /> Feed
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={onTrain}
            isLoading={careBusy === 'train'}
            disabled={careBusy !== null}
            className="h-8 px-4"
          >
            <Dumbbell size={13} className="mr-1.5" /> Train
          </Button>
        </div>
      </div>
    </Card>
  </m.div>
);

export const MyPets = ({ onPetClick }: MyPetsProps) => {
  const { user, refreshUser } = useUser();
  const { addToast } = useToast();
  const [switching, setSwitching] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [careBusy, setCareBusy] = useState<'feed' | 'train' | null>(null);

  const handleCare = async (action: 'feed' | 'train') => {
    if (careBusy) return;
    setCareBusy(action);
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    try {
      const result = await apiFetch(`/pets/${action}`, { method: 'POST' });
      addToast(result?.message || 'Done.', 'success');
      await refreshUser();
    } catch (err: any) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setCareBusy(null);
    }
  };

  const pets = useMemo(() => user?.pets || [], [user?.pets]);
  const currentPet = useMemo(() => {
    if (!pets.length) return user?.current_pet || null;
    return (
      pets.find((pet) => pet.is_active || samePet(pet, user?.current_pet)) ||
      user?.current_pet ||
      pets[0]
    );
  }, [pets, user?.current_pet]);

  const sortedPets = useMemo(
    () =>
      [...pets].sort((a, b) => {
        const activeDiff =
          Number(samePet(b, currentPet) || b.is_active) -
          Number(samePet(a, currentPet) || a.is_active);
        if (activeDiff !== 0) return activeDiff;
        const levelDiff = Number(b.level || 1) - Number(a.level || 1);
        if (levelDiff !== 0) return levelDiff;
        return a.name.localeCompare(b.name);
      }),
    [currentPet, pets],
  );

  const handleRefresh = async () => {
    if (refreshing) return;
    setRefreshing(true);
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    try {
      await refreshUser();
    } finally {
      setRefreshing(false);
    }
  };

  const handleSetActive = async (pet: Pet) => {
    const petRef = getPetKey(pet);
    if (!petRef || switching || samePet(pet, currentPet) || pet.is_active) return;

    setSwitching(petRef);
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    try {
      await apiFetch(`/pets/set_active/${encodeURIComponent(petRef)}`, { method: 'POST' });
      await refreshUser();
      addToast(`${pet.name} activated.`, 'success');
    } catch (err: any) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setSwitching(null);
    }
  };

  if (!user) return null;

  return (
    <div className="pt-6 max-w-5xl mx-auto adaptive-px space-y-10 select-none">
      <header className="space-y-6">
        <div className="flex items-start justify-between gap-6">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5">
              <PawPrint className="text-brand-accent" size={20} />
              <h1 className="text-xl font-bold text-zinc-100 uppercase tracking-tight">
                Companions
              </h1>
            </div>
            <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest opacity-60">
              Your pets, their levels and bonds
            </p>
          </div>

          <Button
            variant="secondary"
            size="sm"
            onClick={handleRefresh}
            isLoading={refreshing}
            className="w-9 h-9 p-0"
          >
            <RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} />
          </Button>
        </div>
      </header>

      <div className="space-y-10">
        {currentPet && (
          <section className="space-y-4">
            <h2 className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest px-1">
              Active pet
            </h2>
            <ActivePetCard
              pet={currentPet}
              {...(onPetClick ? { onOpen: onPetClick } : {})}
              onFeed={() => handleCare('feed')}
              onTrain={() => handleCare('train')}
              careBusy={careBusy}
            />
          </section>
        )}

        <section className="space-y-4">
          <div className="flex items-center justify-between px-1">
            <h2 className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest">
              All pets
            </h2>
            <p className="text-[9px] font-bold text-zinc-700 uppercase tracking-widest">
              Sorted by level
            </p>
          </div>

          <AnimatePresence mode="popLayout">
            {sortedPets.length > 0 ? (
              <m.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="grid grid-cols-1 md:grid-cols-2 gap-4"
              >
                {sortedPets.map((pet) => {
                  const petKey = getPetKey(pet);
                  const isActive = pet.is_active || samePet(pet, currentPet);
                  const isSwitching = switching === petKey;

                  return (
                    <Card
                      key={petKey || pet.name}
                      variant="default"
                      className={cn(
                        'p-4 transition-all',
                        isActive ? 'border-brand-accent/30 bg-brand-accent/5' : 'hover:bg-zinc-900',
                      )}
                    >
                      <div className="flex gap-4">
                        <PetImage
                          pet={pet}
                          iconSize={16}
                          className="w-16 h-16 rounded-md border border-white/10 shrink-0"
                        />
                        <div className="flex-1 min-w-0 py-0.5 space-y-1">
                          <div className="flex items-center justify-between gap-2">
                            <h3 className="text-sm font-bold text-zinc-100 uppercase tracking-tight truncate">
                              {pet.name}
                            </h3>
                            {isActive && <div className="w-1 h-1 rounded-full bg-brand-accent" />}
                          </div>
                          <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest line-clamp-1">
                            {pet.ability || 'No special ability'}
                          </p>
                          <div className="flex items-center gap-2 pt-0.5">
                            <span className="text-[9px] font-mono font-bold text-zinc-600 uppercase">
                              LVL {pet.level || 1}
                            </span>
                            <span className="text-zinc-800">•</span>
                            <span className="text-[9px] font-mono font-bold text-zinc-600 uppercase">
                              Bond {pet.affection ?? 0}%
                            </span>
                          </div>
                        </div>
                      </div>

                      <div className="grid grid-cols-4 gap-2 mt-4 pt-4 border-t border-white/5">
                        <InlineStat icon={Heart} label="HP" value={pet.hp ?? 0} />
                        <InlineStat
                          icon={Swords}
                          label="ATK"
                          value={pet.atk ?? 0}
                          color="text-red-500"
                        />
                        <InlineStat icon={Wind} label="SPD" value={pet.spd ?? 0} />
                        <InlineStat
                          icon={Clover}
                          label="LCK"
                          value={`${Math.round(Number(pet.luck || 0) * 100)}%`}
                        />
                      </div>

                      <div className="mt-4">
                        <Button
                          onClick={() => handleSetActive(pet)}
                          disabled={isActive || isSwitching}
                          variant={isActive ? 'accent' : 'secondary'}
                          className="w-full h-9"
                          isLoading={isSwitching}
                          size="sm"
                        >
                          {isActive ? 'Active Companion' : 'Activate'}
                        </Button>
                      </div>
                    </Card>
                  );
                })}
              </m.div>
            ) : (
              <div className="py-20 border border-dashed border-white/5 rounded-lg bg-zinc-950/50 text-center flex flex-col items-center justify-center space-y-4">
                <div className="w-12 h-12 rounded-full border border-white/5 flex items-center justify-center opacity-10">
                  <PawPrint size={24} />
                </div>
                <p className="text-[9px] font-bold text-zinc-700 uppercase tracking-widest">
                  No pets yet — visit the Breeder
                </p>
              </div>
            )}
          </AnimatePresence>
        </section>
      </div>
    </div>
  );
};
