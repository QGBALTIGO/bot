import { Brain, Clock3, RotateCcw, Trophy } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { getErrorMessage } from '../api/client';
import { sourcePost, useSourceQuery } from './api';
import { nativeParams, navigateNative } from './navigation';
import { Choices, Cover, NativePage, QueryFeedback } from './ui';

type Tile = { key: number; pair: number; name: string; image: string };
const PAIRS: Record<string, number> = { easy: 6, medium: 8, hard: 12, extreme: 18 };
function shuffle<T>(items: T[]): T[] {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j]!, copy[i]!];
  }
  return copy;
}
const seconds = (ms: number) =>
  `${Math.floor(ms / 60000)}:${String(Math.floor(ms / 1000) % 60).padStart(2, '0')}`;
export function Memory() {
  const raw = nativeParams().get('level') || 'easy',
    level = PAIRS[raw] ? raw : 'easy',
    pairs = PAIRS[level]!;
  const catalog = useSourceQuery('/api/cards/animes?limit=5000');
  const best = useSourceQuery('/api/memory/best');
  const [tiles, setTiles] = useState<Tile[]>([]),
    [open, setOpen] = useState<number[]>([]),
    [matched, setMatched] = useState<number[]>([]),
    [moves, setMoves] = useState(0),
    [elapsed, setElapsed] = useState(0),
    [finished, setFinished] = useState(false),
    [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle'),
    [saveError, setSaveError] = useState('');
  const start = useRef(0),
    lock = useRef(false),
    timer = useRef<number | undefined>(undefined),
    report = useRef<{ level: string; time_ms: number; moves: number } | null>(null),
    saving = useRef(false),
    gameId = useRef(0),
    alive = useRef(true);
  const build = useCallback(() => {
    window.clearTimeout(timer.current);
    gameId.current++;
    lock.current = false;
    start.current = 0;
    report.current = null;
    const unique = Array.from(
      new Map(
        (catalog.data?.items || [])
          .filter((x: any) => x.cover_image)
          .map((x: any) => [x.anime_id, x]),
      ).values(),
    ) as any[];
    if (unique.length < pairs) return;
    const selected = shuffle(unique).slice(0, pairs);
    setTiles(
      shuffle(
        selected.flatMap((work, index) =>
          [0, 1].map((copy) => ({
            key: index * 2 + copy,
            pair: index,
            name: work.anime,
            image: work.cover_image,
          })),
        ),
      ),
    );
    setOpen([]);
    setMatched([]);
    setMoves(0);
    setElapsed(0);
    setFinished(false);
    setSaveState('idle');
    setSaveError('');
  }, [catalog.data, pairs]);
  useEffect(() => {
    build();
  }, [build]);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      window.clearTimeout(timer.current);
    };
  }, []);
  useEffect(() => {
    if (finished) return;
    const interval = window.setInterval(() => {
      if (start.current) setElapsed(Math.max(1, performance.now() - start.current));
    }, 200);
    return () => window.clearInterval(interval);
  }, [finished]);
  const save = useCallback(async () => {
    if (!report.current || saving.current) return;
    saving.current = true;
    const id = gameId.current;
    setSaveState('saving');
    try {
      await sourcePost('/api/memory/finish', report.current);
      if (alive.current && id === gameId.current) {
        setSaveState('saved');
        void best.refetch();
      }
    } catch (error) {
      if (alive.current && id === gameId.current) {
        setSaveState('error');
        setSaveError(getErrorMessage(error));
      }
    } finally {
      saving.current = false;
    }
  }, [best.refetch]);
  const flip = (tile: Tile) => {
    if (lock.current || finished || open.includes(tile.key) || matched.includes(tile.pair)) return;
    if (!start.current) start.current = performance.now();
    const next = [...open, tile.key];
    setOpen(next);
    if (next.length !== 2) return;
    lock.current = true;
    const count = moves + 1;
    setMoves(count);
    const first = tiles.find((t) => t.key === next[0]);
    const matches = first?.pair === tile.pair;
    timer.current = window.setTimeout(
      () => {
        setOpen([]);
        lock.current = false;
        if (matches) {
          const all = [...matched, tile.pair];
          setMatched(all);
          if (all.length === pairs) {
            const ms = Math.max(1, Math.round(performance.now() - start.current));
            setElapsed(ms);
            setFinished(true);
            report.current = { level, time_ms: ms, moves: count };
            void save();
          }
        }
      },
      matches ? 350 : 850,
    );
  };
  return (
    <NativePage
      title="Jogo da memória"
      subtitle="Encontre os pares e melhore seu recorde"
      icon={Brain}
    >
      <Choices
        value={level}
        items={[
          ['easy', 'Fácil'],
          ['medium', 'Médio'],
          ['hard', 'Difícil'],
          ['extreme', 'Extremo'],
        ]}
        onChange={(l) => navigateNative('memory', { level: l })}
      />
      <div className="grid grid-cols-3 gap-3">
        {[
          ['Tempo', seconds(elapsed)],
          ['Jogadas', moves],
          ['Pares', `${matched.length}/${pairs}`],
        ].map(([label, value]) => (
          <Card className="p-3" key={label}>
            <p className="text-[9px] text-zinc-500 font-bold uppercase tracking-widest">{label}</p>
            <p
              className="font-mono text-lg text-zinc-100 mt-2"
              aria-live={label === 'Tempo' ? 'off' : 'polite'}
            >
              {value}
            </p>
          </Card>
        ))}
      </div>
      <QueryFeedback loading={catalog.isPending} error={catalog.error} retry={catalog.refetch} />
      {!catalog.isPending && !catalog.error && !tiles.length && (
        <Card className="p-5 text-sm text-zinc-400">
          Ainda não há imagens suficientes para montar este nível.
        </Card>
      )}
      <div
        className={`grid gap-2 ${pairs > 8 ? 'grid-cols-4 sm:grid-cols-6' : 'grid-cols-4'}`}
        aria-label="Tabuleiro de memória"
      >
        {tiles.map((tile) => {
          const visible = open.includes(tile.key) || matched.includes(tile.pair);
          return (
            <button
              key={tile.key}
              type="button"
              onClick={() => flip(tile)}
              disabled={finished || matched.includes(tile.pair)}
              aria-label={visible ? tile.name : `Carta fechada ${tile.key + 1}`}
              aria-pressed={visible}
              className="aspect-[2/3] overflow-hidden rounded-md border border-white/10 bg-zinc-900 focus-visible:outline-2 focus-visible:outline-brand-accent disabled:opacity-60"
            >
              {visible ? (
                <Cover src={tile.image} name={tile.name} />
              ) : (
                <div className="h-full flex items-center justify-center">
                  <Brain size={22} className="text-zinc-600" />
                </div>
              )}
            </button>
          );
        })}
      </div>
      {finished && (
        <Card className="p-5 space-y-3" role="status">
          <h2 className="text-sm text-zinc-100 font-bold flex items-center gap-2">
            <Trophy size={17} />
            Partida concluída
          </h2>
          <p className="text-sm text-zinc-400">
            {moves} jogadas em {seconds(elapsed)}.
          </p>
          <p className="text-xs text-zinc-500">
            {saveState === 'saved'
              ? 'Resultado salvo.'
              : saveState === 'saving'
                ? 'Salvando resultado...'
                : saveError}
          </p>
          {saveState === 'error' && (
            <Button variant="secondary" onClick={save}>
              Tentar salvar novamente
            </Button>
          )}
        </Card>
      )}
      <Button
        variant="secondary"
        leftIcon={<RotateCcw size={14} />}
        disabled={!tiles.length || saveState === 'saving'}
        onClick={build}
      >
        Nova partida
      </Button>
      {best.error && <QueryFeedback loading={false} error={best.error} retry={best.refetch} />}
      {best.data?.by_level?.[level] && (
        <Card className="p-4 flex items-center gap-3 text-xs text-zinc-400">
          <Clock3 size={14} />
          Melhor tempo: {seconds(best.data.by_level[level].time_ms)} ·{' '}
          {best.data.by_level[level].moves} jogadas
        </Card>
      )}
    </NativePage>
  );
}
