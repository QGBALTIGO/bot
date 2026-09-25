import type { Listing, MarketAction } from './contracts.generated';
import { Gavel, Plus, Store } from 'lucide-react';
import { useState } from 'react';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import {
  Choices,
  Dialog,
  Field,
  NativePage,
  Poster,
  PosterGrid,
  QueryFeedback,
  fieldClass,
} from '../../native/ui';
import { type CollectionCard, useFeatureAction, useFeatureQuery } from './api';
import { Picker } from './Picker';
interface Offer {
  id: string;
  character: CollectionCard;
  quantity: number;
  kind: 'fixed' | 'auction';
  price: number;
  bid: number;
  minimum_bid: number;
  status: string;
  ends_at: string;
  version: number;
  is_owner: boolean;
  is_highest_bidder: boolean;
  seller_name: string;
}
const date = (s: string) =>
  new Date(s).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
export function Marketplace() {
  const [mode, setMode] = useState('all'),
    [page, setPage] = useState(0),
    [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<CollectionCard | null>(null),
    [kind, setKind] = useState<'fixed' | 'auction'>('fixed'),
    [quantity, setQuantity] = useState(1),
    [price, setPrice] = useState(1),
    [hours, setHours] = useState(24);
  const [confirm, setConfirm] = useState<{ offer: Offer; action: 'buy' | 'bid' | 'cancel' } | null>(
      null,
    ),
    [bid, setBid] = useState(1);
  const { perform, pending } = useFeatureAction(),
    query = useFeatureQuery<{ items: Offer[]; has_more: boolean }>(
      `/market?mine=${mode === 'mine'}&offset=${page * 24}`,
    );
  const review = (offer: Offer, action: 'buy' | 'bid' | 'cancel') => {
    setBid(offer.minimum_bid);
    setConfirm({ offer, action });
  };
  const labels: Record<string, string> = {
    active: 'Ativo',
    sold: 'Concluído',
    cancelled: 'Cancelado',
    expired: 'Expirado',
  };
  return (
    <NativePage
      title="Mercado"
      subtitle="Negocie personagens com Coins. Confira os valores antes de confirmar."
      icon={Store}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Choices
          value={mode}
          items={[
            ['all', 'Anúncios'],
            ['mine', 'Meus anúncios'],
          ]}
          onChange={(v) => {
            setMode(v);
            setPage(0);
          }}
        />
        <Button
          size="sm"
          leftIcon={<Plus size={14} />}
          onClick={() => {
            setSelected(null);
            setQuantity(1);
            setPrice(1);
            setCreating(true);
          }}
        >
          Criar anúncio
        </Button>
      </div>
      <Card className="p-4">
        <p className="text-xs text-zinc-400 leading-relaxed">
          O valor anunciado é o total do lote. Em leilões, os Coins do maior lance ficam reservados;
          se alguém superar você, o valor retorna ao saldo. Não há dinheiro real nesta negociação.
        </p>
      </Card>
      <QueryFeedback loading={query.isPending} error={query.error} retry={query.refetch} />
      <PosterGrid>
        {query.data?.items.map((offer) => {
          const ended = new Date(offer.ends_at).getTime() <= Date.now();
          return (
            <Poster
              key={offer.id}
              src={offer.character.image}
              title={offer.character.name}
              subtitle={`${offer.quantity} cópia(s) · ${offer.seller_name}`}
            >
              <div className="space-y-3">
                <p className="text-sm font-mono text-zinc-100">
                  {offer.kind === 'auction' ? Math.max(offer.price, offer.bid) : offer.price} Coins
                </p>
                <p className="text-[10px] text-zinc-500">
                  {offer.kind === 'auction' ? 'Leilão' : 'Preço fixo'} ·{' '}
                  {labels[offer.status] || offer.status}
                  <br />
                  Encerra: {date(offer.ends_at)}
                </p>
                {offer.is_highest_bidder && (
                  <p className="text-[10px] text-brand-accent">Seu lance está na frente</p>
                )}
                {offer.status === 'active' && (
                  <div className="flex flex-col gap-2">
                    {ended ? (
                      <Button
                        size="sm"
                        disabled={pending || !(offer.is_owner || offer.is_highest_bidder)}
                        onClick={() =>
                          void perform(
                            `/market/${offer.id}/settle`,
                            {},
                            { economic: true, success: 'Anúncio concluído.' },
                          )
                        }
                      >
                        Concluir anúncio
                      </Button>
                    ) : offer.is_owner ? (
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={pending || offer.bid > 0}
                        onClick={() => review(offer, 'cancel')}
                      >
                        {offer.bid > 0 ? 'Aguardando encerramento' : 'Cancelar anúncio'}
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        disabled={pending}
                        onClick={() => review(offer, offer.kind === 'auction' ? 'bid' : 'buy')}
                      >
                        {offer.kind === 'auction' ? 'Oferecer lance' : 'Revisar compra'}
                      </Button>
                    )}
                  </div>
                )}
              </div>
            </Poster>
          );
        })}
      </PosterGrid>
      {query.data && !query.data.items.length && (
        <p className="text-sm text-zinc-500">
          Nenhum anúncio nesta seleção. Crie o primeiro usando suas duplicatas.
        </p>
      )}
      <div className="flex justify-between">
        <Button
          size="sm"
          variant="secondary"
          disabled={!page}
          onClick={() => setPage((x) => x - 1)}
        >
          Anterior
        </Button>
        <Button
          size="sm"
          variant="secondary"
          disabled={!query.data?.has_more}
          onClick={() => setPage((x) => x + 1)}
        >
          Próxima
        </Button>
      </div>
      {creating && (
        <Dialog title="Novo anúncio" busy={pending} onClose={() => setCreating(false)}>
          {!selected ? (
            <Picker onSelect={setSelected} />
          ) : (
            <div className="space-y-4">
              <p className="text-sm font-bold text-zinc-200">
                {selected.name} · {selected.quantity} cópia(s)
              </p>
              <Button size="sm" variant="ghost" onClick={() => setSelected(null)}>
                Escolher outro personagem
              </Button>
              <Choices
                value={kind}
                items={[
                  ['fixed', 'Preço fixo'],
                  ['auction', 'Leilão'],
                ]}
                onChange={(v) => setKind(v as 'fixed' | 'auction')}
              />
              <div className="grid grid-cols-2 gap-3">
                <Field label="Cópias no lote">
                  <input
                    type="number"
                    className={fieldClass}
                    min={1}
                    max={Math.min(20, selected.quantity)}
                    value={quantity}
                    onChange={(e) => setQuantity(Number(e.target.value))}
                  />
                </Field>
                <Field label={kind === 'auction' ? 'Lance inicial (Coins)' : 'Preço total (Coins)'}>
                  <input
                    type="number"
                    className={fieldClass}
                    min={1}
                    max={100000}
                    value={price}
                    onChange={(e) => setPrice(Number(e.target.value))}
                  />
                </Field>
              </div>
              <Field label="Duração">
                <select
                  className={fieldClass}
                  value={hours}
                  onChange={(e) => setHours(Number(e.target.value))}
                >
                  {[1, 6, 12, 24, 48, 72].map((n) => (
                    <option value={n} key={n}>
                      {n} hora(s)
                    </option>
                  ))}
                </select>
              </Field>
              <p className="text-xs text-zinc-500">
                O personagem ficará reservado até a conclusão ou o cancelamento. Por padrão, uma
                cópia fica na coleção. Um leilão com lances não pode ser cancelado.
              </p>
              <Button
                className="w-full"
                isLoading={pending}
                disabled={
                  !Number.isInteger(price) ||
                  price < 1 ||
                  price > 100000 ||
                  !Number.isInteger(quantity) ||
                  quantity < 1 ||
                  quantity > Math.min(20, selected.quantity)
                }
                onClick={async () => {
                  const ok = await perform(
                    '/market',
                    { character_id: selected.id, quantity, kind, price, hours } satisfies Omit<
                      Listing,
                      'request_id'
                    >,
                    { idempotent: true, success: 'Anúncio publicado.' },
                  );
                  if (ok) setCreating(false);
                }}
              >
                Confirmar anúncio
              </Button>
            </div>
          )}
        </Dialog>
      )}
      {confirm && (
        <Dialog
          title={
            confirm.action === 'cancel'
              ? 'Cancelar anúncio'
              : confirm.action === 'bid'
                ? 'Confirmar lance'
                : 'Confirmar compra'
          }
          busy={pending}
          onClose={() => setConfirm(null)}
        >
          <p className="text-sm text-zinc-200">
            {confirm.offer.character.name} × {confirm.offer.quantity}
          </p>
          {confirm.action === 'bid' ? (
            <>
              <Field label={`Seu lance · mínimo ${confirm.offer.minimum_bid} Coins`}>
                <input
                  className={fieldClass}
                  type="number"
                  min={confirm.offer.minimum_bid}
                  max={100000}
                  value={bid}
                  onChange={(e) => setBid(Number(e.target.value))}
                />
              </Field>
              <p className="text-xs text-zinc-500">
                Esse valor ficará em garantia. Lances no final podem estender o leilão em até dez
                minutos além do prazo original.
              </p>
            </>
          ) : (
            <p className="text-sm text-zinc-400">
              {confirm.action === 'buy'
                ? `Você paga ${confirm.offer.price} Coins pelo lote completo.`
                : 'O personagem será liberado da reserva. Não há cobrança para cancelar.'}
            </p>
          )}
          <Button
            className="w-full"
            isLoading={pending}
            disabled={
              confirm.action === 'bid' &&
              (!Number.isInteger(bid) || bid < confirm.offer.minimum_bid || bid > 100000)
            }
            variant={confirm.action === 'cancel' ? 'danger' : 'primary'}
            onClick={async () => {
              const ok = await perform(
                `/market/${confirm.offer.id}/action`,
                {
                  action: confirm.action,
                  version: confirm.offer.version,
                  amount: confirm.action === 'bid' ? bid : 0,
                } satisfies Omit<MarketAction, 'request_id'>,
                { idempotent: true, economic: true, success: 'Operação confirmada.' },
              );
              if (ok) setConfirm(null);
              else {
                setConfirm(null);
                void query.refetch();
              }
            }}
          >
            Confirmar{' '}
            {confirm.action === 'bid'
              ? 'lance'
              : confirm.action === 'buy'
                ? 'compra'
                : 'cancelamento'}
          </Button>
        </Dialog>
      )}
    </NativePage>
  );
}
