import { Hammer, Search, Sparkles } from 'lucide-react';
import { useState } from 'react';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Card } from '../../components/ui/Card';
import { useDebounced } from '../../native/api';
import { Cover, Dialog, Field, NativePage, QueryFeedback, fieldClass } from '../../native/ui';
import {
  type CardPage,
  type CollectionCard,
  featureFetch,
  useFeatureAction,
  useFeatureQuery,
} from './api';
import { useToast } from '../../components/ui/Toast';
import { getErrorMessage } from '../../api/client';

interface State {
  fragments: number;
  recipes: { id: string; label: string; cost: number }[];
  cosmetics: { cosmetic_id: string; label: string; kind: string }[];
  equipped: string | null;
}
export function Workshop() {
  const state = useFeatureQuery<State>('/workshop'),
    { perform, pending } = useFeatureAction(),
    { addToast } = useToast();
  const [q, setQ] = useState(''),
    [offset, setOffset] = useState(0),
    [selected, setSelected] = useState<Record<number, number>>({});
  const [preview, setPreview] = useState<{
      items: (CollectionCard & { consume: number })[];
      fragments: number;
    } | null>(null),
    [previewing, setPreviewing] = useState(false);
  const query = useFeatureQuery<CardPage>(
    `/characters?view=duplicates&q=${encodeURIComponent(useDebounced(q))}&offset=${offset}`,
  );
  const items = Object.entries(selected)
    .filter(([, n]) => n > 0)
    .map(([id, n]) => ({ character_id: Number(id), quantity: n }));
  const review = async () => {
    if (previewing || pending || !items.length) return;
    setPreviewing(true);
    try {
      setPreview(
        await featureFetch('/workshop/preview', {
          method: 'POST',
          body: JSON.stringify({ items }),
        }),
      );
    } catch (e) {
      addToast(getErrorMessage(e), 'error');
    } finally {
      setPreviewing(false);
    }
  };
  return (
    <NativePage
      title="Oficina"
      subtitle="Transforme duplicatas em cosméticos. Sua última cópia fica com você."
      icon={Hammer}
    >
      <QueryFeedback loading={state.isPending} error={state.error} retry={state.refetch} />
      <Card className="p-5 flex items-center justify-between gap-3">
        <div>
          <p className="text-xs text-zinc-500">Fragmentos disponíveis</p>
          <p className="text-3xl text-zinc-100 font-mono mt-1">{state.data?.fragments ?? 0}</p>
        </div>
        <Sparkles size={26} className="text-brand-accent" />
      </Card>
      <h2 className="text-sm text-zinc-200 font-bold">Escolha o que reciclar</h2>
      <Input
        icon={Search}
        value={q}
        maxLength={80}
        aria-label="Buscar duplicatas"
        onChange={(e) => {
          setQ(e.target.value);
          setOffset(0);
        }}
        placeholder="Nome ou obra..."
      />
      <QueryFeedback loading={query.isPending} error={query.error} retry={query.refetch} />
      <div className="space-y-3">
        {query.data?.items.map((c) => (
          <Card key={c.id} className="p-3 flex gap-3 items-center">
            <Cover name={c.name} src={c.image} className="w-14 shrink-0 rounded-md" />
            <div className="min-w-0 flex-1">
              <p className="text-xs font-bold text-zinc-200 break-words">{c.name}</p>
              <p className="text-[10px] text-zinc-500">
                {c.quantity} cópias ·{' '}
                {c.protected || c.favorite
                  ? 'Protegido'
                  : c.reserved
                    ? 'Reservado'
                    : 'Uma cópia será preservada'}
              </p>
            </div>
            <div className="w-20 shrink-0">
              <Field label="Usar">
                <input
                  type="number"
                  className={fieldClass}
                  min={0}
                  max={Math.min(20, c.quantity - 1)}
                  value={selected[c.id] || 0}
                  disabled={pending || Boolean(c.protected || c.favorite || c.reserved)}
                  onChange={(e) =>
                    setSelected((s) => ({
                      ...s,
                      [c.id]: Math.max(
                        0,
                        Math.min(20, c.quantity - 1, Number(e.target.value) || 0),
                      ),
                    }))
                  }
                />
              </Field>
            </div>
          </Card>
        ))}
      </div>
      {query.data && !query.data.items.length && (
        <p className="text-sm text-zinc-500">Você não tem duplicatas nesta seleção.</p>
      )}
      <div className="flex justify-between gap-2">
        <Button
          size="sm"
          variant="secondary"
          disabled={!offset}
          onClick={() => setOffset((x) => Math.max(0, x - 24))}
        >
          Anterior
        </Button>
        <Button
          size="sm"
          variant="secondary"
          disabled={!query.data?.has_more}
          onClick={() => setOffset((x) => x + 24)}
        >
          Próxima
        </Button>
      </div>
      <Button
        className="w-full"
        isLoading={previewing}
        disabled={pending || !items.length || items.length > 20}
        onClick={() => void review()}
      >
        Revisar {items.reduce((s, i) => s + i.quantity, 0)} cópia(s)
      </Button>
      <h2 className="text-sm text-zinc-200 font-bold">Criar cosméticos</h2>
      <div className="grid sm:grid-cols-3 gap-3">
        {state.data?.recipes.map((recipe) => {
          const owned = state.data!.cosmetics.some((c) => c.cosmetic_id === recipe.id);
          return (
            <Card key={recipe.id} className="p-4 flex flex-col gap-3">
              <h3 className="text-sm font-bold text-zinc-200">{recipe.label}</h3>
              <p className="text-xs text-zinc-500">
                {recipe.cost} fragmentos · sem vantagem em sorteios
              </p>
              <Button
                size="sm"
                className="mt-auto"
                disabled={pending || owned || state.data!.fragments < recipe.cost}
                onClick={() =>
                  void perform(
                    '/workshop/craft',
                    { recipe: recipe.id },
                    { idempotent: true, success: 'Cosmético criado.' },
                  )
                }
              >
                {owned ? 'Já adquirido' : 'Criar'}
              </Button>
            </Card>
          );
        })}
      </div>
      <h2 className="text-sm text-zinc-200 font-bold">Seus cosméticos</h2>
      <div className="flex flex-wrap gap-2">
        {state.data?.cosmetics.map((c) => (
          <Button
            key={c.cosmetic_id}
            size="sm"
            variant={state.data?.equipped === c.cosmetic_id ? 'primary' : 'secondary'}
            disabled={pending}
            onClick={() =>
              void perform(
                '/cosmetics/equipped',
                { cosmetic_id: state.data?.equipped === c.cosmetic_id ? null : c.cosmetic_id },
                { method: 'PUT', success: 'Perfil atualizado.' },
              )
            }
          >
            {c.label}
            {state.data?.equipped === c.cosmetic_id ? ' · Em uso' : ''}
          </Button>
        ))}
      </div>
      {preview && (
        <Dialog title="Confirmar reciclagem" onClose={() => setPreview(null)} busy={pending}>
          <p className="text-xs text-zinc-400">
            Estas cópias serão consumidas. A ação não pode ser desfeita. Nenhum favorito, personagem
            protegido ou última cópia será usado.
          </p>
          <div className="space-y-2">
            {preview.items.map((c) => (
              <p key={c.id} className="text-sm text-zinc-200 break-words">
                {c.name} × {c.consume}
              </p>
            ))}
          </div>
          <p className="text-sm font-bold text-zinc-200">
            Você recebe {preview.fragments} fragmentos.
          </p>
          <Button
            className="w-full"
            variant="danger"
            isLoading={pending}
            onClick={async () => {
              const result = await perform(
                '/workshop/recycle',
                { items: preview.items.map((c) => ({ character_id: c.id, quantity: c.consume })) },
                { idempotent: true, economic: true, success: 'Duplicatas recicladas.' },
              );
              if (result) {
                setPreview(null);
                setSelected({});
              }
            }}
          >
            Confirmar e receber fragmentos
          </Button>
        </Dialog>
      )}
    </NativePage>
  );
}
