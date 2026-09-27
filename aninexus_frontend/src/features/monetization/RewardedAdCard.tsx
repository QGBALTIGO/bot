import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Gift, Loader2, Play, ShieldCheck } from 'lucide-react';
import { useMemo, useState } from 'react';
import { apiFetch, getErrorMessage, invalidateQueries } from '../../api/client';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { useToast } from '../../components/ui/Toast';
import { useUser } from '../../context/UserContext';

interface RewardedStatus {
  enabled: boolean;
  provider: string;
  sdkUrl?: string | null;
  zoneId?: string | null;
  sdkFunction?: string | null;
  requestVar: string;
  rewardDados: number;
  dailyLimit: number;
  rewardedToday: number;
  remainingToday: number;
  cooldownMinutes: number;
  cooldownUntil?: string | null;
  dadoBalance: number;
  dadoMax: number;
  canStart: boolean;
  pending?: { id: string; expiresAt: string } | null;
}

interface RewardedStart {
  id: string;
  ymid: string;
  expiresAt: string;
  sdkUrl: string;
  zoneId: string;
  sdkFunction: string;
  requestVar: string;
  reused: boolean;
}

interface RewardedResult {
  id: string;
  status: 'pending' | 'rewarded' | 'non_valued' | 'expired' | 'cancelled';
  rewardedDados: number;
}

type MonetagHandler = (options?: Record<string, unknown>) => Promise<unknown>;

let sdkPromise: Promise<MonetagHandler> | null = null;

function loadMonetagSdk(config: Pick<RewardedStart, 'sdkUrl' | 'zoneId' | 'sdkFunction'>) {
  const existing = (window as unknown as Record<string, unknown>)[config.sdkFunction];
  if (typeof existing === 'function') return Promise.resolve(existing as MonetagHandler);
  if (sdkPromise) return sdkPromise;

  sdkPromise = new Promise<MonetagHandler>((resolve, reject) => {
    const selector = 'script[data-source-monetag="true"]';
    let script = document.querySelector<HTMLScriptElement>(selector);
    const finish = () => {
      const handler = (window as unknown as Record<string, unknown>)[config.sdkFunction];
      if (typeof handler === 'function') {
        resolve(handler as MonetagHandler);
      } else {
        sdkPromise = null;
        reject(new Error('O anúncio ainda não está disponível.'));
      }
    };

    if (!script) {
      script = document.createElement('script');
      script.src = config.sdkUrl;
      script.async = true;
      script.dataset.zone = config.zoneId;
      script.dataset.sdk = config.sdkFunction;
      script.dataset.sourceMonetag = 'true';
      script.addEventListener('load', finish, { once: true });
      script.addEventListener(
        'error',
        () => {
          sdkPromise = null;
          reject(new Error('Não foi possível carregar o anúncio.'));
        },
        { once: true },
      );
      document.head.appendChild(script);
      return;
    }

    if (script.dataset.zone !== config.zoneId || script.dataset.sdk !== config.sdkFunction) {
      sdkPromise = null;
      reject(new Error('Configuração de anúncios desatualizada. Reabra a MiniApp.'));
      return;
    }
    if (script.dataset.loaded === 'true') finish();
    else script.addEventListener('load', finish, { once: true });
  });

  void sdkPromise.then(() => {
    const script = document.querySelector<HTMLScriptElement>('script[data-source-monetag="true"]');
    if (script) script.dataset.loaded = 'true';
  });

  return sdkPromise;
}

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

async function waitForReward(sessionId: string) {
  let latest: RewardedResult | null = null;
  for (let attempt = 0; attempt < 10; attempt += 1) {
    await wait(attempt === 0 ? 1200 : 1500);
    latest = await apiFetch('/monetization/rewarded/' + sessionId);
    if (latest.status !== 'pending') return latest;
  }
  return latest;
}

export function RewardedAdCard() {
  const { user, refreshUser } = useUser();
  const { addToast } = useToast();
  const cache = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState('');

  const status = useQuery<RewardedStatus>({
    queryKey: ['rewarded-ad-status', user?.id],
    queryFn: () => apiFetch('/monetization/rewarded/status'),
    enabled: Boolean(user),
    staleTime: 15000,
    retry: false,
  });

  const cooldownLabel = useMemo(() => {
    const raw = status.data?.cooldownUntil;
    if (!raw) return '';
    const until = new Date(raw);
    if (!Number.isFinite(until.getTime()) || until <= new Date()) return '';
    return until.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  }, [status.data?.cooldownUntil]);

  if (status.isPending || status.isError || !status.data?.enabled) return null;

  const data = status.data;
  const full = data.dadoBalance >= data.dadoMax;
  const exhausted = data.remainingToday <= 0;
  const buttonText = full
    ? 'Saldo de Dados cheio'
    : exhausted
      ? 'Limite diário atingido'
      : cooldownLabel
        ? 'Disponível às ' + cooldownLabel
        : busy
          ? phase || 'Preparando anúncio...'
          : 'Assistir e ganhar +' + data.rewardDados + ' Dado';

  const refreshAll = async () => {
    await status.refetch();
    invalidateQueries(['/dado/state', '/me']);
    await cache.invalidateQueries({ queryKey: ['api', '/me', null] });
    await refreshUser();
  };

  const watch = async () => {
    if (busy || full || exhausted || cooldownLabel) return;
    setBusy(true);
    setPhase('Preparando anúncio...');
    try {
      const start = (await apiFetch('/monetization/rewarded/start', {
        method: 'POST',
      })) as RewardedStart;
      const handler = await loadMonetagSdk(start);
      setPhase('Assistindo anúncio...');
      try {
        await handler({ ymid: start.ymid, requestVar: start.requestVar });
      } catch (error) {
        console.warn('[Source Monetag] SDK não confirmou a exibição.', error);
      }

      setPhase('Confirmando recompensa...');
      const result = await waitForReward(start.id);
      if (result?.status === 'rewarded') {
        const amount = result.rewardedDados || data.rewardDados;
        addToast(
          'Anúncio confirmado: +' + amount + ' Dado' + (amount === 1 ? '.' : 's.'),
          'success',
        );
        await refreshAll();
        return;
      }
      if (result?.status === 'non_valued') {
        addToast(
          'Esse anúncio não foi elegível para recompensa. Nenhum Dado foi consumido.',
          'info',
        );
        await status.refetch();
        return;
      }
      if (result?.status === 'expired' || result?.status === 'cancelled') {
        addToast('A confirmação do anúncio expirou. Tente novamente mais tarde.', 'error');
        await status.refetch();
        return;
      }
      addToast('A Monetag ainda está confirmando a visualização. Atualize em instantes.', 'info');
      await status.refetch();
    } catch (error) {
      addToast(getErrorMessage(error), 'error');
      await status.refetch();
    } finally {
      setBusy(false);
      setPhase('');
    }
  };

  return (
    <Card className="p-5 space-y-4 border-violet-500/15">
      <div className="flex items-start justify-between gap-4">
        <div className="flex gap-3 min-w-0">
          <div className="w-10 h-10 shrink-0 rounded-md border border-violet-500/20 bg-violet-500/10 grid place-items-center text-violet-300">
            <Gift size={18} />
          </div>
          <div className="min-w-0">
            <p className="text-[9px] font-bold uppercase tracking-widest text-violet-300">
              Publicidade opcional
            </p>
            <h2 className="text-sm font-bold text-zinc-100 mt-1">Ganhe 1 Dado</h2>
            <p className="text-xs text-zinc-500 mt-1 leading-relaxed">
              Assista a um anúncio recompensado. O Dado só é entregue depois da confirmação segura da Monetag.
            </p>
          </div>
        </div>
        <ShieldCheck size={18} className="text-zinc-600 shrink-0" />
      </div>

      <div className="grid grid-cols-3 gap-2">
        <div className="rounded-md border border-white/5 bg-zinc-950/60 p-3">
          <p className="text-[8px] font-bold uppercase tracking-widest text-zinc-600">Hoje</p>
          <p className="text-sm font-mono font-bold text-zinc-200 mt-1">
            {data.rewardedToday}/{data.dailyLimit}
          </p>
        </div>
        <div className="rounded-md border border-white/5 bg-zinc-950/60 p-3">
          <p className="text-[8px] font-bold uppercase tracking-widest text-zinc-600">Saldo</p>
          <p className="text-sm font-mono font-bold text-zinc-200 mt-1">
            {data.dadoBalance}/{data.dadoMax}
          </p>
        </div>
        <div className="rounded-md border border-white/5 bg-zinc-950/60 p-3">
          <p className="text-[8px] font-bold uppercase tracking-widest text-zinc-600">Intervalo</p>
          <p className="text-sm font-mono font-bold text-zinc-200 mt-1">
            {data.cooldownMinutes} min
          </p>
        </div>
      </div>

      <Button
        className="w-full"
        disabled={busy || full || exhausted || Boolean(cooldownLabel)}
        leftIcon={busy ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
        onClick={() => void watch()}
      >
        {buttonText}
      </Button>

      <p className="text-[9px] leading-relaxed text-zinc-700">
        Máximo de {data.dailyLimit} recompensas por dia. Não é necessário clicar no anúncio do anunciante.
      </p>
    </Card>
  );
}
