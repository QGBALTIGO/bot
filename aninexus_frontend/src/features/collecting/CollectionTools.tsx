import {
  ArrowLeftRight,
  Heart,
  LockKeyhole,
  Search,
  Share2,
  SlidersHorizontal,
  Unlock,
} from 'lucide-react';
import { useState } from 'react';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Card } from '../../components/ui/Card';
import { useDebounced } from '../../native/api';
import { nativeParams, navigateNative } from '../../native/navigation';
import { Choices, Dialog, NativePage, Poster, PosterGrid, QueryFeedback } from '../../native/ui';
import { type CollectionCard, type CardPage, useFeatureQuery, useFeatureAction } from './api';

interface Settings {
  discoverable: boolean;
  share_inline: boolean;
  preserve_last: boolean;
  can_manage_events: boolean;
}
interface Match {
  user_id: number;
  name: string;
  receive: CollectionCard[];
  give: CollectionCard[];
}
export function CollectionTools() {
  const initial = nativeParams().get('section') || nativeParams().get('view');
  const [view, setView] = useState(
    nativeParams().get('character_id')
      ? 'owned'
      : initial === 'protected'
        ? 'protected'
        : initial === 'matches'
          ? 'matches'
          : 'wishes',
  );
  const [search, setSearch] = useState(nativeParams().get('character_id') || ''),
    [page, setPage] = useState(0),
    [preferences, setPreferences] = useState(false);
  const [preferenceDraft, setPreferenceDraft] = useState<Partial<Settings>>({});
  const [unlock, setUnlock] = useState<CollectionCard | null>(null);
  const q = useDebounced(search),
    settings = useFeatureQuery<Settings>('/settings');
  const list = useFeatureQuery<CardPage>(
    `/characters?view=${view === 'matches' ? 'wishes' : view}&q=${encodeURIComponent(q)}&offset=${page * 24}`,
    view !== 'matches',
  );
  const matches = useFeatureQuery<{ items: Match[]; opt_in_required: boolean; has_more: boolean }>(
    `/matches?offset=${page * 10}`,
    view === 'matches',
  );
  const { perform, pending } = useFeatureAction();
  const protect = async (c: CollectionCard, enabled: boolean) => {
    const result = await perform(
      `/characters/${c.id}/protection`,
      { enabled },
      { method: 'PUT', success: enabled ? 'Personagem protegido.' : 'Cadeado removido.' },
    );
    if (result) setUnlock(null);
  };
  const current = view === 'matches' ? matches : list;
  return (
    <NativePage
      title="Desejos e cofre"
      subtitle="Sua coleção, suas escolhas. Nada é compartilhado sem sua autorização."
      icon={Heart}
    >
      <div className="flex flex-wrap gap-2">
        <Button
          variant="secondary"
          size="sm"
          leftIcon={<SlidersHorizontal size={14} />}
          onClick={() => setPreferences(true)}
        >
          Preferências
        </Button>
        <Button variant="ghost" size="sm" onClick={() => navigateNative('album')}>
          Abrir meu álbum
        </Button>
      </div>
      <Choices
        wrap
        value={view}
        items={[
          ['wishes', 'Desejos'],
          ['catalog', 'Encontrar'],
          ['protected', 'Cofre'],
          ['duplicates', 'Duplicatas'],
          ['matches', 'Combinações'],
        ]}
        onChange={(v) => {
          setView(v);
          setPage(0);
          setSearch('');
        }}
      />
      {view !== 'matches' && (
        <Input
          icon={Search}
          value={search}
          maxLength={80}
          aria-label="Buscar personagem"
          placeholder="Nome, obra ou ID..."
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(0);
          }}
        />
      )}
      <QueryFeedback
        loading={current.isPending}
        error={current.error}
        retry={current.refetch}
        empty={false}
      />
      {view === 'matches' ? (
        <>
          {matches.data?.opt_in_required && (
            <Card className="p-5 space-y-3">
              <p className="text-sm text-zinc-300">
                Ative a descoberta nas preferências e mantenha o perfil público para encontrar
                trocas compatíveis.
              </p>
              <Button onClick={() => setPreferences(true)}>Gerenciar privacidade</Button>
            </Card>
          )}
          {matches.data?.items.map((match) => (
            <Card key={match.user_id} className="p-4 space-y-4">
              <h2 className="text-sm font-bold text-zinc-100 break-words">{match.name}</h2>
              <p className="text-xs text-zinc-400">
                Esta pessoa procura suas duplicatas e tem personagens que você deseja.
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <p className="text-xs text-zinc-500 mb-2">Você pode receber</p>
                  {match.receive.map((c) => (
                    <p key={c.id} className="text-xs text-zinc-200 break-words">
                      {c.name}
                    </p>
                  ))}
                </div>
                <div>
                  <p className="text-xs text-zinc-500 mb-2">Você pode oferecer</p>
                  {match.give.map((c) => (
                    <p key={c.id} className="text-xs text-zinc-200 break-words">
                      {c.name}
                    </p>
                  ))}
                </div>
              </div>
              <Button
                size="sm"
                leftIcon={<ArrowLeftRight size={14} />}
                onClick={() => navigateNative('trading', { target_user_id: match.user_id })}
              >
                Revisar uma proposta
              </Button>
            </Card>
          ))}
          {matches.data && !matches.data.opt_in_required && !matches.data.items.length && (
            <p className="text-sm text-zinc-500">
              Nenhuma combinação por enquanto. Acrescente desejos e volte depois.
            </p>
          )}
        </>
      ) : (
        <>
          <PosterGrid>
            {list.data?.items.map((c) => (
              <Poster key={c.id} title={c.name} subtitle={c.anime} src={c.image}>
                <div className="space-y-2">
                  <p className="text-[10px] text-zinc-500">
                    {c.quantity} cópia(s){c.favorite ? ' · Favorito' : ''}
                    {c.reserved ? ' · Reservado' : ''}
                  </p>
                  <Button
                    className="w-full"
                    size="sm"
                    variant={c.wished ? 'secondary' : 'primary'}
                    disabled={pending}
                    leftIcon={<Heart size={13} />}
                    onClick={() =>
                      void perform(
                        '/wishes',
                        { ids: [c.id], enabled: !c.wished },
                        { success: c.wished ? 'Removido dos desejos.' : 'Adicionado aos desejos.' },
                      )
                    }
                  >
                    {c.wished ? 'Remover desejo' : 'Quero este'}
                  </Button>
                  {c.quantity > 0 && (
                    <Button
                      className="w-full"
                      size="sm"
                      variant="outline"
                      disabled={pending || Boolean(c.reserved)}
                      leftIcon={c.protected ? <Unlock size={13} /> : <LockKeyhole size={13} />}
                      onClick={() => (c.protected ? setUnlock(c) : void protect(c, true))}
                    >
                      {c.protected ? 'Desbloquear' : 'Proteger'}
                    </Button>
                  )}
                  {c.quantity > 0 && settings.data?.share_inline && (
                    <Button
                      className="w-full"
                      size="sm"
                      variant="ghost"
                      leftIcon={<Share2 size={13} />}
                      onClick={() => {
                        const tg = window.Telegram?.WebApp as any;
                        if (tg?.switchInlineQuery)
                          tg.switchInlineQuery(`colecao ${c.name}`, ['users', 'groups']);
                        else navigateNative('help');
                      }}
                    >
                      Compartilhar
                    </Button>
                  )}
                </div>
              </Poster>
            ))}
          </PosterGrid>
          {list.data && !list.data.items.length && (
            <Card className="p-5">
              <p className="text-sm text-zinc-500">
                Nenhum personagem nesta seleção. Use Encontrar para adicionar desejos ou Duplicatas
                para organizar seu cofre.
              </p>
            </Card>
          )}
        </>
      )}
      <div className="flex justify-between gap-3">
        <Button
          size="sm"
          variant="secondary"
          disabled={page === 0}
          onClick={() => setPage((p) => p - 1)}
        >
          Anterior
        </Button>
        <Button
          size="sm"
          variant="secondary"
          disabled={!current.data?.has_more}
          onClick={() => setPage((p) => p + 1)}
        >
          Próxima página
        </Button>
      </div>
      {unlock && (
        <Dialog title="Remover proteção?" onClose={() => setUnlock(null)} busy={pending}>
          <p className="text-sm text-zinc-400">
            {unlock.name} poderá participar de vendas, trocas e reciclagem. O favorito do perfil
            continua protegido enquanto estiver selecionado.
          </p>
          <Button variant="danger" disabled={pending} onClick={() => void protect(unlock, false)}>
            Confirmar desbloqueio
          </Button>
        </Dialog>
      )}
      {preferences && (
        <Dialog
          title="Preferências da coleção"
          onClose={() => setPreferences(false)}
          busy={pending}
        >
          <QueryFeedback
            loading={settings.isPending}
            error={settings.error}
            retry={settings.refetch}
          />
          {settings.data &&
            (
              [
                [
                  'discoverable',
                  'Aparecer nas sugestões de troca',
                  'Mostra apenas duplicatas compatíveis. Perfis privados continuam ocultos.',
                ],
                [
                  'share_inline',
                  'Permitir vitrine inline',
                  'Você escolhe quais fichas enviar no Telegram.',
                ],
                [
                  'preserve_last',
                  'Preservar a última cópia no mercado',
                  'A Oficina sempre preserva a última cópia.',
                ],
              ] as const
            ).map(([key, label, hint]) => (
              <label key={key} className="flex items-start gap-3 border-b border-white/5 pb-4">
                <input
                  type="checkbox"
                  className="mt-1 shrink-0"
                  checked={preferenceDraft[key] ?? settings.data![key]}
                  disabled={pending}
                  onChange={async (e) => {
                    const enabled = e.target.checked;
                    setPreferenceDraft((old) => ({ ...old, [key]: enabled }));
                    const result = await perform(
                      '/settings',
                      { [key]: enabled },
                      { method: 'PATCH', success: 'Preferências salvas.' },
                    );
                    if (!result) setPreferenceDraft((old) => {
                      const next = { ...old }; delete next[key]; return next;
                    });
                  }}
                />
                <span className="min-w-0 text-xs text-zinc-200">
                  {label}
                  <span className="block text-zinc-500 mt-1 leading-relaxed">{hint}</span>
                </span>
              </label>
            ))}
        </Dialog>
      )}
    </NativePage>
  );
}
