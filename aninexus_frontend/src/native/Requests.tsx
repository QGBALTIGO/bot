import { FileCheck2, Flag, ImagePlus, Search, Send, Shapes } from 'lucide-react';
import { useState } from 'react';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { Badge } from '../components/ui/Badge';
import { useUser } from '../context/UserContext';
import { queryUrl, sourcePost, useDebounced, useSourceAction, useSourceQuery } from './api';
import { nativeParams, navigateNative } from './navigation';
import {
  Choices,
  Cover,
  Dialog,
  Field,
  fieldClass,
  NativePage,
  Poster,
  PosterGrid,
  QueryFeedback,
} from './ui';

interface Result {
  id: number;
  title: string;
  cover?: string;
  year?: number;
  format?: string;
  already_exists?: boolean;
  already_requested?: boolean;
}
function RequireTelegram() {
  return (
    <Card className="p-5 text-sm text-zinc-400">
      Abra esta tela pelo bot no Telegram para enviar sua contribuição com segurança.
    </Card>
  );
}

export function RequestSearch({ contribution = false }: { contribution?: boolean }) {
  const [type, setType] = useState('anime');
  const [text, setText] = useState(nativeParams().get('q') || '');
  const [selected, setSelected] = useState<Result | null>(null);
  const q = useDebounced(text),
    { user } = useUser(),
    { pending, run } = useSourceAction();
  const limit = useSourceQuery('/api/pedido/limit', Boolean(user) && !contribution);
  const query = useSourceQuery<{ items: Result[] }>(
    queryUrl(contribution ? '/api/cards/contrib/work/search' : '/api/pedido/search', {
      q,
      media_type: type,
    }),
    Boolean(user) && q.length >= 2,
  );
  const submit = async () => {
    if (!selected) return;
    const body = contribution
      ? {
          media_type: type,
          anilist_id: selected.id,
          title: selected.title,
          cover_url: selected.cover || '',
        }
      : {
          media_type: type,
          anilist_id: selected.id,
          title: selected.title,
          cover: selected.cover || '',
        };
    const result = await run(
      'submit',
      () => sourcePost(contribution ? '/api/cards/contrib/work' : '/api/pedido/send', body),
      'Solicitação enviada para análise.',
    );
    if (result) setSelected(null);
  };
  if (!user) return <RequireTelegram />;
  return (
    <div className="space-y-5">
      <Choices
        value={type}
        items={[
          ['anime', 'Anime'],
          ['manga', 'Mangá'],
        ]}
        onChange={setType}
      />
      {!contribution && (
        <>
          <QueryFeedback loading={limit.isPending} error={limit.error} retry={limit.refetch} />
          {limit.data && (
            <p className="text-[10px] text-zinc-400 font-mono">
              {limit.data.remaining} de {limit.data.limit} pedidos disponíveis hoje
            </p>
          )}
        </>
      )}
      <Input
        icon={Search}
        aria-label="Buscar obra para solicitar"
        placeholder="Nome original ou alternativo da obra..."
        value={text}
        onChange={(e) => setText(e.target.value)}
        minLength={2}
        maxLength={80}
      />
      {q.length < 2 ? (
        <p className="text-xs text-zinc-500">Digite ao menos dois caracteres.</p>
      ) : (
        <>
          <QueryFeedback
            loading={query.isPending}
            error={query.error}
            retry={query.refetch}
            empty={!query.data?.items.length}
          />
          <PosterGrid>
            {query.data?.items.map((item) => (
              <Poster
                key={item.id}
                src={item.cover}
                title={item.title}
                subtitle={[item.format, item.year].filter(Boolean).join(' · ')}
                onClick={() => setSelected(item)}
              >
                <Badge variant="secondary">
                  {item.already_exists
                    ? 'No catálogo'
                    : item.already_requested
                      ? 'Já solicitado'
                      : 'Disponível para pedir'}
                </Badge>
              </Poster>
            ))}
          </PosterGrid>
        </>
      )}
      {selected && (
        <Dialog title={selected.title} onClose={() => setSelected(null)} busy={Boolean(pending)}>
          <Cover src={selected.cover} name={selected.title} className="w-36 mx-auto rounded-md" />
          <p className="text-xs text-zinc-400">
            {selected.already_exists
              ? 'Esta obra já está no catálogo.'
              : selected.already_requested
                ? 'Esta obra já tem uma solicitação pendente.'
                : 'Confirme o envio desta obra para análise da equipe.'}
          </p>
          <Button
            className="w-full"
            disabled={
              Boolean(pending) ||
              selected.already_exists ||
              selected.already_requested ||
              (!contribution && Number(limit.data?.remaining ?? 0) <= 0)
            }
            isLoading={Boolean(pending)}
            onClick={submit}
            leftIcon={<Send size={14} />}
          >
            Confirmar solicitação
          </Button>
        </Dialog>
      )}
    </div>
  );
}

function Report() {
  const [type, setType] = useState('Link quebrado'),
    [text, setText] = useState('');
  const { pending, run } = useSourceAction();
  return (
    <Card className="p-5">
      <form
        className="space-y-4"
        onSubmit={async (e) => {
          e.preventDefault();
          const result = await run(
            'report',
            () => sourcePost('/api/pedido/report', { report_type: type, message: text.trim() }),
            'Problema enviado para a equipe.',
          );
          if (result) setText('');
        }}
      >
        <Field label="Tipo de problema">
          <select className={fieldClass} value={type} onChange={(e) => setType(e.target.value)}>
            {[
              'Link quebrado',
              'Informação incorreta',
              'Imagem incorreta',
              'Erro no aplicativo',
              'Outro',
            ].map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </Field>
        <Field label="Descrição">
          <textarea
            className={fieldClass}
            required
            minLength={5}
            maxLength={3000}
            rows={5}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Informe a obra, o problema e como reproduzir..."
          />
        </Field>
        <Button
          type="submit"
          isLoading={Boolean(pending)}
          disabled={Boolean(pending) || text.trim().length < 5}
          leftIcon={<Flag size={14} />}
        >
          Enviar relato
        </Button>
      </form>
    </Card>
  );
}
export function Requests() {
  const [view, setView] = useState('request');
  const { user } = useUser();
  return (
    <NativePage
      title="Central de pedidos"
      subtitle="Solicite obras ou avise sobre um problema"
      icon={Send}
    >
      <Choices
        value={view}
        items={[
          ['request', 'Pedir obra'],
          ['report', 'Reportar problema'],
        ]}
        onChange={setView}
      />
      {!user ? <RequireTelegram /> : view === 'request' ? <RequestSearch /> : <Report />}
    </NativePage>
  );
}

function ImageContribution() {
  const params = nativeParams(),
    { user } = useUser();
  const [text, setText] = useState(params.get('q') || ''),
    [selected, setSelected] = useState<any>(null);
  const [url, setUrl] = useState(''),
    [note, setNote] = useState('');
  const q = useDebounced(text),
    { pending, run } = useSourceAction();
  const query = useSourceQuery(queryUrl('/api/cards/search', { q, limit: 100 }), q.length >= 1);
  const choose = (item: any) => {
    setSelected(item);
    setUrl('');
    setNote('');
  };
  const results = query.data?.items || [];
  const target =
    selected ||
    (text === (params.get('q') || '') &&
      results.find((item: any) => String(item.id) === params.get('character_id')));
  if (!user) return <RequireTelegram />;
  return (
    <div className="space-y-5">
      <Input
        icon={Search}
        aria-label="Buscar personagem para contribuir"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setSelected(null);
        }}
        placeholder="Encontre o personagem..."
        maxLength={80}
      />
      {q && (
        <QueryFeedback
          loading={query.isPending}
          error={query.error}
          retry={query.refetch}
          empty={!results.length}
        />
      )}
      {!target && (
        <PosterGrid>
          {results.map((item: any) => (
            <Poster
              key={item.id}
              src={item.image}
              title={item.name}
              subtitle={item.anime}
              onClick={() => choose(item)}
            />
          ))}
        </PosterGrid>
      )}
      {target && (
        <Card className="p-5">
          <form
            className="space-y-4"
            onSubmit={async (e) => {
              e.preventDefault();
              const parsed = new URL(url);
              if (!['http:', 'https:'].includes(parsed.protocol)) return;
              const result = await run(
                'image',
                () =>
                  sourcePost('/api/cards/contrib/image', {
                    character_id: Number(target.id),
                    suggested_image_url: url.trim(),
                    note: note.trim(),
                  }),
                'Imagem enviada para revisão.',
              );
              if (result) {
                setUrl('');
                setNote('');
              }
            }}
          >
            <div className="flex items-center gap-4">
              <Cover src={target.image} name={target.name} className="w-20 shrink-0 rounded-md" />
              <div>
                <h2 className="font-bold text-sm text-zinc-100">{target.name}</h2>
                <p className="text-xs text-zinc-500 mt-1">{target.anime}</p>
              </div>
            </div>
            <Field label="Endereço público da imagem 2:3">
              <Input
                type="url"
                pattern="https?://.+"
                required
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://..."
                maxLength={2048}
              />
            </Field>
            <Field label="Observação opcional">
              <textarea
                className={fieldClass}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                maxLength={1000}
                rows={3}
              />
            </Field>
            <p className="text-xs text-zinc-500">
              A imagem será avaliada antes de substituir a atual. Não envie conteúdo sexualizado,
              montagens ou marcas-d'água.
            </p>
            <Button
              type="submit"
              disabled={Boolean(pending) || !url.trim()}
              isLoading={Boolean(pending)}
            >
              Enviar imagem
            </Button>
          </form>
        </Card>
      )}
    </div>
  );
}
export function Contribute() {
  const view = nativeParams().get('view') || 'image';
  return (
    <NativePage
      title="Contribuições"
      subtitle="Ajude a melhorar o acervo de cards"
      icon={ImagePlus}
    >
      <Choices
        value={view}
        items={[
          ['image', 'Imagem'],
          ['work', 'Obra'],
          ['rules', 'Regras'],
        ]}
        onChange={(v) => navigateNative('contribute', { view: v })}
      />
      {view === 'work' ? (
        <RequestSearch contribution />
      ) : view === 'rules' ? (
        <div className="space-y-3">
          {[
            [
              'Formato vertical 2:3',
              'Use uma imagem vertical de alta qualidade, com o personagem bem enquadrado e sem cortes importantes.',
            ],
            [
              'Fidelidade ao personagem',
              'A arte deve representar o personagem correto, sozinho, com rosto e características reconhecíveis.',
            ],
            [
              'Imagem limpa',
              'Não use textos, marcas-d’água, bordas exageradas, colagens ou elementos que escondam o personagem. Não envie conteúdo sexualizado.',
            ],
            [
              'Revisão da equipe',
              'As sugestões passam por avaliação. Uma imagem aprovada poderá substituir a atual no acervo. Recompensas seguem as regras configuradas pela administração.',
            ],
          ].map(([title, text]) => (
            <Card key={title} className="p-5 space-y-2">
              <h2 className="text-xs font-bold text-zinc-100 uppercase flex items-center gap-2">
                <FileCheck2 size={14} />
                {title}
              </h2>
              <p className="text-sm text-zinc-400 leading-relaxed">{text}</p>
            </Card>
          ))}
        </div>
      ) : (
        <ImageContribution />
      )}
      <Button
        variant="ghost"
        leftIcon={<Shapes size={14} />}
        onClick={() => navigateNative('cards')}
      >
        Explorar cards
      </Button>
    </NativePage>
  );
}
