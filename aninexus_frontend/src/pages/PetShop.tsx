import { AnimatePresence, m } from 'framer-motion';
import { Bone, CheckCircle2, Coins, Lock, PawPrint } from 'lucide-react';
import { useEffect, useState } from 'react';
import { apiFetch, getErrorMessage } from '../api/client';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { ErrorState } from '../components/ui/ErrorState';
import { Skeleton } from '../components/ui/Skeleton';
import { useToast } from '../components/ui/Toast';
import { Pet, useUser } from '../context/UserContext';
import { useApi } from '../hooks/useApi';
import { cn, formatNumber } from '../utils';

interface PetShopProps {
  onPetClick?: (pet: Pet) => void;
}

interface PetShopResponse {
  pets: Pet[];
  owned: string[];
  owned_ids?: string[];
  current_level: number;
}

const getPetRef = (pet: Pet) => String(pet.petid || pet.id || pet.name || '');

const getPetImageSrc = (pet: Pet) => {
  const src = String(pet.img || pet.img_url || pet.image || pet.photo_url || '').trim();
  return /^https?:\/\//i.test(src) || src.startsWith('/') ? src : '';
};

const PetShopImage = ({ pet, className }: { pet: Pet; className?: string }) => {
  const src = getPetImageSrc(pet);
  const [imageFailed, setImageFailed] = useState(false);

  useEffect(() => {
    setImageFailed(false);
  }, [src]);

  return src && !imageFailed ? (
    <img
      key={src}
      src={src}
      alt={pet.name}
      className={className}
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setImageFailed(true)}
    />
  ) : (
    <div className={cn(className, 'flex items-center justify-center text-zinc-800 bg-zinc-900')}>
      <PawPrint size={32} />
    </div>
  );
};

export const PetShop = ({ onPetClick }: PetShopProps) => {
  const { user, triggerRefresh } = useUser();
  const { addToast } = useToast();
  const {
    data: shopData,
    loading,
    error,
    execute: fetchPets,
  } = useApi<PetShopResponse>('/shop/pets');
  const [buying, setBuying] = useState<string | null>(null);

  const handleBuy = async (pet: Pet) => {
    if (buying) return;
    const petRef = getPetRef(pet);
    const price = Number(pet.zenith_price || 0);
    const tg = window.Telegram?.WebApp;

    const doBuy = async () => {
      setBuying(petRef);
      tg?.HapticFeedback?.selectionChanged();
      try {
        await apiFetch(`/shop/buy/pet/${encodeURIComponent(petRef)}`, { method: 'POST' });
        addToast(`${pet.name} foi adotado.`, 'success');
        await Promise.allSettled([fetchPets(), triggerRefresh()]);
      } catch (err) {
        addToast(getErrorMessage(err), 'error');
      } finally {
        setBuying(null);
      }
    };

    if (tg?.showConfirm) {
      tg.showConfirm(`Adotar ${pet.name} por ${formatNumber(price)} Coins?`, (confirmed) => {
        if (confirmed) void doBuy();
      });
      return;
    }
    await doBuy();
  };

  if (loading && !shopData)
    return (
      <div className="pt-6 adaptive-px max-w-2xl mx-auto space-y-8">
        <div className="flex flex-col gap-1.5">
          <Skeleton className="h-8 w-40 rounded-md" />
          <Skeleton className="h-4 w-56 rounded-md opacity-50" />
        </div>
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-32 rounded-md" />
        ))}
      </div>
    );

  if (error && !shopData)
    return (
      <div className="pt-6 max-w-2xl mx-auto adaptive-px">
        <ErrorState message={error} onAction={fetchPets} />
      </div>
    );

  const pets = shopData?.pets || [];
  const ownedIds = shopData?.owned_ids || [];
  const currentLevel = shopData?.current_level || 1;
  const coinBalance = Number(user?.balance ?? user?.stats?.points ?? 0);

  return (
    <div className="pt-6 max-w-3xl mx-auto adaptive-px space-y-8 select-none">
      <header className="space-y-1">
        <div className="flex items-center gap-2.5">
          <Bone className="text-brand-accent" size={20} />
          <h1 className="text-xl font-bold text-zinc-100 uppercase tracking-tight">
            Loja de Companheiros
          </h1>
        </div>
        <div className="flex items-center gap-2 opacity-60">
          <PawPrint size={10} className="text-zinc-500" />
          <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
            Adote companheiros que modificam sua experiência no AniNexus
          </p>
        </div>
      </header>

      <Card variant="surface" className="p-4 flex items-center justify-between">
        <div>
          <p className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest">Seu saldo</p>
          <p className="text-xl font-mono font-bold text-zinc-100 mt-1">{formatNumber(coinBalance)}</p>
        </div>
        <div className="w-10 h-10 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
          <Coins size={18} className="text-amber-500" />
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4">
        <AnimatePresence mode="popLayout">
          {pets.map((pet, i) => {
            const petRef = getPetRef(pet);
            const reqLevel = Number(pet.req_level || 1);
            const price = Number(pet.zenith_price || 0);
            const isOwned =
              ownedIds.includes(petRef) ||
              ownedIds.includes(String(pet.id)) ||
              (shopData?.owned || []).includes(pet.name);
            const isLocked = !isOwned && currentLevel < reqLevel;
            const canAfford = coinBalance >= price;

            return (
              <m.div
                layout
                key={pet.id || pet.name}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
              >
                <Card
                  variant="default"
                  onClick={() => onPetClick?.({ ...pet, shopIndex: i })}
                  className={cn(
                    'p-5 flex flex-col sm:flex-row gap-5 items-center cursor-pointer transition-all',
                    isOwned ? 'border-emerald-500/10 bg-emerald-500/[0.01]' : 'hover:bg-zinc-900',
                    isLocked && 'opacity-50 grayscale',
                  )}
                >
                  <div className="relative shrink-0">
                    <div
                      className={cn(
                        'w-24 h-24 rounded-md overflow-hidden border bg-zinc-900',
                        isOwned ? 'border-emerald-500/30' : 'border-white/5',
                      )}
                    >
                      <PetShopImage pet={pet} className="w-full h-full object-cover" />
                    </div>

                    {isOwned && (
                      <div className="absolute -top-2 -right-2 bg-emerald-500 text-black w-6 h-6 rounded-full flex items-center justify-center shadow-lg border-4 border-zinc-950">
                        <CheckCircle2 size={14} strokeWidth={3} />
                      </div>
                    )}

                    {isLocked && (
                      <div className="absolute inset-0 flex items-center justify-center bg-black/40 rounded-md">
                        <Lock size={18} className="text-white" />
                      </div>
                    )}
                  </div>

                  <div className="flex-1 min-w-0 space-y-4 w-full text-center sm:text-left">
                    <div className="space-y-1">
                      <h2 className="text-lg font-bold text-zinc-100 uppercase tracking-tight">{pet.name}</h2>
                      <p className="text-[10px] font-bold text-brand-accent uppercase tracking-widest">
                        {pet.ability || 'Sem habilidade especial'}
                      </p>
                      <p className="text-[10px] text-zinc-500 leading-relaxed">{pet.desc}</p>
                    </div>

                    <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-4 border-t border-white/5">
                      <div className="flex items-center gap-6">
                        <div className="space-y-0.5">
                          <span className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest block">Preço</span>
                          <div className="flex items-center justify-center sm:justify-start gap-1.5">
                            <Coins size={14} className="text-amber-500" />
                            <span className="text-base font-mono font-bold text-zinc-100">{formatNumber(price)}</span>
                          </div>
                        </div>
                        <div className="space-y-0.5">
                          <span className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest block">Classe</span>
                          <Badge variant="secondary" size="xs">{pet.rarity?.toUpperCase() || 'PADRÃO'}</Badge>
                        </div>
                      </div>

                      <div className="w-full sm:w-auto">
                        {!isOwned && !isLocked && (
                          <Button
                            variant={canAfford ? 'accent' : 'secondary'}
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              void handleBuy(pet);
                            }}
                            isLoading={buying === petRef}
                            disabled={!canAfford}
                            className="w-full sm:w-auto px-8 h-10"
                          >
                            {canAfford ? 'Adotar' : 'Coins insuficientes'}
                          </Button>
                        )}

                        {isOwned && (
                          <Badge variant="success" className="py-2 px-6">JÁ POSSUI</Badge>
                        )}

                        {isLocked && (
                          <div className="text-center sm:text-right">
                            <Badge variant="secondary" className="opacity-50 px-6">BLOQUEADO</Badge>
                            <p className="text-[8px] font-bold text-zinc-700 uppercase tracking-widest mt-1">
                              REQUER NÍVEL {reqLevel}
                            </p>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </Card>
              </m.div>
            );
          })}
        </AnimatePresence>
      </div>
    </div>
  );
};
