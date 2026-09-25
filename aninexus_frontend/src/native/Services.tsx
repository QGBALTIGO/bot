import { Check, CreditCard, ExternalLink, ShieldCheck } from 'lucide-react';
import { useRef, useState } from 'react';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { getErrorMessage } from '../api/client';
import { useToast } from '../components/ui/Toast';
import { nativeParams, navigateNative, openExternal } from './navigation';
import { sourcePost, useSourceQuery, queryUrl } from './api';
import { Choices, Dialog, NativePage, QueryFeedback } from './ui';

export function Subscription() {
  const config = useSourceQuery('/api/native/config');
  const [selected, setSelected] = useState<any>(null),
    [checkout, setCheckout] = useState<any>(null),
    [pending, setPending] = useState(false);
  const busy = useRef(false),
    { addToast } = useToast();
  const createIntent = async () => {
    if (!selected || busy.current) return;
    busy.current = true;
    setPending(true);
    try {
      const result = await sourcePost('/api/baltigoflix/create-intent', {
        plan_code: selected.code,
      });
      const url = new URL(result.checkout_url);
      if (url.protocol !== 'https:') throw new Error('Endereço de pagamento inválido.');
      setCheckout({ ...result, checkout_url: url.href });
      setSelected(null);
    } catch (error) {
      addToast(getErrorMessage(error), 'error');
    } finally {
      busy.current = false;
      setPending(false);
    }
  };
  const format = (cents: number) =>
    new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(cents / 100);
  return (
    <NativePage title="BaltigoFlix" subtitle="Planos e assinatura" icon={CreditCard}>
      {nativeParams().get('pending') && (
        <Card className="p-5 text-sm text-zinc-400">
          O pagamento é confirmado pelo provedor. Esta tela não comprova aprovação. Consulte a
          mensagem de confirmação recebida no bot.
        </Card>
      )}
      <QueryFeedback loading={config.isPending} error={config.error} retry={config.refetch} />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {config.data?.plans?.map((plan: any) => (
          <Card key={plan.code} className="p-5 space-y-5">
            <h2 className="text-xs font-bold uppercase tracking-widest text-zinc-300">
              {plan.name}
            </h2>
            <p className="text-3xl font-mono font-bold text-zinc-100">
              {format(plan.amount_cents)}
            </p>
            <Button
              className="w-full"
              variant="secondary"
              onClick={() => {
                setCheckout(null);
                setSelected(plan);
              }}
            >
              Escolher plano
            </Button>
          </Card>
        ))}
      </div>
      {checkout && (
        <Card className="p-5 space-y-4">
          <h2 className="text-sm font-bold text-zinc-100">Pedido criado</h2>
          <p className="text-sm text-zinc-400">
            {checkout.plan_name} · {format(checkout.amount_cents)}. Continue no ambiente de
            pagamento. O acesso depende da confirmação do provedor.
          </p>
          <Button
            leftIcon={<ExternalLink size={14} />}
            onClick={() => openExternal(checkout.checkout_url)}
          >
            Continuar para pagamento
          </Button>
        </Card>
      )}
      {selected && (
        <Dialog title={selected.name} onClose={() => setSelected(null)} busy={pending}>
          <p className="text-sm text-zinc-400">
            Valor: <strong className="text-zinc-100">{format(selected.amount_cents)}</strong>. Ao
            continuar, um pedido será vinculado à sua conta do Telegram. Nenhum pagamento é
            realizado automaticamente.
          </p>
          <Button
            className="w-full"
            isLoading={pending}
            disabled={pending || !window.Telegram?.WebApp?.initData}
            onClick={createIntent}
          >
            Criar pedido
          </Button>
          {!window.Telegram?.WebApp?.initData && (
            <p className="text-xs text-zinc-500">Abra pelo bot no Telegram para continuar.</p>
          )}
        </Dialog>
      )}
    </NativePage>
  );
}
export function Terms() {
  const lang = nativeParams().get('lang') || 'pt';
  const config = useSourceQuery(queryUrl('/api/native/config', { lang }));
  const [privacy, setPrivacy] = useState(false),
    [terms, setTerms] = useState(false),
    [verified, setVerified] = useState(false),
    [pending, setPending] = useState(''),
    [done, setDone] = useState('');
  const busy = useRef(false),
    { addToast } = useToast();
  const t = config.data?.texts || {},
    signed = Boolean(window.Telegram?.WebApp?.initData);
  const perform = async (action: 'check' | 'accept' | 'decline') => {
    if (busy.current || !signed) return;
    if (action === 'accept' && (!privacy || !terms || !verified)) return;
    busy.current = true;
    setPending(action);
    try {
      const result = await sourcePost(
        action === 'check' ? '/api/channel/check' : `/api/terms/${action}`,
        { lang },
      );
      if (action === 'check') {
        setVerified(true);
        addToast(t.verify_ok || 'Inscrição confirmada.', 'success');
      } else {
        setDone(action);
        addToast(result.message || t.done, 'success');
      }
    } catch (error) {
      addToast(getErrorMessage(error), 'error');
    } finally {
      busy.current = false;
      setPending('');
    }
  };
  return (
    <NativePage
      title={t.title || 'Termos de uso e privacidade'}
      subtitle={t.subtitle || 'Source Baltigo'}
      icon={ShieldCheck}
    >
      <Choices
        value={lang}
        items={[
          ['pt', 'Português'],
          ['en', 'English'],
          ['es', 'Español'],
        ]}
        onChange={(l) => navigateNative('terms', { lang: l })}
      />
      <QueryFeedback loading={config.isPending} error={config.error} retry={config.refetch} />
      {config.data && (
        <>
          <p className="text-sm text-zinc-400">{t.intro}</p>
          {config.data.terms.map((s: any) => (
            <Card className="p-5 space-y-3" key={s.title}>
              <h2 className="text-xs text-zinc-100 font-bold uppercase tracking-widest">
                {s.title}
              </h2>
              <p className="text-sm text-zinc-400 leading-relaxed">{s.text}</p>
            </Card>
          ))}
          {done ? (
            <Card className="p-5 space-y-4">
              <p role="status" className="text-sm text-zinc-300">
                {done === 'accept' ? t.done : t.no}
              </p>
              <Button onClick={() => window.Telegram?.WebApp?.close?.()}>Voltar ao Telegram</Button>
            </Card>
          ) : (
            <>
              <Card className="p-5 space-y-4">
                <h2 className="text-xs uppercase font-bold text-zinc-100">{t.join_title}</h2>
                <p className="text-sm text-zinc-400">{t.join_text}</p>
                <div className="flex flex-wrap gap-3">
                  <Button variant="secondary" onClick={() => openExternal(config.data.channel_url)}>
                    {t.join_button}
                  </Button>
                  <Button
                    disabled={!signed || Boolean(pending) || verified}
                    isLoading={pending === 'check'}
                    onClick={() => perform('check')}
                    leftIcon={verified ? <Check size={14} /> : undefined}
                  >
                    {verified ? t.verify_confirmed : t.verify_button}
                  </Button>
                </div>
              </Card>
              <Card className="p-5 space-y-4">
                {[
                  [privacy, setPrivacy, t.check1],
                  [terms, setTerms, t.check2],
                ].map(([value, setter, label], index) => (
                  <label
                    className="flex items-start gap-3 text-sm text-zinc-300 cursor-pointer"
                    key={index}
                  >
                    <input
                      className="mt-0.5 w-4 h-4 accent-blue-500"
                      type="checkbox"
                      checked={Boolean(value)}
                      onChange={(e) => (setter as (v: boolean) => void)(e.target.checked)}
                    />
                    {String(label)}
                  </label>
                ))}
              </Card>
              {!signed && (
                <p className="text-sm text-zinc-500">
                  Leia os termos aqui e abra a MiniApp pelo Telegram para aceitar.
                </p>
              )}
              <div className="flex flex-wrap gap-3">
                <Button
                  disabled={!signed || !privacy || !terms || !verified || Boolean(pending)}
                  isLoading={pending === 'accept'}
                  onClick={() => perform('accept')}
                >
                  {t.accept}
                </Button>
                <Button
                  variant="secondary"
                  disabled={!signed || Boolean(pending)}
                  isLoading={pending === 'decline'}
                  onClick={() => perform('decline')}
                >
                  {t.decline}
                </Button>
              </div>
            </>
          )}
        </>
      )}
    </NativePage>
  );
}
