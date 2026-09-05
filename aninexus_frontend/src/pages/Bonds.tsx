import { Check, Heart, Link2, Send, UserPlus, X } from 'lucide-react';
import { useMemo, useState } from 'react';
import { apiFetch, getErrorMessage, invalidateQueries } from '../api/client';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { Input } from '../components/ui/Input';
import { Skeleton } from '../components/ui/Skeleton';
import { useToast } from '../components/ui/Toast';
import { useApi } from '../hooks/useApi';

interface Bond {
  bond_id: number;
  partner_id: number;
  partner_name: string;
  partner_avatar?: string | null;
  married_at?: string | null;
  created_at?: string | null;
  status: string;
}

interface BondInvite {
  invite_id: number;
  direction: 'incoming' | 'outgoing';
  inviter_id: number;
  invitee_id: number;
  other_user_id: number;
  other_user_name: string;
  status: string;
  created_at?: string | null;
  expires_at?: string | null;
}

export const Bonds = () => {
  const { addToast } = useToast();
  const [targetId, setTargetId] = useState('');
  const [sending, setSending] = useState(false);
  const [responding, setResponding] = useState<number | null>(null);
  const [removing, setRemoving] = useState(false);

  const {
    data: bond,
    loading: bondLoading,
    error: bondError,
    execute: reloadBond,
  } = useApi<Bond | null>('/social/bond');
  const {
    data: invites,
    loading: invitesLoading,
    error: invitesError,
    execute: reloadInvites,
  } = useApi<BondInvite[]>('/social/bond/invites', { initialData: [] });

  const incoming = useMemo(
    () => (invites || []).filter((invite) => invite.direction === 'incoming'),
    [invites],
  );
  const outgoing = useMemo(
    () => (invites || []).filter((invite) => invite.direction === 'outgoing'),
    [invites],
  );

  const reload = async () => {
    await Promise.allSettled([reloadBond(), reloadInvites()]);
    invalidateQueries(['/social/marriage', '/social/bond', '/social/bond/invites']);
  };

  const sendInvite = async () => {
    const target = Number(targetId.trim());
    if (!Number.isInteger(target) || target <= 0 || sending) return;
    setSending(true);
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    try {
      const result = await apiFetch('/social/bond/invite', {
        method: 'POST',
        body: JSON.stringify({ target_user_id: target }),
      });
      addToast(result?.already_pending ? 'Esse convite já estava pendente.' : 'Convite de vínculo enviado.', 'success');
      setTargetId('');
      await reload();
    } catch (error) {
      addToast(getErrorMessage(error), 'error');
    } finally {
      setSending(false);
    }
  };

  const respond = async (inviteId: number, action: 'accept' | 'reject') => {
    if (responding) return;
    setResponding(inviteId);
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    try {
      await apiFetch(`/social/bond/invites/${inviteId}/respond`, {
        method: 'POST',
        body: JSON.stringify({ action }),
      });
      addToast(action === 'accept' ? 'Vínculo criado.' : 'Convite recusado.', 'success');
      await reload();
    } catch (error) {
      addToast(getErrorMessage(error), 'error');
    } finally {
      setResponding(null);
    }
  };

  const removeBond = async () => {
    if (removing) return;
    const execute = async () => {
      setRemoving(true);
      try {
        await apiFetch('/social/bond', { method: 'DELETE' });
        addToast('Vínculo encerrado.', 'success');
        await reload();
      } catch (error) {
        addToast(getErrorMessage(error), 'error');
      } finally {
        setRemoving(false);
      }
    };

    const tg = window.Telegram?.WebApp;
    if (tg?.showConfirm) {
      tg.showConfirm('Encerrar este vínculo?', (confirmed) => {
        if (confirmed) void execute();
      });
    } else if (window.confirm('Encerrar este vínculo?')) {
      await execute();
    }
  };

  if ((bondLoading && bond === undefined) || (invitesLoading && invites === undefined)) {
    return (
      <div className="pt-6 max-w-2xl mx-auto adaptive-px space-y-6">
        <Skeleton className="h-24 rounded-lg" />
        <Skeleton className="h-44 rounded-lg" />
        <Skeleton className="h-28 rounded-lg" />
      </div>
    );
  }

  if ((bondError && bond === undefined) || (invitesError && invites === undefined)) {
    return (
      <div className="pt-6 max-w-2xl mx-auto adaptive-px">
        <ErrorState message={bondError || invitesError || 'Não foi possível carregar os vínculos.'} onAction={reload} />
      </div>
    );
  }

  return (
    <div className="pt-6 max-w-2xl mx-auto adaptive-px space-y-8 select-none">
      <header className="space-y-1">
        <div className="flex items-center gap-2.5">
          <Heart size={21} className="text-pink-400" />
          <h1 className="text-xl font-bold text-zinc-100 uppercase tracking-tight">Vínculos</h1>
        </div>
        <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest opacity-70">
          Crie um vínculo social com outro usuário do AniNexus
        </p>
      </header>

      {bond ? (
        <Card variant="surface" className="p-6 space-y-5 border-pink-500/15">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-md bg-pink-500/10 border border-pink-500/20 flex items-center justify-center shrink-0">
              <Heart size={21} className="text-pink-400" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest mb-1">Vínculo ativo</p>
              <h2 className="text-lg font-bold text-zinc-100 uppercase tracking-tight truncate">{bond.partner_name}</h2>
              <p className="text-[9px] font-mono text-zinc-600 mt-1">ID {bond.partner_id}</p>
            </div>
            <Badge variant="success" size="xs" icon={Link2}>ATIVO</Badge>
          </div>

          {bond.created_at && (
            <p className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest">
              Desde {new Date(bond.created_at).toLocaleDateString('pt-BR')}
            </p>
          )}

          <Button variant="outline" className="w-full" onClick={removeBond} isLoading={removing}>
            Encerrar vínculo
          </Button>
        </Card>
      ) : (
        <Card variant="surface" className="p-6 space-y-4">
          <div className="flex items-center gap-3">
            <UserPlus size={18} className="text-brand-accent" />
            <div>
              <h2 className="text-sm font-bold text-zinc-100 uppercase">Enviar convite</h2>
              <p className="text-[9px] text-zinc-600 uppercase tracking-widest mt-0.5">Use o ID do Telegram da pessoa</p>
            </div>
          </div>
          <div className="flex gap-2">
            <Input
              placeholder="ID do Telegram"
              inputMode="numeric"
              value={targetId}
              onChange={(event) => setTargetId(event.target.value.replace(/\D/g, ''))}
            />
            <Button
              variant="accent"
              className="shrink-0 px-5"
              onClick={sendInvite}
              isLoading={sending}
              disabled={!targetId.trim()}
            >
              <Send size={14} />
            </Button>
          </div>
          <p className="text-[9px] text-zinc-600 leading-relaxed">
            O vínculo só é criado quando a outra pessoa aceita. Cada usuário pode manter apenas um vínculo ativo.
          </p>
        </Card>
      )}

      <section className="space-y-4">
        <div className="flex items-center justify-between px-1">
          <h2 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Convites recebidos</h2>
          <Badge variant="secondary" size="xs">{incoming.length}</Badge>
        </div>
        {incoming.length > 0 ? (
          <div className="space-y-2">
            {incoming.map((invite) => (
              <Card key={invite.invite_id} variant="default" className="p-4 flex items-center gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-bold text-zinc-100 uppercase truncate">{invite.other_user_name}</p>
                  <p className="text-[9px] font-mono text-zinc-600 mt-1">ID {invite.other_user_id}</p>
                </div>
                <Button
                  variant="accent"
                  size="sm"
                  onClick={() => respond(invite.invite_id, 'accept')}
                  isLoading={responding === invite.invite_id}
                  disabled={Boolean(responding)}
                >
                  <Check size={13} /> Aceitar
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => respond(invite.invite_id, 'reject')}
                  disabled={Boolean(responding)}
                >
                  <X size={13} />
                </Button>
              </Card>
            ))}
          </div>
        ) : (
          <EmptyState icon={Heart} title="Nenhum convite" message="Convites de vínculo recebidos aparecem aqui." />
        )}
      </section>

      {outgoing.length > 0 && (
        <section className="space-y-4">
          <div className="flex items-center justify-between px-1">
            <h2 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Aguardando resposta</h2>
            <Badge variant="secondary" size="xs">{outgoing.length}</Badge>
          </div>
          <div className="space-y-2">
            {outgoing.map((invite) => (
              <Card key={invite.invite_id} variant="default" className="p-4 flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-sm font-bold text-zinc-100 uppercase truncate">{invite.other_user_name}</p>
                  <p className="text-[9px] font-mono text-zinc-600 mt-1">ID {invite.other_user_id}</p>
                </div>
                <Badge variant="secondary" size="xs">PENDENTE</Badge>
              </Card>
            ))}
          </div>
        </section>
      )}
    </div>
  );
};
