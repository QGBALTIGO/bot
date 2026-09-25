import { Dices, ScanSearch, Search } from 'lucide-react';
import { useState } from 'react';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { useToast } from '../../components/ui/Toast';
import { getErrorMessage } from '../../api/client';
import { NativePage, QueryFeedback, Field, fieldClass } from '../../native/ui';
import { nativeParams, navigateNative } from '../../native/navigation';
import { featureFetch, useFeatureQuery } from './api';
interface Match {
  anime_id: number;
  title: string;
  episode: number | null;
  similarity: number;
  at_seconds: number;
}
export function Identify() {
  const [file, setFile] = useState<File | null>(null),
    [consent, setConsent] = useState(false),
    [pending, setPending] = useState(false),
    [items, setItems] = useState<Match[]>([]),
    [searched, setSearched] = useState(false);
  const { addToast } = useToast();
  const search = async () => {
    if (!file || !consent || pending) return;
    setPending(true);
    try {
      const result = await featureFetch<{ items: Match[] }>('/identify', {
        method: 'POST',
        body: file,
        headers: {
          'Content-Type': file.type || 'application/octet-stream',
          'X-Scene-Consent': 'yes',
        },
      });
      setItems(result.items);
      setSearched(true);
    } catch (e) {
      addToast(getErrorMessage(e), 'error');
    } finally {
      setPending(false);
    }
  };
  return (
    <NativePage
      title="Identificar anime"
      subtitle="Encontre uma obra a partir de uma cena. Identificação aproximada por trace.moe."
      icon={ScanSearch}
    >
      <Card className="p-5 space-y-4">
        <Field label="Imagem da cena · até 2 MB">
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className={fieldClass}
            onChange={(e) => {
              const image = e.target.files?.[0];
              if (image && image.size > 2 * 1024 * 1024) {
                addToast('Escolha uma imagem de até 2 MB.', 'error');
                e.target.value = '';
                setFile(null);
              } else {
                setFile(image || null);
                setItems([]);
                setSearched(false);
              }
            }}
          />
        </Field>
        <label className="flex gap-3 items-start">
          <input
            type="checkbox"
            checked={consent}
            className="mt-1"
            onChange={(e) => setConsent(e.target.checked)}
          />
          <span className="text-xs text-zinc-400 leading-relaxed">
            Autorizo enviar esta imagem ao trace.moe para identificar a cena. Não envie fotos
            pessoais ou informações privadas.
          </span>
        </label>
        <Button
          className="w-full"
          disabled={!file || !consent || pending}
          isLoading={pending}
          leftIcon={<Search size={14} />}
          onClick={() => void search()}
        >
          Identificar cena
        </Button>
      </Card>
      {items.map((m, index) => (
        <Card key={`${m.anime_id}-${index}`} className="p-4 space-y-3">
          <h2 className="text-sm font-bold text-zinc-100 break-words">{m.title}</h2>
          <p className="text-xs text-zinc-500">
            Correspondência: {m.similarity}% · Episódio {m.episode ?? 'não informado'} · Cena em{' '}
            {Math.floor(m.at_seconds / 60)}:{String(Math.floor(m.at_seconds % 60)).padStart(2, '0')}
          </p>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => navigateNative('catalog_anime', { q: m.title })}
          >
            Buscar no catálogo
          </Button>
        </Card>
      ))}
      {searched && !items.length && (
        <p className="text-sm text-zinc-500">
          Nenhuma correspondência apropriada. Tente uma cena nítida, sem bordas ou texto sobreposto.
        </p>
      )}
    </NativePage>
  );
}
interface DiceInfo {
  rules: string[];
  guarantee_note: string;
  eligible_characters: number;
  character_probability: number | null;
  history: {
    roll_id: number;
    dice_value: number;
    rewarded_character_id: number | null;
    character_name?: string;
    status: string;
    created_at: number;
  }[];
}
export function DiceInfo() {
  const anime = Number(nativeParams().get('anime_id')) || 0;
  const query = useFeatureQuery<DiceInfo>(`/dice-info?anime_id=${anime}`);
  const labels: Record<string, string> = {
    pending: 'Aguardando escolha',
    picked: 'Escolha registrada',
    resolved: 'Concluído',
    completed: 'Concluído',
    cancelled: 'Cancelado',
    expired: 'Expirado',
  };
  return (
    <NativePage title="Regras e histórico do Dado" icon={Dices} back={() => navigateNative('dado')}>
      <QueryFeedback loading={query.isPending} error={query.error} retry={query.refetch} />
      <Card className="p-5 space-y-3">
        {query.data?.rules.map((rule) => (
          <p className="text-sm text-zinc-400 leading-relaxed" key={rule}>
            {rule}
          </p>
        ))}
        <p className="text-xs text-zinc-500">{query.data?.guarantee_note}</p>
        {Boolean(query.data?.eligible_characters) && (
          <p className="text-sm text-zinc-300">
            Esta obra tem {query.data?.eligible_characters} personagens elegíveis. Chance de cada um
            após escolher a obra:{' '}
            {((query.data?.character_probability || 0) * 100).toLocaleString('pt-BR', {
              maximumFractionDigits: 3,
            })}
            %.
          </p>
        )}
      </Card>
      <h2 className="text-sm font-bold text-zinc-200">Últimos 20 resultados</h2>
      <div className="space-y-2">
        {query.data?.history.map((r) => (
          <Card key={r.roll_id} className="p-3 flex flex-wrap justify-between gap-2">
            <p className="text-xs text-zinc-400">
              Dado {r.dice_value} · {labels[r.status] || r.status}
            </p>
            <p className="text-xs text-zinc-500">
              {new Date(r.created_at * 1000).toLocaleString('pt-BR')}
            </p>
            {r.rewarded_character_id && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() =>
                  navigateNative('cards', {
                    view: 'characters',
                    character_id: r.rewarded_character_id!,
                    q: r.character_name || String(r.rewarded_character_id),
                  })
                }
              >
                Ver personagem #{r.rewarded_character_id}
              </Button>
            )}
          </Card>
        ))}
      </div>
    </NativePage>
  );
}
