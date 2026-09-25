import { Coins, Search, Settings2, Store } from 'lucide-react';
import { useState } from 'react';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { sourcePost, useDebounced, useSourceAction, useSourceQuery, queryUrl } from './api';
import { navigateNative, nativeParams } from './navigation';
import {
  Choices,
  Cover,
  Dialog,
  Field,
  More,
  NativePage,
  Poster,
  PosterGrid,
  QueryFeedback,
} from './ui';
import { Shop as DailyShop } from '../pages/Shop';
import type { Character } from '../context/UserContext';

export function NicknameForm({ paid = false }: { paid?: boolean }) {
  const [nickname, setNickname] = useState('');
  const [confirm, setConfirm] = useState(false);
  const { pending, run } = useSourceAction();
  const config = useSourceQuery('/api/native/config');
  const price = config.data?.nickname_price;
  const valid = /^[A-Z][A-Za-z0-9_]{3,16}$/.test(nickname);
  const submit = async () => {
    const result = await run(
      'nickname',
      () => sourcePost(paid ? '/api/native/nickname' : '/api/menu/nickname', { nickname }),
      'Nickname atualizado.',
    );
    if (result) {
      setNickname('');
      setConfirm(false);
    }
  };
  return (
    <Card className="p-5 space-y-4">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) {
            if (paid) setConfirm(true);
            else void submit();
          }
        }}
      >
        <Field label="Novo nickname">
          <Input
            aria-label="Novo nickname"
            required
            pattern="[A-Z][A-Za-z0-9_]{3,16}"
            minLength={4}
            maxLength={17}
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
            placeholder="SeuNome"
            autoComplete="off"
          />
        </Field>
        <p className="text-xs text-zinc-500 leading-relaxed">
          De 4 a 17 caracteres, começando com letra maiúscula. Letras, números e sublinhado.{' '}
          {paid
            ? 'A cobrança só é realizada se a alteração for concluída.'
            : 'A primeira definição é gratuita.'}
        </p>
        <Button
          type="submit"
          disabled={!valid || Boolean(pending) || (paid && price === undefined)}
          isLoading={Boolean(pending)}
          leftIcon={<Settings2 size={14} />}
        >
          {paid ? `Alterar por ${price ?? '—'} coins` : 'Definir nickname'}
        </Button>
      </form>
      {paid && config.error && (
        <QueryFeedback loading={false} error={config.error} retry={config.refetch} />
      )}
      {confirm && (
        <Dialog
          title="Confirmar alteração"
          onClose={() => setConfirm(false)}
          busy={Boolean(pending)}
        >
          <p className="text-sm text-zinc-400">
            Usar <strong className="text-zinc-100">{price} coins</strong> para alterar seu nickname
            para <strong className="text-zinc-100">{nickname}</strong>?
          </p>
          <Button
            className="w-full"
            isLoading={Boolean(pending)}
            disabled={Boolean(pending)}
            onClick={submit}
          >
            Confirmar e alterar
          </Button>
        </Dialog>
      )}
    </Card>
  );
}
function SellCharacters() {
  const [text, setText] = useState(''),
    [selected, setSelected] = useState<any>(null),
    [visible, setVisible] = useState(40);
  const q = useDebounced(text),
    { pending, run } = useSourceAction();
  const query = useSourceQuery(queryUrl('/api/shop/sell/all', { q }));
  const config = useSourceQuery('/api/native/config');
  const items = query.data?.items || [],
    price = config.data?.sell_price;
  const sell = async () => {
    if (!selected) return;
    const result = await run(
      'sell',
      () => sourcePost('/api/shop/sell/confirm', { character_id: Number(selected.character_id) }),
      'Personagem vendido.',
    );
    if (result) setSelected(null);
  };
  return (
    <NativePage
      title="Vender personagens"
      subtitle="Troque uma cópia da sua coleção por coins"
      icon={Coins}
    >
      <Input
        icon={Search}
        aria-label="Buscar personagem para vender"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setVisible(40);
        }}
        placeholder="Nome do personagem ou obra..."
        maxLength={80}
      />
      <QueryFeedback
        loading={query.isPending}
        error={query.error || config.error}
        retry={() => {
          void config.refetch();
          void query.refetch();
        }}
        empty={!items.length}
      />
      <PosterGrid>
        {items.slice(0, visible).map((item: any) => (
          <Poster
            key={item.character_id}
            title={item.character_name}
            src={item.image}
            subtitle={`${item.quantity} cópia(s) · ${item.anime_title}`}
            onClick={() => setSelected(item)}
          />
        ))}
      </PosterGrid>
      <More
        show={visible < items.length}
        pending={false}
        onClick={() => setVisible((n) => n + 40)}
      />
      {selected && (
        <Dialog title="Confirmar venda" onClose={() => setSelected(null)} busy={Boolean(pending)}>
          <Cover
            src={selected.image}
            name={selected.character_name}
            className="w-32 mx-auto rounded-md"
          />
          <p className="text-sm text-zinc-400">
            Vender <strong className="text-zinc-100">uma cópia de {selected.character_name}</strong>{' '}
            por {price ?? '—'} coin(s)? Ela será removida da sua coleção.
          </p>
          <Button
            className="w-full"
            disabled={Boolean(pending) || price === undefined}
            isLoading={Boolean(pending)}
            onClick={sell}
          >
            Vender uma cópia
          </Button>
          <Button
            className="w-full"
            variant="secondary"
            disabled={Boolean(pending)}
            onClick={() => setSelected(null)}
          >
            Cancelar
          </Button>
        </Dialog>
      )}
    </NativePage>
  );
}
export function Shop({ onCharClick }: { onCharClick: (character: Character) => void }) {
  const section = nativeParams().get('section') || 'daily';
  return (
    <>
      <div className="pt-5 adaptive-px max-w-5xl mx-auto">
        <Choices
          value={section}
          items={[
            ['daily', 'Loja diária'],
            ['sell', 'Vender'],
            ['nickname', 'Nickname'],
          ]}
          onChange={(s) => navigateNative('shop', { section: s })}
        />
      </div>
      {section === 'sell' ? (
        <SellCharacters />
      ) : section === 'nickname' ? (
        <NativePage title="Alterar nickname" subtitle="Personalize seu nome no Source" icon={Store}>
          <NicknameForm paid />
        </NativePage>
      ) : (
        <DailyShop onCharClick={onCharClick} />
      )}
    </>
  );
}
