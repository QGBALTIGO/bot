import { useQueryClient } from '@tanstack/react-query';
import { Bell, ExternalLink, Link2, RefreshCw, Settings2, Shield, Trash2, Unlink } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { apiFetch, getErrorMessage, setSessionToken } from '../api/client';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { useToast } from '../components/ui/Toast';
import { sourcePost, useSourceAction, useSourceQuery } from './api';
import { navigateNative } from './navigation';
import { Dialog, Field, fieldClass, NativePage, QueryFeedback } from './ui';
import { FavoriteSettings } from './FavoriteSettings';
import { NicknameForm } from './ShopExtras';

export function Settings() {
  const query = useSourceQuery('/api/menu/profile');
  const aninexus = useSourceQuery<{ linked: boolean; linkedAt?: string | null }>(
    '/api/v1_7b82/integrations/aninexus/status',
  );
  const profile = query.data?.profile;
  const { pending, run } = useSourceAction(),
    { addToast } = useToast(),
    cache = useQueryClient();
  const [confirm, setConfirm] = useState(false),
    [typed, setTyped] = useState(''),
    [deleting, setDeleting] = useState(false),
    [deleted, setDeleted] = useState(false);
  const deleteLock = useRef(false);
  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState === 'visible') void aninexus.refetch();
    };
    document.addEventListener('visibilitychange', refresh);
    window.addEventListener('focus', refresh);
    return () => {
      document.removeEventListener('visibilitychange', refresh);
      window.removeEventListener('focus', refresh);
    };
  }, [aninexus.refetch]);
  const connectAniNexus = async () => {
    const result = await run<{ url: string; expiresInSeconds: number }>(
      'aninexus-link',
      () => apiFetch('/integrations/aninexus/link-token', { method: 'POST' }),
    );
    if (!result?.url) return;
    const tg = window.Telegram?.WebApp;
    if (tg?.openLink) tg.openLink(result.url);
    else window.open(result.url, '_blank', 'noopener,noreferrer');
  };
  const unlinkAniNexus = async () => {
    const result = await run<{ ok: boolean }>(
      'aninexus-unlink',
      () => apiFetch('/integrations/aninexus/link', { method: 'DELETE' }),
      'Conta AniNexus desconectada.',
    );
    if (result?.ok) void aninexus.refetch();
  };
  const save = (key: string, body: Record<string, unknown>) =>
    run(key, () => sourcePost(`/api/menu/${key}`, body), 'Preferência atualizada.');
  const remove = async () => {
    if (typed !== 'EXCLUIR' || deleteLock.current) return;
    deleteLock.current = true;
    setDeleting(true);
    try {
      await sourcePost('/api/menu/delete-account');
      setConfirm(false);
      setDeleted(true);
      setSessionToken(null);
      cache.clear();
      window.dispatchEvent(new Event('source:account-deleted'));
    } catch (error) {
      addToast(getErrorMessage(error), 'error');
    } finally {
      deleteLock.current = false;
      setDeleting(false);
    }
  };
  if (deleted)
    return (
      <NativePage title="Conta excluída" subtitle="Seus dados foram removidos" icon={Trash2}>
        <Card className="p-5 space-y-4">
          <p className="text-sm text-zinc-400">
            A conta foi excluída. Feche a MiniApp para encerrar esta sessão.
          </p>
          <Button onClick={() => window.Telegram?.WebApp?.close?.()}>Fechar MiniApp</Button>
        </Card>
      </NativePage>
    );
  return (
    <NativePage
      title="Configurações"
      subtitle="Perfil, preferências e privacidade"
      icon={Settings2}
    >
      <QueryFeedback loading={query.isPending} error={query.error} retry={query.refetch} />
      {profile && (
        <>
          <Card className="p-5 space-y-3">
            <h2 className="text-sm font-bold text-zinc-100">{profile.display_name}</h2>
            <p className="text-xs text-zinc-500">Nickname: {profile.nickname || 'Não definido'}</p>
            {profile.nickname && (
              <Button
                variant="secondary"
                onClick={() => navigateNative('shop', { section: 'nickname' })}
              >
                Alterar nickname
              </Button>
            )}
          </Card>
          {!profile.nickname && <NicknameForm />}
          <FavoriteSettings current={profile.favorite} />
          <Card className="p-5 space-y-4 border-brand-accent/15">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0 space-y-1">
                <div className="flex items-center gap-2">
                  <Link2 size={15} className="text-brand-accent" />
                  <h2 className="text-sm font-bold text-zinc-100">AniNexus</h2>
                </div>
                <p className="text-xs text-zinc-500 leading-relaxed">
                  Conecte sua conta para levar seu perfil Source ao AniNexus. Sua senha e sua sessão do Telegram nunca são compartilhadas.
                </p>
              </div>
              <span className={`shrink-0 text-[9px] font-bold uppercase tracking-widest px-2 py-1 rounded border ${
                aninexus.data?.linked
                  ? 'text-emerald-400 border-emerald-500/20 bg-emerald-500/5'
                  : 'text-zinc-500 border-white/5 bg-zinc-900'
              }`}>
                {aninexus.isPending ? 'Verificando' : aninexus.data?.linked ? 'Conectado' : 'Não conectado'}
              </span>
            </div>
            {aninexus.data?.linked && aninexus.data.linkedAt && (
              <p className="text-[10px] text-zinc-600">
                Vinculado em {new Date(aninexus.data.linkedAt).toLocaleDateString('pt-BR')}.
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                leftIcon={<ExternalLink size={13} />}
                disabled={Boolean(pending)}
                isLoading={pending === 'aninexus-link'}
                onClick={connectAniNexus}
              >
                {aninexus.data?.linked ? 'Reconectar AniNexus' : 'Conectar AniNexus'}
              </Button>
              <Button
                size="sm"
                variant="secondary"
                leftIcon={<RefreshCw size={13} />}
                disabled={Boolean(pending) || aninexus.isFetching}
                onClick={() => void aninexus.refetch()}
              >
                Atualizar status
              </Button>
              {aninexus.data?.linked && (
                <Button
                  size="sm"
                  variant="secondary"
                  leftIcon={<Unlink size={13} />}
                  disabled={Boolean(pending)}
                  isLoading={pending === 'aninexus-unlink'}
                  onClick={unlinkAniNexus}
                >
                  Desconectar
                </Button>
              )}
            </div>
          </Card>
          <Card className="p-5 space-y-5">
            <Field label="País">
              <select
                aria-label="País"
                className={fieldClass}
                disabled={Boolean(pending)}
                value={profile.country_code || 'BR'}
                onChange={(e) => save('country', { country_code: e.target.value })}
              >
                {(query.data?.countries || []).map((c: any) => (
                  <option key={c.code} value={c.code}>
                    {c.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Idioma">
              <select
                aria-label="Idioma"
                className={fieldClass}
                disabled={Boolean(pending)}
                value={profile.language || 'pt'}
                onChange={(e) => save('language', { language: e.target.value })}
              >
                {(query.data?.languages || []).map((l: any) => (
                  <option key={l.code} value={l.code}>
                    {l.name}
                  </option>
                ))}
              </select>
            </Field>
            {[
              {
                key: 'privacy',
                label: 'Perfil privado',
                value: Boolean(profile.private_profile),
                icon: Shield,
              },
              {
                key: 'notifications',
                label: 'Notificações',
                value: Boolean(profile.notifications_enabled),
                icon: Bell,
              },
            ].map(({ key, label, value, icon: Icon }) => (
              <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3" key={key}>
                <span className="text-xs text-zinc-300 flex items-center gap-2">
                  <Icon size={14} />
                  {label}
                </span>
                <Button
                  variant={value ? 'primary' : 'secondary'}
                  size="sm"
                  role="switch"
                  aria-label={label}
                  aria-checked={value}
                  disabled={Boolean(pending)}
                  isLoading={pending === key}
                  onClick={() => save(key, { value: !value })}
                >
                  {value ? 'Ativado' : 'Desativado'}
                </Button>
              </div>
            ))}
          </Card>
          <Button variant="secondary" onClick={() => navigateNative('terms')}>
            Termos de uso e privacidade
          </Button>
          <Card className="p-5 border-red-500/20 space-y-4">
            <h2 className="text-xs font-bold text-red-400 uppercase">Excluir conta</h2>
            <p className="text-sm text-zinc-500">
              Esta ação remove seus dados e sua coleção. Não pode ser desfeita.
            </p>
            <Button
              variant="danger"
              leftIcon={<Trash2 size={14} />}
              onClick={() => {
                setTyped('');
                setConfirm(true);
              }}
            >
              Excluir minha conta
            </Button>
          </Card>
        </>
      )}
      {confirm && (
        <Dialog
          title="Excluir conta permanentemente"
          onClose={() => setConfirm(false)}
          busy={deleting}
        >
          <p className="text-sm text-zinc-400">
            Você perderá sua coleção e seus dados. Digite EXCLUIR para confirmar.
          </p>
          <Input
            aria-label="Digite EXCLUIR"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            autoComplete="off"
          />
          <Button
            variant="danger"
            className="w-full"
            disabled={typed !== 'EXCLUIR' || deleting}
            isLoading={deleting}
            onClick={remove}
          >
            Excluir definitivamente
          </Button>
          <Button
            variant="secondary"
            className="w-full"
            disabled={deleting}
            onClick={() => setConfirm(false)}
          >
            Cancelar
          </Button>
        </Dialog>
      )}
    </NativePage>
  );
}
