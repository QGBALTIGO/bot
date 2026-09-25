import type { EventSpec } from './contracts.generated';
import { CalendarDays, Flag, Plus, Users } from 'lucide-react';
import { useState } from 'react';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Cover, Dialog, Field, NativePage, QueryFeedback, fieldClass } from '../../native/ui';
import { type CollectionCard, useFeatureAction, useFeatureQuery } from './api';
interface Event {
  id: string;
  title: string;
  description: string;
  status: string;
  starts_at: string;
  ends_at: string;
  goal: number;
  progress: number;
  contribution: number;
  today: number;
  daily_limit: number;
  reward_label: string;
  claimed: boolean;
  characters: CollectionCard[];
}
const formatted = (s: string) =>
  new Date(s).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
export function Events() {
  const query = useFeatureQuery<{ items: Event[] }>('/events'),
    settings = useFeatureQuery<{ can_manage_events: boolean }>('/settings');
  const { perform, pending } = useFeatureAction(),
    [selected, setSelected] = useState<Event | null>(null),
    [creating, setCreating] = useState(false),
    [publish, setPublish] = useState<Event | null>(null);
  const [form, setForm] = useState({
    title: '',
    description: '',
    ids: '',
    goal: 100,
    daily_limit: 1,
    reward_label: 'Expedição concluída',
    starts_at: '',
    ends_at: '',
  });
  const validIds = form.ids
    .split(/[,\s]+/)
    .filter(Boolean)
    .map(Number);
  return (
    <NativePage
      title="Eventos e expedições"
      subtitle="Colecione com a comunidade. Suas contribuições não consomem personagens."
      icon={Flag}
    >
      {settings.data?.can_manage_events && (
        <Button size="sm" leftIcon={<Plus size={14} />} onClick={() => setCreating(true)}>
          Preparar evento
        </Button>
      )}
      <QueryFeedback loading={query.isPending} error={query.error} retry={query.refetch} />
      {query.data && !query.data.items.length && (
        <Card className="p-5 space-y-2">
          <h2 className="text-sm font-bold text-zinc-200">Nenhum evento publicado</h2>
          <p className="text-sm text-zinc-500">
            Os eventos aparecerão aqui depois de revisados pela administração. Nenhuma recompensa é
            criada automaticamente.
          </p>
        </Card>
      )}
      <div className="grid md:grid-cols-2 gap-4">
        {query.data?.items.map((e) => {
          const active =
            e.status === 'active' &&
            Date.parse(e.starts_at) <= Date.now() &&
            Date.parse(e.ends_at) > Date.now();
          return (
            <Card key={e.id} className="p-5 space-y-4">
              <div>
                <p className="text-[10px] uppercase tracking-wider text-zinc-500">
                  {e.status === 'draft'
                    ? 'Rascunho · somente administração'
                    : active
                      ? 'Em andamento'
                      : 'Fora do período'}
                </p>
                <h2 className="text-lg font-bold text-zinc-100 break-words mt-1">{e.title}</h2>
                <p className="text-sm text-zinc-400 leading-relaxed mt-2 break-words">
                  {e.description}
                </p>
              </div>
              <p className="text-[10px] text-zinc-500">
                {formatted(e.starts_at)} — {formatted(e.ends_at)}
              </p>
              <div className="space-y-2">
                <div className="flex justify-between gap-3 text-xs text-zinc-400">
                  <span>Meta coletiva</span>
                  <span className="font-mono">
                    {e.progress} / {e.goal}
                  </span>
                </div>
                <progress
                  max={e.goal}
                  value={Math.min(e.goal, e.progress)}
                  className="w-full h-1.5 accent-blue-500"
                  aria-label="Progresso da expedição"
                />
              </div>
              <p className="text-xs text-zinc-500">
                Sua contribuição: {e.contribution} · Hoje: {e.today}/{e.daily_limit}
                <br />
                Emblema: {e.reward_label}
              </p>
              <div className="flex flex-wrap gap-2">
                {e.status === 'draft' ? (
                  <Button size="sm" disabled={pending} onClick={() => setPublish(e)}>
                    Revisar publicação
                  </Button>
                ) : (
                  <>
                    <Button
                      size="sm"
                      disabled={!active || pending || e.today >= e.daily_limit}
                      onClick={() => setSelected(e)}
                    >
                      Contribuir
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={pending || e.claimed || e.progress < e.goal || e.contribution < 1}
                      onClick={() =>
                        void perform(
                          `/events/${e.id}/claim`,
                          {},
                          { success: 'Recompensa disponível na Oficina.' },
                        )
                      }
                    >
                      {e.claimed ? 'Resgatado' : 'Resgatar emblema'}
                    </Button>
                  </>
                )}
              </div>
            </Card>
          );
        })}
      </div>
      {selected && (
        <Dialog
          title={`Contribuir · ${selected.title}`}
          onClose={() => setSelected(null)}
          busy={pending}
        >
          <p className="text-xs text-zinc-400">
            Escolha um personagem que você possui. Cada personagem pode contribuir uma vez ao dia;
            limite de {selected.daily_limit} contribuição(ões). Sua carta permanece na coleção.
          </p>
          <div className="grid grid-cols-3 gap-3 max-h-96 overflow-y-auto">
            {selected.characters.map((c) => (
              <button
                key={c.id}
                className="border border-white/10 rounded-md min-w-0 overflow-hidden text-left disabled:opacity-50"
                disabled={pending}
                onClick={async () => {
                  const ok = await perform(
                    `/events/${selected.id}/contribute`,
                    { character_id: c.id },
                    { idempotent: true, success: 'Contribuição registrada.' },
                  );
                  if (ok) setSelected(null);
                }}
              >
                <Cover name={c.name} src={c.image} />
                <span className="block p-2 text-xs text-zinc-200 break-words">{c.name}</span>
              </button>
            ))}
          </div>
        </Dialog>
      )}
      {publish && (
        <Dialog title="Publicar evento revisado?" onClose={() => setPublish(null)} busy={pending}>
          <p className="text-sm text-zinc-200">{publish.title}</p>
          <p className="text-xs text-zinc-400">
            {publish.characters.length} personagens · meta {publish.goal} · {publish.daily_limit}{' '}
            contribuição(ões) por dia.
          </p>
          <p className="text-xs text-zinc-500">
            O manifesto fica imutável após a publicação. A recompensa é apenas o emblema “
            {publish.reward_label}”, sem Coins ou cartas extras.
          </p>
          <Button
            className="w-full"
            isLoading={pending}
            onClick={async () => {
              const ok = await perform(
                `/events/${publish.id}/publish`,
                {},
                { success: 'Evento publicado.' },
              );
              if (ok) setPublish(null);
            }}
          >
            Confirmar publicação
          </Button>
        </Dialog>
      )}
      {creating && (
        <Dialog title="Preparar evento" onClose={() => setCreating(false)} busy={pending}>
          <div className="space-y-3">
            <Field label="Nome">
              <input
                className={fieldClass}
                maxLength={80}
                value={form.title}
                onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              />
            </Field>
            <Field label="Descrição">
              <textarea
                className={fieldClass}
                maxLength={1000}
                value={form.description}
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              />
            </Field>
            <Field label="IDs de personagens do catálogo, separados por vírgula">
              <textarea
                className={fieldClass}
                value={form.ids}
                maxLength={1400}
                onChange={(e) => setForm((f) => ({ ...f, ids: e.target.value }))}
              />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Meta coletiva">
                <input
                  type="number"
                  className={fieldClass}
                  min={1}
                  max={100000}
                  value={form.goal}
                  onChange={(e) => setForm((f) => ({ ...f, goal: Number(e.target.value) }))}
                />
              </Field>
              <Field label="Limite diário">
                <input
                  type="number"
                  className={fieldClass}
                  min={1}
                  max={5}
                  value={form.daily_limit}
                  onChange={(e) => setForm((f) => ({ ...f, daily_limit: Number(e.target.value) }))}
                />
              </Field>
            </div>
            <Field label="Nome do emblema">
              <input
                className={fieldClass}
                maxLength={60}
                value={form.reward_label}
                onChange={(e) => setForm((f) => ({ ...f, reward_label: e.target.value }))}
              />
            </Field>
            <Field label="Início (horário do seu aparelho)">
              <input
                type="datetime-local"
                className={fieldClass}
                value={form.starts_at}
                onChange={(e) => setForm((f) => ({ ...f, starts_at: e.target.value }))}
              />
            </Field>
            <Field label="Fim (até 30 dias depois)">
              <input
                type="datetime-local"
                className={fieldClass}
                value={form.ends_at}
                onChange={(e) => setForm((f) => ({ ...f, ends_at: e.target.value }))}
              />
            </Field>
            <Button
              className="w-full"
              disabled={
                pending ||
                form.title.trim().length < 3 ||
                form.description.trim().length < 10 ||
                !form.starts_at ||
                !form.ends_at ||
                !validIds.length ||
                validIds.length > 100 ||
                validIds.some((n) => !Number.isSafeInteger(n) || n < 1)
              }
              onClick={async () => {
                const ok = await perform(
                  '/events',
                  {
                    title: form.title.trim(),
                    description: form.description.trim(),
                    character_ids: validIds,
                    goal: form.goal,
                    daily_limit: form.daily_limit,
                    reward_label: form.reward_label.trim(),
                    starts_at: new Date(form.starts_at).toISOString(),
                    ends_at: new Date(form.ends_at).toISOString(),
                  } satisfies Omit<EventSpec, 'request_id'>,
                  { idempotent: true, success: 'Rascunho criado. Revise antes de publicar.' },
                );
                if (ok) setCreating(false);
              }}
            >
              Salvar rascunho
            </Button>
          </div>
        </Dialog>
      )}
    </NativePage>
  );
}
