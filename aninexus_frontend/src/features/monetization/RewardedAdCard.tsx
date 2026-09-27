import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Coins, Gift, Loader2, Play, ShieldCheck, Sparkles } from 'lucide-react';
import { useMemo, useState } from 'react';
import { apiFetch, getErrorMessage, invalidateQueries } from '../../api/client';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { useToast } from '../../components/ui/Toast';
import { useUser } from '../../context/UserContext';

type RewardType = 'coins' | 'dado';

interface RewardedStatus {
  enabled: boolean;
  provider: string;
  sdkUrl?: string | null;
  zoneId?: string | null;
  sdkFunction?: string | null;
  requestVar: string;
  rewards: { coins: number; dado: number };
  dailyLimit: number;
  rewardedToday: number;
  remainingToday: number;
  cooldownMinutes: number;
  cooldownUntil?: string | null;
  dadoBalance: number;
  dadoMax: number;
  canStart: boolean;
  canStartCoins: boolean;
  canStartDado: boolean;
  pending?: {
    id: string;
    rewardType: RewardType;
    rewardAmount: number;
    expiresAt: string;
  } | null;
}

interface RewardedStart {
  id: string;
  ymid: string;
  expiresAt: string;
  sdkUrl: string;
  zoneId: string;
  sdkFunction: string;
  requestVar: string;
  rewardType: RewardType;
  rewardAmount: number;
  reused: boolean;
}

interface RewardedResult {
  id: string;
  status: 'pending' | 'rewarded' | 'non_valued' | 'expired' | 'cancelled';
  rewardType: RewardType;
  rewardAmount: number;
  rewardedDados: number;
  rewardedCoins: number;
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
  const [selectedReward, setSelectedReward] = useState<RewardType>('coins');

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
  const exhausted = data.remainingToday <= 0;
  const dadoFull = data.dadoBalance >= data.dadoMax;
  const selectedAmount =
    selectedReward === 'coins' ? data.rewards.coins : data.rewards.dado;
  const selectedAllowed =
    selectedReward === 'coins' ? data.canStartCoins : data.canStartDado;

  const buttonText = exhausted
    ? 'Limite diário atingido'
    : cooldownLabel
      ? 'Disponível às ' + cooldownLabel
      : busy
        ? phase || 'Preparando anúncio...'
        : selectedReward === 'coins'
          ? `Assistir e ganhar +${selectedAmount} Coins`
          : `Assistir e ganhar +${selectedAmount} Dado`;

  const refreshAll = async () => {
    await status.refetch();
    invalidateQueries(['/dado/state', '/me', '/quests']);
    await cache.invalidateQueries({ queryKey: ['api', '/me', null] });
    await refreshUser();
  };

  const watch = async () => {
    if (busy || exhausted || cooldownLabel || !selectedAllowed) return;
    setBusy(true);
    setPhase('Preparando anúncio...');

    try {
      const start = (await apiFetch('/monetization/rewarded/start', {
        method: 'POST',
        body: JSON.stringify({ rewardType: selectedReward }),
      })) as RewardedStart;

      if (start.rewardType !== selectedReward) setSelectedReward(start.rewardType);

      const handler = await loadMonetagSdk(start);
      setPhase('Assistindo anúncio...');

      try {
        await handler({
          ymid: start.ymid,
          requestVar: start.requestVar,
        });
      } catch (error) {
        // A Monetag recomenda postback server-side para reward logic.
        // O backend pode ter confirmado o evento mesmo se o callback visual atrasar.
        console.warn('[Source Monetag] callback do SDK não confirmou a tempo.', error);
      }

      setPhase('Validando com a Monetag...');
      const result = await waitForReward(start.id);

      if (result?.status === 'rewarded') {
        if (result.rewardedDados > 0) {
          addToast(`Anúncio validado: +${result.rewardedDados} Dado.`, 'success');
        } else if (result.rewardedCoins > 0) {
          const converted = start.rewardType === 'dado';
          addToast(
            converted
              ? `Seu saldo de Dados encheu durante o anúncio. Recompensa convertida em +${result.rewardedCoins} Coins.`
              : `Anúncio validado: +${result.rewardedCoins} Coins.`,
            'success',
          );
        }
        await refreshAll();
        return;
      }

      if (result?.status === 'non_valued') {
        addToast(
          'A Monetag classificou esta exibição como não monetizada. Nenhuma recompensa foi contabilizada e ela não consome seu limite diário.',
          'info',
        );
        await status.refetch();
        return;
      }

      if (result?.status === 'expired' || result?.status === 'cancelled') {
        addToast('A confirmação do anúncio expirou. Tente novamente.', 'error');
        await status.refetch();
        return;
      }

      addToast(
        'A Monetag ainda está confirmando a exibição. O crédito será liberado automaticamente quando o postback chegar.',
        'info',
      );
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
              Recompensa por anúncio
            </p>
            <h2 className="text-sm font-bold text-zinc-100 mt-1">Monetag</h2>
            <p className="text-xs text-zinc-500 mt-1 leading-relaxed">
              Anúncio opcional. Escolha sua recompensa e ela só é creditada quando a Monetag
              confirmar uma exibição monetizada.
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
          <p className="text-[8px] font-bold uppercase tracking-widest text-zinc-600">Restam</p>
          <p className="text-sm font-mono font-bold text-zinc-200 mt-1">
            {data.remainingToday}
          </p>
        </div>
        <div className="rounded-md border border-white/5 bg-zinc-950/60 p-3">
          <p className="text-[8px] font-bold uppercase tracking-widest text-zinc-600">Intervalo</p>
          <p className="text-sm font-mono font-bold text-zinc-200 mt-1">
            {data.cooldownMinutes} min
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Escolher recompensa">
        <button
          type="button"
          role="radio"
          aria-checked={selectedReward === 'coins'}
          disabled={busy}
          onClick={() => setSelectedReward('coins')}
          className={`rounded-md border p-3 text-left transition-colors ${
            selectedReward === 'coins'
              ? 'border-amber-500/30 bg-amber-500/10'
              : 'border-white/5 bg-zinc-950/60 hover:border-white/10'
          }`}
        >
          <Coins size={16} className="text-amber-400 mb-2" />
          <p className="text-xs font-bold text-zinc-100">+{data.rewards.coins} Coins</p>
          <p className="text-[9px] text-zinc-600 mt-1">Sempre disponível</p>
        </button>

        <button
          type="button"
          role="radio"
          aria-checked={selectedReward === 'dado'}
          disabled={busy || dadoFull}
          onClick={() => setSelectedReward('dado')}
          className={`rounded-md border p-3 text-left transition-colors ${
            selectedReward === 'dado'
              ? 'border-violet-500/30 bg-violet-500/10'
              : 'border-white/5 bg-zinc-950/60 hover:border-white/10'
          } ${dadoFull ? 'opacity-45 cursor-not-allowed' : ''}`}
        >
          <Sparkles size={16} className="text-violet-300 mb-2" />
          <p className="text-xs font-bold text-zinc-100">+{data.rewards.dado} Dado</p>
          <p className="text-[9px] text-zinc-600 mt-1">
            {dadoFull ? 'Saldo já está cheio' : `${data.dadoBalance}/${data.dadoMax} no saldo`}
          </p>
        </button>
      </div>

      <Button
        className="w-full"
        disabled={busy || exhausted || Boolean(cooldownLabel) || !selectedAllowed}
        leftIcon={busy ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
        onClick={() => void watch()}
      >
        {buttonText}
      </Button>

      <p className="text-[9px] leading-relaxed text-zinc-700">
        Máximo de {data.dailyLimit} anúncios recompensados por dia. Só eventos
        <strong className="text-zinc-600"> valued </strong>
        confirmados pela Monetag contam no limite e geram recompensa. Não é necessário clicar no
        anúncio do anunciante.
      </p>
    </Card>
  );
}
