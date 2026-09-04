import { Coins, Dice5, Lock, RefreshCw, ShoppingBag, Sparkles, Store, Zap } from 'lucide-react';
import { useCallback, useState } from 'react';
import { apiFetch, getErrorMessage } from '../api/client';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { ErrorState } from '../components/ui/ErrorState';
import { Skeleton } from '../components/ui/Skeleton';
import type { Character } from '../context/UserContext';
import { useToast } from '../components/ui/Toast';
import { useUser } from '../context/UserContext';
import { useApi } from '../hooks/useApi';
import { cn, formatNumber } from '../utils';

interface ShopProps {
  onCharClick: (char: Character) => void;
}

type Offer = {
  slot_code: string;
  group: string;
  card_id: number;
  name: string;
  title: string;
  card_no: string;
  rarity: string;
  bp: string;
  image: string;
  price: number;
  level_required: number;
  bought: boolean;
};

type ShopState = {
  coins: number;
  dado_balance: number;
  dado_max: number;
  dado_price: number;
  level: number;
  next_refresh_iso?: string | null;
  countdown_label: string;
  offers: Offer[];
};

export const Shop = ({ onCharClick }: ShopProps) => {
  void onCharClick;
  const { addToast } = useToast();
  const { refreshUser } = useUser();
  const {
    data,
    loading,
    error,
    execute: refresh,
  } = useApi<ShopState>('/source-shop');
  const [buying, setBuying] = useState<string | null>(null);

  const refreshAll = useCallback(async () => {
    await Promise.allSettled([refresh(), refreshUser()]);
  }, [refresh, refreshUser]);

  const buyDado = async () => {
    setBuying('dado');
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    try {
      await apiFetch('/source-shop/buy-dado', { method: 'POST' });
      addToast('+1 Dado adicionado ao seu saldo.', 'success');
      await refreshAll();
    } catch (err) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setBuying(null);
    }
  };

  const buyXCard = async (offer: Offer) => {
    setBuying(offer.slot_code);
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    try {
      await apiFetch(`/source-shop/buy-xcard/${encodeURIComponent(offer.slot_code)}`, {
        method: 'POST',
      });
      addToast(`${offer.name} foi adicionado às suas XCards.`, 'success');
      await refreshAll();
    } catch (err) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setBuying(null);
    }
  };

  if (error && !data) {
    return (
      <div className="pt-6 adaptive-px max-w-2xl mx-auto">
        <ErrorState message={error} onAction={refresh} />
      </div>
    );
  }

  if (loading || !data) {
    return (
      <div className="pt-6 adaptive-px max-w-5xl mx-auto space-y-8">
        <Skeleton className="h-9 w-56 rounded-md" />
        <div className="grid grid-cols-3 gap-3">
          {[1, 2, 3].map((item) => <Skeleton key={item} className="h-20 rounded-md" />)}
        </div>
        <Skeleton className="h-32 rounded-xl" />
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="aspect-[2/3] rounded-xl" />)}
        </div>
      </div>
    );
  }

  return (
    <div className="pt-6 max-w-5xl mx-auto adaptive-px space-y-8 select-none">
      <header className="space-y-6">
        <div className="flex items-start justify-between gap-6">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5">
              <Store size={20} className="text-brand-accent" />
              <h1 className="text-xl font-bold text-zinc-100 uppercase tracking-tight">Loja AniNexus</h1>
            </div>
            <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
              Itens reais do Source • ofertas de XCards renovadas diariamente
            </p>
          </div>
          <Button variant="secondary" size="sm" onClick={refreshAll} className="w-9 h-9 p-0">
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
          </Button>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <Card className="p-3.5">
            <Coins size={12} className="text-amber-500 mb-2" />
            <p className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest">Coins</p>
            <p className="text-lg font-mono font-bold text-zinc-100 mt-1">{formatNumber(data.coins)}</p>
          </Card>
          <Card className="p-3.5">
            <Dice5 size={12} className="text-brand-accent mb-2" />
            <p className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest">Dados</p>
            <p className="text-lg font-mono font-bold text-zinc-100 mt-1">{data.dado_balance}/{data.dado_max}</p>
          </Card>
          <Card className="p-3.5">
            <Zap size={12} className="text-emerald-500 mb-2" />
            <p className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest">Nível</p>
            <p className="text-lg font-mono font-bold text-zinc-100 mt-1">{data.level}</p>
          </Card>
        </div>
      </header>

      <Card variant="surface" className="p-5 sm:p-6 relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_85%_20%,rgba(59,130,246,0.10),transparent_45%)]" />
        <div className="relative z-10 flex items-center justify-between gap-5">
          <div className="flex items-center gap-4 min-w-0">
            <div className="w-14 h-14 rounded-xl bg-brand-accent/10 border border-brand-accent/20 flex items-center justify-center shrink-0">
              <Dice5 size={26} className="text-brand-accent" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <h2 className="text-sm font-bold text-zinc-100 uppercase tracking-tight">+1 Dado</h2>
                <Badge variant="primary" size="xs">{data.dado_price} Coins</Badge>
              </div>
              <p className="text-[10px] text-zinc-500 uppercase tracking-widest leading-relaxed">
                Adiciona um Dado ao mesmo saldo usado pelo comando /dado.
              </p>
            </div>
          </div>
          <Button
            onClick={buyDado}
            isLoading={buying === 'dado'}
            disabled={data.dado_balance >= data.dado_max || data.coins < data.dado_price}
            size="sm"
            className="shrink-0"
          >
            {data.dado_balance >= data.dado_max ? 'Cheio' : 'Comprar'}
          </Button>
        </div>
      </Card>

      <section className="space-y-5">
        <div className="flex items-center justify-between px-1 gap-3">
          <div className="flex items-center gap-2">
            <ShoppingBag size={14} className="text-brand-accent" />
            <h2 className="text-[10px] font-bold text-zinc-100 uppercase tracking-widest">XCards do dia</h2>
          </div>
          <Badge variant="secondary" size="xs">RENOVA EM {data.countdown_label || '--'}</Badge>
        </div>

        <div className="grid grid-cols-2 xs:grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-3 sm:gap-4">
          {(data.offers || []).map((offer, index) => {
            const locked = data.level < offer.level_required;
            const unavailable = offer.bought || locked || data.coins < offer.price;
            return (
              <m.article
                key={offer.slot_code}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: Math.min(index * 0.035, 0.25) }}
                className="rounded-xl overflow-hidden border border-white/[0.06] bg-zinc-900/50"
              >
                <div className="relative aspect-[2/3] overflow-hidden bg-zinc-950">
                  {offer.image ? (
                    <img
                      src={offer.image}
                      alt={offer.name}
                      referrerPolicy="no-referrer"
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="absolute inset-0 flex items-center justify-center"><Sparkles className="text-zinc-800" /></div>
                  )}
                  <div className="absolute inset-0 bg-gradient-to-t from-black via-transparent to-transparent" />
                  <div className="absolute top-2 left-2 right-2 flex items-center justify-between gap-2">
                    <Badge variant={offer.group === 'special' ? 'epic' : offer.group === 'rare' ? 'primary' : 'secondary'} size="xs">
                      {offer.rarity || offer.group}
                    </Badge>
                    {offer.bought && <Badge variant="success" size="xs">COMPRADO</Badge>}
                  </div>
                  <div className="absolute bottom-0 left-0 right-0 p-3">
                    <p className="text-xs font-bold text-white leading-tight line-clamp-2">{offer.name}</p>
                    <p className="text-[8px] text-zinc-400 uppercase tracking-wider mt-1 line-clamp-1">{offer.title}</p>
                    <div className="flex items-center gap-2 mt-2">
                      {offer.bp && <span className="text-[8px] font-mono text-zinc-500">BP {offer.bp}</span>}
                      {locked && <span className="text-[8px] text-red-400 flex items-center gap-1"><Lock size={8} /> NV {offer.level_required}</span>}
                    </div>
                  </div>
                </div>
                <div className="p-2.5">
                  <Button
                    variant={offer.bought ? 'ghost' : 'outline'}
                    size="sm"
                    isLoading={buying === offer.slot_code}
                    disabled={unavailable}
                    onClick={() => buyXCard(offer)}
                    className={cn('w-full h-9', offer.bought && 'opacity-50')}
                  >
                    {offer.bought ? 'Comprado' : locked ? `Nível ${offer.level_required}` : `${offer.price} Coins`}
                  </Button>
                </div>
              </m.article>
            );
          })}
        </div>
      </section>
    </div>
  );
};
