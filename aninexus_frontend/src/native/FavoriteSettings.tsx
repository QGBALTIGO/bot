import { Heart, Search, Trash2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { useUser, type FavoriteCharacter } from '../context/UserContext';
import { sourcePost, useSourceAction, useSourceQuery } from './api';
import { Dialog, QueryFeedback } from './ui';
import { nativeParams } from './navigation';

/** The favorite belongs to the account, not to an individual catalog or view. */
export function FavoriteSettings({ current }: { current?: FavoriteCharacter | null }) {
  const { user, patchUser } = useUser();
  const cache = useQueryClient();
  const { pending, run } = useSourceAction();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [visible, setVisible] = useState(24);
  const query = useSourceQuery<{ items: FavoriteCharacter[] }>('/api/menu/collection-characters', open);
  const matches = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase('pt-BR');
    return (query.data?.items || []).filter((c) => `${c.name} ${c.anime}`.toLocaleLowerCase('pt-BR').includes(needle));
  }, [query.data, search]);

  useEffect(() => {
    if (nativeParams().get('section') === 'favorite') document.querySelector('[data-favorite-settings]')?.scrollIntoView({ block: 'start' });
  }, []);

  const save = async (character: FavoriteCharacter | null) => {
    const result = await run('favorite', () => sourcePost('/api/menu/favorite', {
      character_id: character?.id ?? null,
    }), character ? 'Personagem favorito atualizado.' : 'Favorito removido.');
    if (!result) return;
    const favorite = 'favorite' in result ? result.favorite : character;
    patchUser({ favorite });
    cache.setQueryData(['source', user?.id || 0, '/api/menu/profile'], (old: any) => old ? {
      ...old, profile: { ...old.profile, favorite },
    } : old);
    setOpen(false);
  };

  return (
    <Card className="p-4 sm:p-5 space-y-4 scroll-mt-4" data-favorite-settings>
      <div className="flex items-center gap-2">
        <Heart size={16} className="text-brand-accent shrink-0" />
        <h2 className="text-xs font-bold uppercase text-zinc-100">Personagem favorito</h2>
      </div>
      {current ? <div className="flex gap-4 items-center">
        {current.image && <img src={current.image} alt={current.name} decoding="async" referrerPolicy="no-referrer"
          className="w-16 aspect-[2/3] object-cover rounded-md shrink-0" />}
        <div className="min-w-0">
          <p className="text-sm font-bold text-zinc-100 break-words">{current.name}</p>
          <p className="text-xs text-zinc-400 break-words">{current.anime}</p>
        </div>
      </div> : <p className="text-sm text-zinc-400">Nenhum favorito definido.</p>}
      <p className="text-xs text-zinc-500 leading-relaxed">Escolha alguém da sua coleção para destacar no painel e no seu perfil do bot.</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <Button variant="secondary" disabled={Boolean(pending)} onClick={() => {
          setSearch(''); setVisible(24); setOpen(true);
        }} leftIcon={<Heart size={14} />}>{current ? 'Alterar favorito' : 'Escolher favorito'}</Button>
        {current && <Button variant="ghost" disabled={Boolean(pending)} isLoading={Boolean(pending)}
          onClick={() => save(null)} leftIcon={<Trash2 size={14} />}>Remover favorito</Button>}
      </div>
      {open && <Dialog title="Escolher personagem favorito" onClose={() => setOpen(false)} busy={Boolean(pending)}>
        <Input icon={Search} aria-label="Buscar personagem favorito" placeholder="Personagem ou obra..."
          value={search} onChange={(e) => { setSearch(e.target.value); setVisible(24); }} autoComplete="off" />
        <QueryFeedback loading={query.isPending} error={query.error} retry={query.refetch} />
        {!query.isPending && !query.error && !matches.length && <p role="status" className="text-sm text-zinc-400">
          {query.data?.items.length ? 'Nenhum personagem corresponde à busca.' : 'Sua coleção ainda está vazia. Capture um personagem para escolher seu favorito.'}
        </p>}
        <div className="grid grid-cols-1 gap-2">
          {matches.slice(0, visible).map((character) => <button key={character.id} type="button"
            aria-label={`Favoritar ${character.name}`} aria-pressed={current?.id === character.id}
            disabled={Boolean(pending)} onClick={() => save(character)}
            className="flex items-center gap-3 w-full min-w-0 p-3 text-left rounded-md border border-white/10 bg-zinc-900 hover:border-brand-accent disabled:opacity-50">
            <img src={character.image} alt="" loading="lazy" decoding="async" referrerPolicy="no-referrer"
              className="w-12 aspect-[2/3] rounded object-cover shrink-0" />
            <span className="min-w-0 flex-1"><span className="block text-sm font-bold text-zinc-100 break-words">{character.name}</span>
              <span className="block text-xs text-zinc-500 break-words">{character.anime}</span></span>
            <Heart size={18} className={`shrink-0 ${current?.id === character.id ? 'text-brand-accent fill-brand-accent' : 'text-zinc-500'}`} />
          </button>)}
        </div>
        {matches.length > visible && <Button variant="secondary" className="w-full" onClick={() => setVisible((n) => n + 24)}>Mostrar mais personagens</Button>}
      </Dialog>}
    </Card>
  );
}
