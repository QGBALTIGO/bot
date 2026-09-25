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
import { nativeParams } from '../native/navigation';
import { Dialog } from '../native/ui';
import { Picker } from '../features/collecting/Picker';
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
  revision?: number;
  sender_confirmed?: boolean;
  receiver_confirmed?: boolean;
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

const CharThumb = ({
  char,
  selected,
  onClick,
}: {
  char: TradeCharacter;
  selected?: boolean;
  onClick?: () => void;
}) => {
  const [imgError, setImgError] = useState(false);
  return (
    <button
      type="button"
      onClick={onClick}
      style={{ aspectRatio: '2 / 3' }}
      className={cn(
        'relative w-full min-w-0 rounded-md overflow-hidden border transition-all text-left',
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
      <div className="absolute inset-0 bg-gradient-to-t from-black/95 via-transparent to-transparent" />
      <div className="absolute bottom-0 inset-x-0 p-2">
        <p className="text-[9px] font-bold text-white uppercase tracking-tight line-clamp-1">
          {char.name}
        </p>
        <p className="text-[8px] font-bold text-zinc-400 uppercase tracking-widest line-clamp-1">
          {cleanRarityLabel(char.rarity) || char.rarity}
        </p>
      </div>
      {Number(char.count || 0) > 1 && (
        <span className="absolute top-1 left-1 px-1.5 py-0.5 rounded bg-black/70 text-[8px] font-mono font-bold text-white">
          ×{char.count}
        </span>
      )}
      {selected && (
        <div className="absolute top-1 right-1 w-5 h-5 rounded-full bg-brand-accent text-black flex items-center justify-center">
          <Check size={11} strokeWidth={3} />
        </div>
      )}
    </button>
  );
};

const OfferCard = ({
  offer,
  isReceiver,
  onRespond,
  onEdit,
  busy,
}: {
  offer: TradeOffer;
  isReceiver: boolean;
  onRespond?: (action: 'accept' | 'reject') => void;
  onEdit?: () => void;
  busy?: boolean;
}) => (
  <Card variant="default" className="p-4 space-y-4">
    <div className="flex items-center justify-between gap-3">
      <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest truncate">
        {isReceiver ? `De ${offer.sender_name}` : `Para ${offer.receiver_name}`}
      </p>
      <span className="text-[8px] font-mono font-bold text-zinc-600 uppercase shrink-0">
        {statusLabel(offer.status)}
      </span>
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
    <p className="text-xs text-zinc-400">
      Proposta v{offer.revision || 1} ·{' '}
      {offer.sender_confirmed ? 'Remetente confirmou' : 'Remetente precisa confirmar'} ·{' '}
      {offer.receiver_confirmed ? 'Destinatário confirmou' : 'Destinatário precisa confirmar'}
    </p>
    {offer.status === 'pending' && onRespond && (
      <div className="grid grid-cols-2 gap-2">
        <Button
          variant="accent"
          size="sm"
          className="h-10"
          isLoading={busy ?? false}
          disabled={Boolean(isReceiver ? offer.receiver_confirmed : offer.sender_confirmed)}
          onClick={() => onRespond('accept')}
        >
          <Check size={13} className="mr-1.5" />{' '}
          {(isReceiver ? offer.receiver_confirmed : offer.sender_confirmed)
            ? 'Confirmado'
            : 'Confirmar'}
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="h-10"
          disabled={busy}
          onClick={() => onRespond('reject')}
        >
          <X size={13} className="mr-1.5" /> Recusar
        </Button>
      </div>
    )}
    {offer.status === 'pending' && (
      <Button variant="secondary" size="sm" disabled={busy} onClick={onEdit}>
        Alterar minha oferta
      </Button>
    )}
  </Card>
);

export const Trading = () => {
  const { user, refreshUser } = useUser();
  const { addToast } = useToast();
  const [tab, setTab] = useState<'inbox' | 'sent' | 'new'>(
    nativeParams().get('target_user_id') ? 'new' : 'inbox',
  );
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

  const [targetId, setTargetId] = useState(nativeParams().get('target_user_id') || '');
  const [editOffer, setEditOffer] = useState<TradeOffer | null>(null);
  const [replacement, setReplacement] = useState<number | null>(null);
  const [editBusy, setEditBusy] = useState(false);
  const [confirmOffer, setConfirmOffer] = useState<TradeOffer | null>(null);
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
      if (!res.items?.length)
        setTargetError('Esse usuário não tem personagens disponíveis para troca.');
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
    if (responding) return;
    setResponding(offer.id);
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    try {
      const result = await apiFetch(`/trade/respond/${offer.id}`, {
        method: 'POST',
        body: JSON.stringify({ action, expected_revision: offer.revision || 1 }),
      });
      setConfirmOffer(null);
      addToast(
        action === 'accept'
          ? result.status === 'pending'
            ? 'Confirmação registrada. Falta a outra pessoa confirmar.'
            : 'Troca concluída.'
          : 'Troca recusada.',
        'success',
      );
      if (action === 'accept' && result.status !== 'pending') {
        void refreshUser();
        invalidateQueries(['/harem']);
      }
      await fetchOffers();
    } catch (err) {
      setConfirmOffer(null);
      addToast(getErrorMessage(err), 'error');
      await fetchOffers();
    } finally {
      setResponding(null);
    }
  };

  const saveRevision = async () => {
    if (!editOffer || !replacement || editBusy) return;
    setEditBusy(true);
    try {
      await apiFetch(`/trade/offers/${editOffer.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          expected_revision: editOffer.revision || 1,
          character_id: replacement,
        }),
      });
      setEditOffer(null);
      setReplacement(null);
      addToast('Proposta alterada. As duas pessoas precisam confirmar novamente.', 'success');
      await fetchOffers();
    } catch (err) {
      addToast(getErrorMessage(err), 'error');
      setEditOffer(null);
      await fetchOffers();
    } finally {
      setEditBusy(false);
    }
  };

  const handleSubmit = async () => {
    const receiverId = Number(targetId.trim());
    if (!receiverId || !myPick || !theirPick || submitting) return;
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
    {
      id: 'inbox' as const,
      label: 'Recebidas',
      icon: Inbox,
      count: inbox.filter((o) => o.status === 'pending').length,
    },
    {
      id: 'sent' as const,
      label: 'Enviadas',
      icon: Send,
      count: sent.filter((o) => o.status === 'pending').length,
    },
    { id: 'new' as const, label: 'Nova troca', icon: ArrowLeftRight, count: 0 },
  ];

  return (
    <div className="pt-6 max-w-2xl mx-auto adaptive-px space-y-6">
      <header className="space-y-1">
        <div className="flex items-center gap-2.5">
          <ArrowLeftRight className="text-brand-accent" size={20} />
          <h1 className="text-xl font-bold text-zinc-100 uppercase tracking-tight">Trocas</h1>
        </div>
        <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest opacity-60">
          Troque personagens com outros jogadores
        </p>
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
              tab === item.id
                ? 'bg-zinc-100 text-zinc-950 border-zinc-100'
                : 'bg-zinc-900 border-white/5 text-zinc-500 hover:text-zinc-200',
            )}
          >
            <item.icon size={13} /> {item.label}
            {item.count > 0 && (
              <span className="min-w-4 h-4 px-1 rounded-full text-[9px] font-mono flex items-center justify-center bg-brand-accent text-black">
                {item.count}
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
                  onEdit={() => {
                    setReplacement(null);
                    setEditOffer(offer);
                  }}
                  onRespond={(action) =>
                    action === 'accept' ? setConfirmOffer(offer) : handleRespond(offer, action)
                  }
                />
              ))
            ) : (
              <div className="py-16 border border-dashed border-white/5 rounded-lg bg-zinc-950/50">
                <EmptyState
                  icon={tab === 'inbox' ? Inbox : Send}
                  title={tab === 'inbox' ? 'Nenhuma oferta recebida' : 'Nenhuma oferta enviada'}
                  message={
                    tab === 'inbox'
                      ? 'As ofertas de outros jogadores aparecerão aqui.'
                      : 'Crie uma proposta pela aba Nova troca.'
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
                1 · ID do usuário
              </p>
              <div className="flex gap-2">
                <Input
                  icon={Search}
                  placeholder="ID do Telegram"
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
                  disabled={!targetId.trim() || Number(targetId) === Number(myId)}
                >
                  Buscar
                </Button>
              </div>
              {targetError && (
                <p className="text-[10px] font-bold text-red-400 uppercase tracking-widest">
                  {targetError}
                </p>
              )}
            </Card>

            {targetChars.length > 0 && (
              <Card variant="surface" className="p-4 space-y-3">
                <p className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest">
                  2 · Escolha o personagem que quer receber
                </p>
                <div className="grid grid-cols-4 sm:grid-cols-5 gap-2 max-h-72 overflow-y-auto">
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

            {targetChars.length > 0 && (myLoading || myChars.length > 0) && (
              <Card variant="surface" className="p-4 space-y-3">
                <p className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest">
                  3 · Escolha o personagem que vai entregar
                </p>
                {myLoading ? (
                  <div className="grid grid-cols-4 gap-2">
                    {Array.from({ length: 8 }).map((_, i) => (
                      <Skeleton key={i} className="h-36 rounded-md" />
                    ))}
                  </div>
                ) : (
                  <div className="grid grid-cols-4 sm:grid-cols-5 gap-2 max-h-72 overflow-y-auto">
                    {myChars.map((char) => (
                      <CharThumb
                        key={char.id}
                        char={char}
                        selected={myPick === char.id}
                        onClick={() => setMyPick(myPick === char.id ? null : char.id)}
                      />
                    ))}
                  </div>
                )}
              </Card>
            )}

            <Button
              variant="accent"
              className="w-full h-12"
              isLoading={submitting}
              disabled={!theirPick || !myPick || !targetId}
              onClick={handleSubmit}
              leftIcon={<Send size={15} />}
            >
              Enviar oferta de troca
            </Button>
            <p className="text-[9px] text-zinc-600 uppercase tracking-widest text-center leading-relaxed">
              Cada personagem fica reservado enquanto a oferta estiver pendente. A oferta expira em
              24 horas.
            </p>
          </m.div>
        )}
      </AnimatePresence>
      {editOffer && (
        <Dialog
          title={`Alterar proposta v${editOffer.revision || 1}`}
          onClose={() => setEditOffer(null)}
          busy={editBusy}
        >
          <p className="text-sm text-zinc-400">
            Você pode substituir somente o personagem que entrega. Os dois aceites serão cancelados.
          </p>
          <Picker onSelect={(card) => setReplacement(card.id)} />
          {replacement && (
            <p className="text-xs text-brand-accent">Personagem selecionado: {replacement}</p>
          )}
          <Button className="w-full" disabled={!replacement || editBusy} onClick={saveRevision}>
            Salvar nova proposta
          </Button>
        </Dialog>
      )}
      {confirmOffer && (
        <Dialog
          title={`Confirmar proposta v${confirmOffer.revision || 1}`}
          onClose={() => setConfirmOffer(null)}
          busy={Boolean(responding)}
        >
          <p className="text-sm text-zinc-300">
            Você entrega{' '}
            <strong>
              {Number(confirmOffer.sender_id) === Number(myId)
                ? confirmOffer.sender_char.name
                : confirmOffer.receiver_char.name}
            </strong>{' '}
            e recebe{' '}
            <strong>
              {Number(confirmOffer.sender_id) === Number(myId)
                ? confirmOffer.receiver_char.name
                : confirmOffer.sender_char.name}
            </strong>
            .
          </p>
          <p className="text-xs text-zinc-500">
            Se a oferta mudar, esta confirmação deixa de valer. A troca só conclui com os dois
            aceites da mesma versão.
          </p>
          <Button
            className="w-full"
            disabled={Boolean(responding)}
            onClick={() => handleRespond(confirmOffer, 'accept')}
          >
            Confirmar esta versão
          </Button>
        </Dialog>
      )}
    </div>
  );
};
