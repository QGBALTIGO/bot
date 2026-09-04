import { AnimatePresence, m } from 'framer-motion';
import { CheckCircle2, Coins, Copy, Gift, Send, Share2, UserPlus } from 'lucide-react';
import { useState } from 'react';
import { apiFetch, getErrorMessage } from '../api/client';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { ErrorState } from '../components/ui/ErrorState';
import { Skeleton } from '../components/ui/Skeleton';
import { useToast } from '../components/ui/Toast';
import { useUser } from '../context/UserContext';
import { useApi } from '../hooks/useApi';
import { formatNumber } from '../utils';

interface Referral {
  referred_id: number;
  referred_name: string;
  level: number;
  rewarded: boolean;
}

interface ReferralStats {
  invited_count: number;
  qualified_count: number;
  claimable_count: number;
  rewarded_count: number;
  earned_coins: number;
  required_level: number;
  referrer_reward_coins: number;
  referred_reward_dados: number;
}

export const Referrals = () => {
  const { user, refreshUser } = useUser();
  const { addToast } = useToast();
  const { data: referrals, loading, error, execute: fetchReferrals } = useApi<Referral[]>(
    '/social/referrals',
    { initialData: [] },
  );
  const { data: stats, execute: fetchStats } = useApi<ReferralStats>('/social/referrals/stats');
  const [claiming, setClaiming] = useState(false);
  const botUsername = (import.meta.env.VITE_BOT_USERNAME || 'SourceBaltigo_Bot').replace(/^@/, '');
  const referralLink = user?.id ? `https://t.me/${botUsername}?start=ref_${user.id}` : '';

  const copyToClipboard = async () => {
    if (!referralLink) return;
    try {
      await navigator.clipboard.writeText(referralLink);
      window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
      addToast('Link copiado.', 'success');
    } catch {
      addToast('Não foi possível copiar automaticamente.', 'error');
    }
  };

  const shareReferral = () => {
    if (!referralLink) return;
    const text = 'Vem para o AniNexus comigo! Colecione personagens e evolua seu perfil no Source Baltigo.';
    const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(referralLink)}&text=${encodeURIComponent(text)}`;
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    if (window.Telegram?.WebApp?.openTelegramLink) window.Telegram.WebApp.openTelegramLink(shareUrl);
    else window.open(shareUrl, '_blank', 'noopener,noreferrer');
  };

  const claimRewards = async () => {
    if (claiming || !stats?.claimable_count) return;
    setClaiming(true);
    try {
      const result = await apiFetch('/social/referrals/claim', { method: 'POST' });
      addToast(
        result.claimed > 0
          ? `Recompensas resgatadas: +${result.coins} Coin${result.coins === 1 ? '' : 's'}.`
          : 'Nenhuma recompensa nova disponível.',
        result.claimed > 0 ? 'success' : 'info',
      );
      await Promise.allSettled([fetchReferrals(), fetchStats(), refreshUser()]);
    } catch (err) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setClaiming(false);
    }
  };

  if (loading && !referrals?.length) {
    return (
      <div className="pt-6 adaptive-px max-w-2xl mx-auto space-y-8">
        <Skeleton className="h-40 w-full rounded-md" />
        <div className="grid grid-cols-2 gap-4">
          <Skeleton className="h-20 rounded-md" />
          <Skeleton className="h-20 rounded-md" />
        </div>
        <Skeleton className="h-60 w-full rounded-md" />
      </div>
    );
  }

  return (
    <div className="pt-6 max-w-2xl mx-auto adaptive-px space-y-8 select-none">
      <header className="space-y-1">
        <div className="flex items-center gap-2.5">
          <UserPlus className="text-brand-accent" size={20} />
          <h1 className="text-xl font-bold text-zinc-100 uppercase tracking-tight">Indicações</h1>
        </div>
        <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest opacity-60">
          Convide amigos e evoluam juntos
        </p>
      </header>

      <Card variant="surface" className="p-6 space-y-6">
        <div className="space-y-2">
          <p className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest">Seu link</p>
          <div className="px-4 py-3 bg-zinc-950 border border-white/5 rounded-md font-mono text-[11px] text-brand-accent break-all select-all">
            {referralLink || 'Carregando...'}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Button variant="accent" onClick={shareReferral} disabled={!referralLink} className="h-12" leftIcon={<Send size={16} />}>
            Compartilhar
          </Button>
          <Button variant="secondary" onClick={copyToClipboard} disabled={!referralLink} className="h-12" leftIcon={<Copy size={16} />}>
            Copiar
          </Button>
        </div>
      </Card>

      <section className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          ['Convidados', stats?.invited_count ?? referrals?.length ?? 0],
          ['Nível 2+', stats?.qualified_count ?? 0],
          ['Resgatados', stats?.rewarded_count ?? 0],
          ['Coins ganhos', stats?.earned_coins ?? 0],
        ].map(([label, value]) => (
          <Card key={String(label)} variant="default" className="p-4">
            <p className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest mb-2">{label}</p>
            <p className="text-xl font-mono font-bold text-zinc-100">{formatNumber(Number(value))}</p>
          </Card>
        ))}
      </section>

      <Card variant="default" className="p-5 border-brand-accent/10 bg-brand-accent/[0.02] space-y-4">
        <div className="flex items-start gap-4">
          <div className="w-10 h-10 rounded bg-brand-accent/10 flex items-center justify-center border border-brand-accent/20 shrink-0">
            <Gift size={18} className="text-brand-accent" />
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="text-sm font-bold text-zinc-100 uppercase tracking-tight">Recompensa de indicação</h2>
            <p className="text-[10px] text-zinc-500 uppercase tracking-widest mt-1 leading-relaxed">
              Quando o convidado alcançar o nível {stats?.required_level ?? 2}, você recebe +{stats?.referrer_reward_coins ?? 1} Coin e ele recebe +{stats?.referred_reward_dados ?? 1} Dado. Cada convite paga uma única vez.
            </p>
          </div>
        </div>
        <Button
          variant="accent"
          className="w-full h-11"
          onClick={claimRewards}
          isLoading={claiming}
          disabled={!stats?.claimable_count}
          leftIcon={<Coins size={15} />}
        >
          {stats?.claimable_count ? `Resgatar ${stats.claimable_count} recompensa${stats.claimable_count === 1 ? '' : 's'}` : 'Nenhuma recompensa disponível'}
        </Button>
      </Card>

      <section className="space-y-4">
        <div className="flex items-center justify-between px-1">
          <h2 className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest">Amigos convidados</h2>
          <Badge variant="secondary" size="xs">{referrals?.length || 0}</Badge>
        </div>

        <AnimatePresence mode="wait">
          {error ? (
            <ErrorState message="Não foi possível carregar suas indicações." onAction={fetchReferrals} />
          ) : referrals && referrals.length > 0 ? (
            <m.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-2">
              {referrals.map((referral) => (
                <Card key={referral.referred_id} variant="default" className="p-3 flex items-center justify-between gap-4">
                  <div className="min-w-0">
                    <p className="text-sm font-bold text-zinc-100 uppercase tracking-tight truncate">{referral.referred_name}</p>
                    <p className="text-[9px] font-mono text-zinc-600 uppercase mt-1">Nível {referral.level}</p>
                  </div>
                  {referral.rewarded ? (
                    <Badge variant="success" size="xs" icon={CheckCircle2}>Recompensado</Badge>
                  ) : referral.level >= (stats?.required_level ?? 2) ? (
                    <Badge variant="primary" size="xs">Disponível</Badge>
                  ) : (
                    <Badge variant="secondary" size="xs">Em progresso</Badge>
                  )}
                </Card>
              ))}
            </m.div>
          ) : (
            <div className="py-16 border border-dashed border-white/5 rounded-lg bg-zinc-950/50 text-center space-y-3">
              <Share2 size={24} className="mx-auto text-zinc-800" />
              <p className="text-[9px] font-bold text-zinc-700 uppercase tracking-widest">Nenhuma indicação ainda</p>
            </div>
          )}
        </AnimatePresence>
      </section>
    </div>
  );
};
