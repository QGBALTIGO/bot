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
import { cleanRarityLabel, cn, FALLBACK_IMAGE, formatNumber } from '../utils';

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

interface HaremPage {
  total: number;
  page: number;
  items: TradeCharacter[];
}

const CharThumb = ({ char, selected, onClick }: {
  char: TradeCharacter;
  selected?: boolean;
  onClick?: () => void;
}) => {
  const [imgError, setImgError] = useState(false);
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'relative rounded-md overflow-hidden aspect-[3/4] border transition-all text-left',
        selected
          ? 'border-brand-accent ring-1 ring-brand-accent/50'
          : 'border-white/5 hover:border-white/15',
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
      <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-transparent to-transparent" />
      <div className="absolute bottom-0 inset-x-0 p-1.5">
        <p className="text-[9px] font-bold text-white uppercase tracking-tight line-clamp-1">
          {char.name}
        </p>
        <p className="text-[8px] font-bold text-zinc-400 uppercase tracking-widest line-clamp-1">
          {cleanRarityLabel(char.rarity) || char.rarity}
        </p>
      </div>
      {selected && (
        <div className="absolute top-1 right-1 w-4 h-4 rounded-full bg-brand-accent text-black flex items-center justify-center">
          <Check size={10} strokeWidth={3} />
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
  <Card variant="default" className="p-4 space-y-3">
    <div className="flex items-center justify-between">
      <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
        {isReceiver ? `From ${offer.sender_name}` : `To ${offer.receiver_name}`}
      </p>
      <span className="text-[8px] font-mono font-bold text-zinc-600 uppercase">
        {offer.status}
      </span>
    </div>
    <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2">
      <div className="space-y-1">
        <p className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest text-center">
          {isReceiver ? 'They give' : 'You give'}
        </p>
        <CharThumb char={isReceiver ? offer.sender_char : offer.receiver_char} />
      </div>
      <ArrowLeftRight size={16} className="text-zinc-600" />
      <div className="space-y-1">
        <p className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest text-center">
          {isReceiver ? 'You give' : 'They give'}
        </p>
        <CharThumb char={isReceiver ? offer.receiver_char : offer.sender_char} />
      </div>
    </div>
    {isReceiver && offer.status === 'pending' && onRespond && (
      <div className="flex gap-2">
        <Button
          variant="accent"
          size="sm"
          className="flex-1"
          isLoading={busy ?? false}
          onClick={() => onRespond('accept')}
        >
          <Check size={12} className="mr-1" /> Accept
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="flex-1"
          disabled={busy}
          onClick={() => onRespond('reject')}
        >
          <X size={12} className="mr-1" /> Reject
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

  const {
    data: offers,
    loading,
    error,
    execute: fetchOffers,
  } = useApi<TradeOffer[]>('/trade/offers');

  const myId = user?.id;
  const inbox = useMemo(
    () => (offers || []).filter((o) => Number(o.receiver_id) === Number(myId)),
    [offers, myId],
  );
  const sent = useMemo(
    () => (offers || []).filter((o) => Number(o.sender_id) === Number(myId)),
    [offers, myId],
  );

  // --- New trade form state ---
  const [targetId, setTargetId] = useState('');
  const [targetName, setTargetName] = useState<string | null>(null);
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
    if (!id) return;
    setTargetLoading(true);
    setTargetError(null);
    setTheirPick(null);
    try {
      const res: HaremPage = await apiFetch(`/harem/${id}?limit=50`);
      setTargetChars(res.items || []);
      setTargetName(res.items?.length ? `Operator #${String(id).slice(-4)}` : null);
      if (!res.items?.length) setTargetError('This operator has no characters to trade.');
    } catch (err) {
      setTargetChars([]);
      setTargetError(getErrorMessage(err));
    } finally {
      setTargetLoading(false);
    }
  }, [targetId]);

  const loadMyChars = useCallback(async () => {
    setMyLoading(true);
    try {
      const res: HaremPage = await apiFetch('/harem?limit=50');
      setMyChars(res.items || []);
    } catch (err) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setMyLoading(false);
    }
  }, [addToast]);

  useEffect(() => {
    if (tab === 'new' && myChars.length === 0) loadMyChars();
  }, [tab, myChars.length, loadMyChars]);

  const handleRespond = async (offer: TradeOffer, action: 'accept' | 'reject') => {
    setResponding(offer.id);
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    try {
      const res = await apiFetch(`/trade/respond/${offer.id}`, {
        method: 'POST',
        body: JSON.stringify({ action }),
      });
      addToast(
        action === 'accept' ? 'Trade accepted — characters swapped.' : 'Trade rejected.',
        'success',
      );
      if (action === 'accept') {
        await refreshUser();
        invalidateQueries(['/harem']);
      }
      await fetchOffers();
      void res;
    } catch (err) {
      addToast(getErrorMessage(err), 'error');
      await fetchOffers();
    } finally {
      setResponding(null);
    }
  };

  const handleSubmit = async () => {
    const receiverId = Number(targetId.trim());
    if (!receiverId || !myPick || !theirPick) return;
    setSubmitting(true);
    try {
      await apiFetch('/trade/offer', {
        method: 'POST',
        body: JSON.stringify({
          receiver_id: receiverId,
          sender_char_id: myPick,
          receiver_char_id: theirPick,
        }),
      });
      addToast('Trade offer sent. It expires in 24h.', 'success');
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

  const TABS = [
    { id: 'inbox' as const, label: 'Inbox', icon: Inbox, count: inbox.length },
    { id: 'sent' as const, label: 'Sent', icon: Send, count: sent.length },
    { id: 'new' as const, label: 'New Trade', icon: ArrowLeftRight, count: 0 },
  ];

  return (
    <div className="pt-6 max-w-2xl mx-auto adaptive-px space-y-6">
      <header className="space-y-1">
        <div className="flex items-center gap-2.5">
          <ArrowLeftRight className="text-brand-accent" size={20} />
          <h1 className="text-xl font-bold text-zinc-100 uppercase tracking-tight">Trading</h1>
        </div>
        <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest opacity-60">
          Swap characters with other players
        </p>
      </header>

      <div className="flex gap-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => {
              window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
              setTab(t.id);
            }}
            className={cn(
              'h-10 px-4 rounded-md flex items-center gap-2 border transition-all text-[10px] font-bold uppercase tracking-widest',
              tab === t.id
                ? 'bg-zinc-100 text-zinc-950 border-zinc-100'
                : 'bg-zinc-900 border-white/5 text-zinc-500 hover:text-zinc-200',
            )}
          >
            <t.icon size={13} />
            {t.label}
            {t.count > 0 && (
              <span
                className={cn(
                  'min-w-4 h-4 px-1 rounded-full text-[9px] font-mono flex items-center justify-center',
                  tab === t.id ? 'bg-zinc-950 text-zinc-100' : 'bg-brand-accent text-black',
                )}
              >
                {t.count}
              </span>
            )}
          </button>
        ))}
      </div>

      <AnimatePresence mode="wait">
        {tab !== 'new' ? (
          <m.div
            key={tab}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="space-y-3"
          >
            {error && !(tab === 'inbox' ? inbox : sent).length ? (
              <ErrorState message={error} onAction={fetchOffers} />
            ) : loading && !offers ? (
              Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-40 w-full rounded-md" />
              ))
            ) : (tab === 'inbox' ? inbox : sent).length > 0 ? (
              (tab === 'inbox' ? inbox : sent).map((offer) => (
                <OfferCard
                  key={offer.id}
                  offer={offer}
                  isReceiver={tab === 'inbox'}
                  busy={responding === offer.id}
                  onRespond={(action) => handleRespond(offer, action)}
                />
              ))
            ) : (
              <div className="py-16 border border-dashed border-white/5 rounded-lg bg-zinc-950/50">
                <EmptyState
                  icon={tab === 'inbox' ? Inbox : Send}
                  title={tab === 'inbox' ? 'No incoming offers' : 'No sent offers'}
                  message={
                    tab === 'inbox'
                      ? 'Trade offers from other players will appear here.'
                      : 'Propose a trade from the New Trade tab.'
                  }
                />
              </div>
            )}
          </m.div>
        ) : (
          <m.div
            key="new"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="space-y-6"
          >
            <Card variant="surface" className="p-4 space-y-3">
              <p className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest">
                1 · Player's Telegram ID
              </p>
              <div className="flex gap-2">
                <Input
                  icon={Search}
                  placeholder="Telegram user ID"
                  value={targetId}
                  inputMode="numeric"
                  onChange={(e) => setTargetId(e.target.value.replace(/\D/g, ''))}
                  className="h-10"
                />
                <Button
                  variant="outline"
                  size="sm"
                  className="h-10 px-4"
                  isLoading={targetLoading}
                  onClick={loadTarget}
                  disabled={!targetId.trim()}
                >
                  Scan
                </Button>
              </div>
              {targetError && (
                <p className="text-[10px] font-bold text-red-400 uppercase tracking-widest">
                  {targetError}
                </p>
              )}
              {targetName && (
                <p className="text-[10px] font-bold text-emerald-500 uppercase tracking-widest">
                  {targetName} · {formatNumber(targetChars.length)} characters found
                </p>
              )}
            </Card>

            {targetChars.length > 0 && (
              <Card variant="surface" className="p-4 space-y-3">
                <p className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest">
                  2 · Pick their character
                </p>
                <div className="grid grid-cols-4 sm:grid-cols-5 gap-2 max-h-64 overflow-y-auto">
                  {targetChars.map((char) => (
                    <CharThumb
                      key={char.id}
                      char={char}
                      selected={theirPick === char.id}
                      onClick={() => setTheirPick(theirPick === char.id ? null : char.id)}
                    />
                  ))}
                </div>
              </Card>
            )}

            {(theirPick || myLoading) && (
              <Card variant="surface" className="p-4 space-y-3">
                <p className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest">
                  3 · Pick your character to offer
                </p>
                {myLoading ? (
                  <div className="grid grid-cols-4 sm:grid-cols-5 gap-2">
                    {Array.from({ length: 10 }).map((_, i) => (
                      <Skeleton key={i} className="aspect-[3/4] rounded-md" />
                    ))}
                  </div>
                ) : myChars.length > 0 ? (
                  <div className="grid grid-cols-4 sm:grid-cols-5 gap-2 max-h-64 overflow-y-auto">
                    {myChars.map((char) => (
                      <CharThumb
                        key={char.id}
                        char={char}
                        selected={myPick === char.id}
                        onClick={() => setMyPick(myPick === char.id ? null : char.id)}
                      />
                    ))}
                  </div>
                ) : (
                  <p className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest">
                    Your archive is empty.
                  </p>
                )}
              </Card>
            )}

            <Button
              variant="accent"
              className="w-full h-12"
              disabled={!theirPick || !myPick || !targetId.trim()}
              isLoading={submitting}
              onClick={handleSubmit}
            >
              <Send size={14} className="mr-2" /> Send Trade Offer
            </Button>
          </m.div>
        )}
      </AnimatePresence>
    </div>
  );
};
