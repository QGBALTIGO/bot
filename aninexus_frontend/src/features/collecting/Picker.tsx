import { Search } from 'lucide-react';
import { useState } from 'react';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { useDebounced } from '../../native/api';
import { Cover, QueryFeedback } from '../../native/ui';
import { type CollectionCard, type CardPage, useFeatureQuery } from './api';
export function Picker({
  onSelect,
  transferable = true,
  catalog = false,
}: {
  onSelect: (card: CollectionCard) => void;
  transferable?: boolean;
  catalog?: boolean;
}) {
  const [q, setQ] = useState(''),
    [page, setPage] = useState(0);
  const query = useFeatureQuery<CardPage>(
    `/characters?view=${catalog ? 'catalog' : 'owned'}&q=${encodeURIComponent(useDebounced(q))}&offset=${page * 24}`,
  );
  return (
    <div className="space-y-3">
      <Input
        icon={Search}
        value={q}
        maxLength={80}
        aria-label="Buscar na seleção"
        placeholder="Buscar personagem..."
        onChange={(e) => {
          setQ(e.target.value);
          setPage(0);
        }}
      />
      <QueryFeedback loading={query.isPending} error={query.error} retry={query.refetch} />
      <div className="grid grid-cols-3 gap-2 max-h-80 overflow-y-auto">
        {query.data?.items.map((c) => (
          <button
            key={c.id}
            type="button"
            disabled={transferable && Boolean(c.protected || c.favorite || c.reserved)}
            onClick={() => onSelect(c)}
            className="min-w-0 rounded-md border border-white/10 text-left overflow-hidden disabled:opacity-40 focus-visible:ring-2 focus-visible:ring-brand-accent"
          >
            <Cover name={c.name} src={c.image} />
            <span className="block p-2 text-[10px] text-zinc-200 line-clamp-2">{c.name}</span>
            <span className="block px-2 pb-2 text-[9px] text-zinc-500">
              {c.quantity} cópia(s)
              {c.protected || c.favorite ? ' · Protegido' : c.reserved ? ' · Reservado' : ''}
            </span>
          </button>
        ))}
      </div>
      {query.data && !query.data.items.length && (
        <p className="text-xs text-zinc-500">Nenhum personagem disponível.</p>
      )}
      <div className="flex justify-between">
        <Button
          variant="secondary"
          size="sm"
          disabled={!page}
          onClick={() => setPage((x) => x - 1)}
        >
          Anterior
        </Button>
        <Button
          variant="secondary"
          size="sm"
          disabled={!query.data?.has_more}
          onClick={() => setPage((x) => x + 1)}
        >
          Próxima
        </Button>
      </div>
    </div>
  );
}
