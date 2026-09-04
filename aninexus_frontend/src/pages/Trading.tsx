import { AnimatePresence, m } from 'framer-motion';
import { ArrowLeftRight, Check, Inbox, Search, Send, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiFetch, getErrorMessage, invalidateQueries } from '../api/client';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { Input } from '../components/ui/Input';
import { Skeleton } from '../components/ui/Skeleton';
import { useToast } from '../components/ui/Toast';
import { useUser } from '../context/UserContext';
import { useApi } from '../hooks/useApi';
import { cleanRarityLabel, cn, FALLBACK_IMAGE } from '../utils';

interface TradeCharacter {
  id: string;
  name: string;
  anime?: string;
  rarity: string;
  img_url: string;
  count?: number;
}

interface TradeOffer {
  id: string;
  sender_id: number;
  sender_name: string;
  receiver_id: number;
  receiver_name: string;
  sender_char: TradeCharacter;
  receiver_char: TradeCharacter;
  status: string;
}

interface CollectionPage {
  total: number;
  page: number;
  items: TradeCharacter[];
}

const statusLabel = (status: string) => {
  const labels: Record<string, string> = {
    pending: 'Pendente',
    completed: 'Concluída',
    rejected: 'Recusada',
    expired: 'Expirada',
    failed: 'Falhou',
  };
  return labels[status] || status;
};

const CharThumb = ({ char, selected, onClick }: { char: TradeCharacter; selected?: boolean; onClick?: () => void }) => {
  const [imgError, setImgError] = useState(false);
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'relative rounded-md overflow-hidden aspect-[2/3] border transition-all text-left',
        selected ? 'border-brand-accent ring-1 ring-brand-accent/50' : 'border-white/5 hover:border-white/15',
      )}
    >
      <img
        src={imgError ? FALLBACK_IMAGE : char.img_url || FALLBACK_IMAGE}
        alt={char.name}
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => setImgError(true)}
        className="absolute inset-0 w-full h-full object-cover"
      />
      <div className="absolute inset-0 bg-gradient-to-t from-black/95 via-transparent to-transparent" />
      <div className="absolute bottom-0 inset-x-0 p-2">
        <p className="text-[9px] font-bold text-white uppercase tracking-tight line-clamp-1">{char.name}</p>
        <p className="text-[8px] font-bold text-zinc-400 uppercase tracking-widest line-clamp-1">
          {cleanRarityLabel(char.rarity) || char.rarity}
        </p>
      </div>
      {Number(char.count || 0) > 1 && (
        <span className="absolute top-1 left-1 px-1.5 py-0.5 rounded bg-black/70 text-[8px] font-mono font-bold text-white">×{char.count}</span>
      )}
      {selected && (
        <div className="absolute top-1 right-1 w-5 h-5 rounded-full bg-brand-accent text-black flex items-center justify-center">
          <Check size={11} strokeWidth={3} />
        </div>
      )}
    </button>
  );
};

const OfferCard = ({ offer, isReceiver, onRespond, busy }: {
  offer: TradeOffer;
  isReceiver: boolean;
  onRespond?: (action: 'accept' | 'reject') => void;
  busy?: boolean;
}) => (
  <Card variant="default" className="p-4 space-y-4">
    <div className="flex items-center justify-between gap-3">
      <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest truncate">
        {isReceiver ? `De ${offer.sender_name}` : `Para ${offer.receiver_name}`}
      </p>
      <span className="text-[8px] font-mono font-bold text-zinc-600 uppercase shrink-0">{statusLabel(offer.status)}</span>
    </div>
    <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
      <div className="space-y-1.5">
        <p className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest text-center">
          {isReceiver ? 'Ele oferece' : 'Você oferece'}
        </p>
        <CharThumb char={offer.sender_char} />
      </div>
      <ArrowLeftRight size={17} className="text-zinc-600" />
      <div className="space-y-1.5">
        <p className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest text-center">
          {isReceiver ? 'Você entrega' : 'Você recebe'}
        </p>
        <CharThumb char={offer.receiver_char} />
      </div>
    </div>
    {isReceiver && offer.status === 'pending' && onRespond && (
      <div className="grid grid-cols-2 gap-2">
        <Button variant="accent" size="sm" className="h-10" isLoading={busy ?? false} onClick={() => onRespond('accept')}>
          <Check size={13} className="mr-1.5" /> Aceitar
        </Button>
        <Button variant="outline" size="sm" className="h-10" disabled={busy} onClick={() => onRespond('reject')}>
          <X size={13} className="mr-1.5" /> Recusar
        </Button>
      </div>
    )}
  </Card>
);

export const Trading = () => {
  const { user, refreshUser } = useUser();
  const { addToast } = useToast();
  const [tab, setTab] = useState<'inbox' | 'sent' | 'new'>('inbox');
  const [responding, setResponding] = useState<string | null>(null);
  const { data: offers, loading, error, execute: fetchOffers } = useApi<TradeOffer[]>('/trade/offers');
  const myId = user?.id;
  const inbox = useMemo(() => (offers || []).filter((o) => Number(o.receiver_id) === Number(myId)), [offers, myId]);
  const sent = useMemo(() => (offers || []).filter((o) => Number(o.sender_id) === Number(myId)), [offers, myId]);

  const [targetId, setTargetId] = useState('');
  const [targetChars, setTargetChars] = useState<TradeCharacter[]>([]);
  const [targetLoading, setTargetLoading] = useState(false);
  const [targetError, setTargetError] = useState<string | null>(null);
  const [myChars, setMyChars] = useState<TradeCharacter[]>([]);
  const [myLoading, setMyLoading] = useState(false);
  const [theirPick, setTheirPick] = useState<string | null>(null);
  const [myPick, setMyPick] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const loadTarget = useCallback(async () => {
    const id = Number(targetId.trim());
    if (!id || id === Number(myId)) return;
    setTargetLoading(true);
    setTargetError(null);
    setTheirPick(null);
    try {
      const res: CollectionPage = await apiFetch(`/trade/user/${id}/collection?limit=100`);
      setTargetChars(res.items || []);
      if (!res.items?.length) setTargetError('Esse usuário não tem personagens disponíveis para troca.');
    } catch (err) {
      setTargetChars([]);
      setTargetError(getErrorMessage(err));
    } finally {
      setTargetLoading(false);
    }
  }, [targetId, myId]);

  const loadMyChars = useCallback(async () => {
    setMyLoading(true);
    try {
      const res: CollectionPage = await apiFetch('/harem?limit=100');
      setMyChars(res.items || []);
    } catch (err) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setMyLoading(false);
    }
  }, [addToast]);

  useEffect(() => {
    if (tab === 'new' && myChars.length === 0) void loadMyChars();
  }, [tab, myChars.length, loadMyChars]);

  const handleRespond = async (offer: TradeOffer, action: 'accept' | 'reject') => {
    setResponding(offer.id);
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    try {
      await apiFetch(`/trade/respond/${offer.id}`, { method: 'POST', body: JSON.stringify({ action }) });
      addToast(action === 'accept' ? 'Troca concluída.' : 'Troca recusada.', 'success');
      if (action === 'accept') {
        await refreshUser();
        invalidateQueries(['/harem']);
      }
      await fetchOffers();
    } catch (err) {
      addToast(getErrorMessage(err), 'error');
      await fetchOffers();
    } finally {
      setResponding(null);
    }
  };

  const handleSubmit = async () => {
    const receiverId = Number(targetId.trim());
    if (!receiverId || !myPick || !theirPick || submitting) return;
    setSubmitting(true);
    try {
      await apiFetch('/trade/offer', {
        method: 'POST',
        body: JSON.stringify({ receiver_id: receiverId, sender_char_id: myPick, receiver_char_id: theirPick }),
      });
      addToast('Oferta enviada. Ela expira em 24 horas.', 'success');
      setTab('sent');
      setTheirPick(null);
      setMyPick(null);
      await fetchOffers();
    } catch (err) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const tabs = [
    { id: 'inbox' as const, label: 'Recebidas', icon: Inbox, count: inbox.filter((o) => o.status === 'pending').length },
    { id: 'sent' as const, label: 'Enviadas', icon: Send, count: sent.filter((o) => o.status === 'pending').length },
    { id: 'new' as const, label: 'Nova troca', icon: ArrowLeftRight, count: 0 },
  ];

  return (
    <div className="pt-6 max-w-2xl mx-auto adaptive-px space-y-6">
      <header className="space-y-1">
        <div className="flex items-center gap-2.5">
          <ArrowLeftRight className="text-brand-accent" size={20} />
          <h1 className="text-xl font-bold text-zinc-100 uppercase tracking-tight">Trocas</h1>
        </div>
        <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest opacity-60">Troque personagens com outros jogadores</p>
      </header>

      <div className="flex gap-2 overflow-x-auto no-scrollbar">
        {tabs.map((item) => (
          <button
            key={item.id}
            onClick={() => {
              window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
              setTab(item.id);
            }}
            className={cn(
              'h-10 px-4 rounded-md flex items-center gap-2 border transition-all text-[10px] font-bold uppercase tracking-widest shrink-0',
              tab === item.id ? 'bg-zinc-100 text-zinc-950 border-zinc-100' : 'bg-zinc-900 border-white/5 text-zinc-500 hover:text-zinc-200',
            )}
          >
            <item.icon size={13} /> {item.label}
            {item.count > 0 && <span className="min-w-4 h-4 px-1 rounded-full text-[9px] font-mono flex items-center justify-center bg-brand-accent text-black">{item.count}</span>}
          </button>
        ))}
      </div>

      <AnimatePresence mode="wait">
        {tab !== 'new' ? (
          <m.div key={tab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="space-y-3">
            {error && !(tab === 'inbox' ? inbox : sent).length ? (
              <ErrorState message={error} onAction={fetchOffers} />
            ) : loading && !offers ? (
              Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-40 w-full rounded-md" />)
            ) : (tab === 'inbox' ? inbox : sent).length > 0 ? (
              (tab === 'inbox' ? inbox : sent).map((offer) => (
                <OfferCard key={offer.id} offer={offer} isReceiver={tab === 'inbox'} busy={responding === offer.id} onRespond={(action) => handleRespond(offer, action)} />
              ))
            ) : (
              <div className="py-16 border border-dashed border-white/5 rounded-lg bg-zinc-950/50">
                <EmptyState
                  icon={tab === 'inbox' ? Inbox : Send}
                  title={tab === 'inbox' ? 'Nenhuma oferta recebida' : 'Nenhuma oferta enviada'}
                  message={tab === 'inbox' ? 'As ofertas de outros jogadores aparecerão aqui.' : 'Crie uma proposta pela aba Nova troca.'}
                />
              </div>
            )}
          </m.div>
        ) : (
          <m.div key="new" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="space-y-6">
            <Card variant="surface" className="p-4 space-y-3">
              <p className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest">1 · ID do usuário</p>
              <div className="flex gap-2">
                <Input icon={Search} placeholder="ID do Telegram" value={targetId} inputMode="numeric" onChange={(e) => setTargetId(e.target.value.replace(/\D/g, ''))} className="h-10" />
                <Button variant="outline" size="sm" className="h-10 px-4" isLoading={targetLoading} onClick={loadTarget} disabled={!targetId.trim() || Number(targetId) === Number(myId)}>Buscar</Button>
              </div>
              {targetError && <p className="text-[10px] font-bold text-red-400 uppercase tracking-widest">{targetError}</p>}
            </Card>

            {targetChars.length > 0 && (
              <Card variant="surface" className="p-4 space-y-3">
                <p className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest">2 · Escolha o personagem que quer receber</p>
                <div className="grid grid-cols-4 sm:grid-cols-5 gap-2 max-h-72 overflow-y-auto">
                  {targetChars.map((char) => <CharThumb key={char.id} char={char} selected={theirPick === char.id} onClick={() => setTheirPick(theirPick === char.id ? null : char.id)} />)}
                </div>
              </Card>
            )}

            {(myLoading || myChars.length > 0) && (
              <Card variant="surface" className="p-4 space-y-3">
                <p className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest">3 · Escolha o personagem que vai entregar</p>
                {myLoading ? (
                  <div className="grid grid-cols-4 gap-2">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="aspect-[2/3] rounded-md" />)}</div>
                ) : (
                  <div className="grid grid-cols-4 sm:grid-cols-5 gap-2 max-h-72 overflow-y-auto">
                    {myChars.map((char) => <CharThumb key={char.id} char={char} selected={myPick === char.id} onClick={() => setMyPick(myPick === char.id ? null : char.id)} />)}
                  </div>
                )}
              </Card>
            )}

            <Button variant="accent" className="w-full h-12" isLoading={submitting} disabled={!theirPick || !myPick || !targetId} onClick={handleSubmit} leftIcon={<Send size={15} />}>
              Enviar oferta de troca
            </Button>
            <p className="text-[9px] text-zinc-600 uppercase tracking-widest text-center leading-relaxed">
              Cada personagem fica reservado enquanto a oferta estiver pendente. A oferta expira em 24 horas.
            </p>
          </m.div>
        )}
      </AnimatePresence>
    </div>
  );
};
