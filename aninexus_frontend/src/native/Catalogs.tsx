import { BookOpen, ExternalLink, Film, Search, Shapes, Star } from 'lucide-react';
import { CharacterTools, WishWork } from '../features/collecting/CharacterActions';
import { useState } from 'react';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import {
  useDebounced,
  useSourceAction,
  useSourcePages,
  useSourceQuery,
  sourcePost,
  queryUrl,
} from './api';
import { nativeParams, navigateNative, openExternal } from './navigation';
import { Choices, Cover, Dialog, More, NativePage, Poster, PosterGrid, QueryFeedback } from './ui';

interface Media {
  message_id: number;
  titulo: string;
  cover_url?: string;
  link_post?: string;
  format?: string;
  score?: number;
  year?: number;
  badge?: string;
}
interface Work {
  anime_id: number;
  anime: string;
  cover_image?: string;
  banner_image?: string;
  count?: number;
}
interface Character {
  id?: number;
  character_id?: number;
  name: string;
  anime?: string;
  image?: string;
  quantity?: number;
  subcategory?: string;
}
const keyOf = (item: Character) => Number(item.character_id ?? item.id);

export function Catalog({ manga = false }: { manga?: boolean }) {
  const [search, setSearch] = useState(nativeParams().get('q') || '');
  const [letter, setLetter] = useState('ALL');
  const [selected, setSelected] = useState<Media | null>(null);
  const q = useDebounced(search),
    endpoint = manga ? '/api/mangas/catalogo' : '/api/catalogo';
  const query = useSourcePages<Media>(endpoint, { q, letter });
  const items = query.data?.pages.flatMap((p) => p.items) || [];
  return (
    <NativePage
      title={manga ? 'Mangás' : 'Animes'}
      subtitle="Catálogo Baltigo"
      icon={manga ? BookOpen : Film}
    >
      <Input
        icon={Search}
        aria-label="Buscar no catálogo"
        placeholder="Buscar uma obra..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        maxLength={80}
      />
      <Choices
        label="Filtrar por inicial"
        value={letter}
        items={['ALL', '#', ...'ABCDEFGHIJKLMNOPQRSTUVWXYZ'].map((l) => [
          l,
          l === 'ALL' ? 'Todas' : l,
        ])}
        onChange={setLetter}
      />
      <p className="text-[10px] text-zinc-500 font-mono" aria-live="polite">
        {query.data?.pages[0]?.total ?? 0} obras encontradas
      </p>
      <QueryFeedback
        loading={query.isPending}
        error={query.error}
        retry={query.refetch}
        empty={!items.length}
      />
      <PosterGrid>
        {items.map((item) => (
          <Poster
            key={item.message_id}
            src={item.cover_url}
            title={item.titulo}
            subtitle={[item.format, item.year].filter(Boolean).join(' · ')}
            onClick={() => setSelected(item)}
          />
        ))}
      </PosterGrid>
      <More
        show={Boolean(query.hasNextPage)}
        pending={query.isFetchingNextPage}
        onClick={query.fetchNextPage}
      />
      {selected && (
        <Dialog title={selected.titulo} onClose={() => setSelected(null)}>
          <div className="flex gap-4">
            <Cover
              src={selected.cover_url}
              name={selected.titulo}
              className="w-28 shrink-0 rounded-md"
            />
            <div className="space-y-3 text-xs text-zinc-400">
              {selected.format && <Badge variant="secondary">{selected.format}</Badge>}
              {selected.year && <p>{selected.year}</p>}
              {selected.score && (
                <p className="flex items-center gap-1">
                  <Star size={13} />
                  {selected.score}
                </p>
              )}
            </div>
          </div>
          {selected.link_post ? (
            <Button
              className="w-full"
              leftIcon={<ExternalLink size={14} />}
              onClick={() => openExternal(selected.link_post!)}
            >
              Abrir no Telegram
            </Button>
          ) : (
            <p className="text-xs text-zinc-500">Link indisponível para esta obra.</p>
          )}
          <Button
            variant="secondary"
            className="w-full"
            onClick={() => navigateNative('requests', { q: selected.titulo })}
          >
            Solicitar ou reportar
          </Button>
        </Dialog>
      )}
    </NativePage>
  );
}

export function CharacterDialog({
  item,
  onClose,
  owned = false,
}: {
  item: Character;
  onClose: () => void;
  owned?: boolean;
}) {
  const { pending, run } = useSourceAction();
  return (
    <Dialog title={item.name} onClose={onClose} busy={Boolean(pending)}>
      <Cover src={item.image} name={item.name} className="w-48 mx-auto rounded-md" />
      <div className="text-center text-xs text-zinc-400 space-y-2">
        <p>{item.anime}</p>
        {item.quantity !== undefined && <p>{item.quantity} cópia(s) na coleção</p>}
        {item.subcategory && <Badge variant="secondary">{item.subcategory}</Badge>}
      </div>
      <CharacterTools id={keyOf(item)} owned={owned}/>
      {owned && (
        <Button
          className="w-full"
          isLoading={pending === 'favorite'}
          disabled={Boolean(pending)}
          leftIcon={<Star size={14} />}
          onClick={() =>
            run(
              'favorite',
              () => sourcePost('/api/menu/favorite', { character_id: keyOf(item) }),
              'Favorito atualizado.',
            )
          }
        >
          Definir como favorito
        </Button>
      )}
      <Button
        variant="secondary"
        className="w-full"
        disabled={Boolean(pending)}
        onClick={() =>
          navigateNative('contribute', { view: 'image', character_id: keyOf(item), q: item.name })
        }
      >
        Sugerir nova imagem
      </Button>
    </Dialog>
  );
}

export function Cards() {
  const params = nativeParams(),
    animeId = params.get('anime_id'),
    category = params.get('name') || '';
  const view = params.get('view') || 'works';
  const [search, setSearch] = useState(params.get('q') || '');
  const [selected, setSelected] = useState<Character | null>(null);
  const q = useDebounced(search),
    characterSearch = view === 'characters' && !animeId;
  const categories = useSourceQuery<{ items: { name: string; count: number }[] }>(
    '/api/cards/subcategories',
  );
  const endpoint = animeId
    ? '/api/cards/characters'
    : view === 'category'
      ? '/api/cards/subcategory'
      : '/api/cards/animes';
  const pages = useSourcePages<Work & Character>(
    endpoint,
    animeId ? { anime_id: animeId, q } : view === 'category' ? { name: category, q } : { q },
    !characterSearch && (view !== 'category' || Boolean(category)),
  );
  const searchQuery = useSourceQuery<{ items: Character[]; total: number }>(
    queryUrl('/api/cards/search', { q, limit: 500 }),
    characterSearch && q.length > 0,
  );
  const query = characterSearch ? searchQuery : pages;
  const items: (Work & Character)[] = characterSearch
    ? ((searchQuery.data?.items || []) as (Work & Character)[])
    : pages.data?.pages.flatMap((p) => p.items) || [];
  const total = characterSearch ? searchQuery.data?.total : pages.data?.pages[0]?.total;
  const workTitle = pages.data?.pages[0]?.anime;
  const title = animeId
    ? (typeof workTitle === 'string' ? workTitle : workTitle?.anime) || 'Personagens'
    : category || 'Cards';
  return (
    <NativePage
      title={title}
      subtitle="Obras, personagens e categorias"
      icon={Shapes}
      {...(animeId || category ? { back: () => navigateNative('cards') } : {})}
    >
      {animeId && <WishWork animeId={Number(animeId)}/>}
      {!animeId && (
        <Choices
          value={view}
          items={[
            ['works', 'Obras'],
            ['characters', 'Personagens'],
            ['category', 'Categorias'],
          ]}
          onChange={(v) => navigateNative('cards', { view: v })}
        />
      )}
      {view === 'category' && !animeId && (
        <>
          <QueryFeedback
            loading={categories.isPending}
            error={categories.error}
            retry={categories.refetch}
          />
          <Choices
            value={category}
            items={(categories.data?.items || []).map((c) => [c.name, `${c.name} · ${c.count}`])}
            onChange={(name) => navigateNative('cards', { view: 'category', name })}
          />
        </>
      )}
      {(view !== 'category' || category) && (
        <Input
          icon={Search}
          aria-label="Buscar cards"
          placeholder={characterSearch ? 'Nome de um personagem...' : 'Buscar...'}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          maxLength={80}
        />
      )}
      {characterSearch && !q ? (
        <Card className="p-6 text-xs text-zinc-500">
          Digite o nome de um personagem para pesquisar em todas as obras.
        </Card>
      ) : view === 'category' && !category ? (
        <p className="text-xs text-zinc-500">Selecione uma categoria.</p>
      ) : (
        <>
          <p className="text-[10px] font-mono text-zinc-500" aria-live="polite">
            {total || 0} resultados
          </p>
          <QueryFeedback
            loading={query.isPending}
            error={query.error}
            retry={query.refetch}
            empty={!items.length}
          />
          <PosterGrid>
            {items.map((item, i) =>
              animeId || view === 'characters' || view === 'category' ? (
                <Poster
                  key={item.id ?? i}
                  src={item.image}
                  title={item.name}
                  subtitle={item.anime}
                  onClick={() => setSelected(item)}
                />
              ) : (
                <Poster
                  key={item.anime_id}
                  src={item.cover_image}
                  title={item.anime}
                  onClick={() => navigateNative('cards', { anime_id: item.anime_id })}
                />
              ),
            )}
          </PosterGrid>
          {!characterSearch && (
            <More
              show={Boolean(pages.hasNextPage)}
              pending={pages.isFetchingNextPage}
              onClick={pages.fetchNextPage}
            />
          )}
          {characterSearch && items.length === 500 && (
            <p className="text-xs text-zinc-500">
              Mostrando até 500 resultados. Refine a busca para encontrar um personagem específico.
            </p>
          )}
        </>
      )}
      <Button variant="secondary" onClick={() => navigateNative('contribute', { view: 'work' })}>
        Contribuir com uma obra
      </Button>
      {selected && <CharacterDialog item={selected} onClose={() => setSelected(null)} />}
    </NativePage>
  );
}

export function Album() {
  const params = nativeParams(),
    animeId = params.get('anime_id'),
    share = params.get('share') || '',
    shared = Boolean(share);
  const sharedEndpoint = (path: string) =>
    shared ? `/api/collection/shared/${path}${path.includes('?') ? '&' : '?'}share=${encodeURIComponent(share)}` : `/api/collection/${path}`;
  const [view, setView] = useState(animeId ? 'owned' : 'cards');
  const [search, setSearch] = useState('');
  const [visible, setVisible] = useState(40);
  const [selected, setSelected] = useState<Character | null>(null);
  const stats = useSourceQuery(sharedEndpoint('state'));
  const query = useSourceQuery(
    animeId
      ? sharedEndpoint(`anime?anime_id=${encodeURIComponent(animeId)}&mode=${encodeURIComponent(view)}`)
      : sharedEndpoint(view === 'works' ? 'animes' : 'cards'),
  );
  const items = (query.data?.items || []).filter((item: any) =>
    String(item.name || item.anime || '')
      .toLocaleLowerCase('pt-BR')
      .includes(search.toLocaleLowerCase('pt-BR')),
  );
  const details = query.data?.anime;
  return (
    <NativePage
      title={
        animeId
          ? (typeof details === 'string' ? details : details?.anime) || 'Álbum da obra'
          : shared ? `Coleção de ${stats.data?.profile?.display_name || 'jogador'}` : 'Meu álbum'
      }
      subtitle={shared ? "Coleção compartilhada · somente leitura" : "Sua coleção, cópias e obras completas"}
      icon={BookOpen}
      {...(animeId ? { back: () => navigateNative('album') } : {})}
    >
      <div className="grid grid-cols-3 gap-3">
        {[
          ['Cards', stats.data?.stats?.unique_cards],
          ['Cópias', stats.data?.stats?.total_copies],
          ['Completas', stats.data?.stats?.completed_animes],
        ].map(([label, value]) => (
          <Card key={label} className="p-3">
            <p className="text-[9px] uppercase tracking-widest text-zinc-500">{label}</p>
            <p className="font-mono text-xl text-zinc-100 mt-2">{value ?? '—'}</p>
          </Card>
        ))}
      </div>
      <Choices
        value={view}
        items={
          animeId
            ? [
                ['owned', 'Obtidos'],
                ['missing', 'Faltantes'],
                ['gallery', 'Todos'],
              ]
            : [
                ['cards', 'Personagens'],
                ['works', 'Obras'],
              ]
        }
        onChange={(v) => {
          setView(v);
          setVisible(40);
        }}
      />
      <Input
        icon={Search}
        aria-label="Buscar no álbum"
        placeholder="Buscar na coleção..."
        value={search}
        onChange={(e) => {
          setSearch(e.target.value);
          setVisible(40);
        }}
      />
      <QueryFeedback
        loading={query.isPending}
        error={query.error}
        retry={query.refetch}
        empty={!items.length}
      />
      <PosterGrid>
        {items
          .slice(0, visible)
          .map((item: any, i: number) =>
            view === 'works' ? (
              <Poster
                key={item.anime_id}
                src={item.cover_image}
                title={item.anime}
                subtitle={`${item.owned_count}/${item.total_count} · ${item.completion_pct}%`}
                onClick={() => navigateNative('album', { anime_id: item.anime_id, ...(shared ? { share } : {}) })}
              />
            ) : (
              <Poster
                key={item.character_id ?? item.id ?? i}
                src={item.image}
                title={item.name}
                subtitle={`${item.quantity || 0} cópia(s) · ${item.anime || ''}`}
                onClick={() => { if (!shared) setSelected(item); }}
              />
            ),
          )}
      </PosterGrid>
      <More
        show={visible < items.length}
        pending={false}
        onClick={() => setVisible((n) => n + 40)}
      />
      {selected && (
        <CharacterDialog
          item={selected}
          owned={Number(selected.quantity) > 0}
          onClose={() => setSelected(null)}
        />
      )}
    </NativePage>
  );
}
