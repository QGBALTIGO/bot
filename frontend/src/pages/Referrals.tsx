import 'react';
import { AnimatePresence, m } from 'framer-motion';
import { Activity, Copy, Gem, Gift, Send, Share2, UserPlus } from 'lucide-react';
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
  rewarded: boolean;
}

interface ReferralStats {
  invited_count: number;
  tracked_count: number;
  earned_shards: number;
  referrer_reward_shards: number;
  referrer_reward_xp: number;
  referred_reward_shards: number;
  referred_reward_pet: string;
}

export const Referrals = () => {
  const { user } = useUser();
  const { addToast } = useToast();
  const {
    data: referrals,
    loading,
    error,
  } = useApi<Referral[]>('/social/referrals', { initialData: [] });
  const { data: stats } = useApi<ReferralStats>('/social/referrals/stats');
  const botUsername = (import.meta.env.VITE_BOT_USERNAME || 'SealYourWaifuBot').replace(/^@/, '');
  const referralLink = user?.id ? `https://t.me/${botUsername}?start=ref_${user.id}` : '';
  const referralCount = stats?.invited_count ?? referrals?.length ?? 0;
  const earnedShards = stats?.earned_shards ?? referralCount * 500;
  const referrerRewardShards = stats?.referrer_reward_shards ?? 500;
  const referrerRewardXp = stats?.referrer_reward_xp ?? 50;
  const referredRewardShards = stats?.referred_reward_shards ?? 1500;
  const referredRewardPet = stats?.referred_reward_pet ?? 'blaze_fang';

  const copyToClipboard = async () => {
    if (!referralLink) return;
    try {
      await navigator.clipboard.writeText(referralLink);
      window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
      addToast('Referral link copied.', 'success');
    } catch {
      addToast('Manual copy required.', 'error');
    }
  };

  const shareReferral = () => {
    if (!referralLink) return;
    const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(referralLink)}&text=${encodeURIComponent('Vem para o Source Baltigo — colecione personagens, jogue e evolua sua coleção. Benefícios para novos collectors.')}`;
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    if (window.Telegram?.WebApp?.openTelegramLink) {
      window.Telegram.WebApp.openTelegramLink(shareUrl);
    } else {
      window.open(shareUrl, '_blank', 'noopener,noreferrer');
    }
  };

  if (loading && !referrals?.length)
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

  return (
    <div className="pt-6 max-w-2xl mx-auto adaptive-px space-y-8 select-none">
      <header className="space-y-1">
        <div className="flex items-center gap-2.5">
          <UserPlus className="text-brand-accent" size={20} />
          <h1 className="text-xl font-bold text-zinc-100 uppercase tracking-tight">Recruitment</h1>
        </div>
        <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest opacity-60">
          Invite friends, earn Coins
        </p>
      </header>

      <section className="space-y-4">
        <Card variant="surface" className="p-6 space-y-6">
          <div className="space-y-2 text-center sm:text-left">
            <p className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest">
              Your Referral Link
            </p>
            <div className="px-4 py-3 bg-zinc-950 border border-white/5 rounded-md font-mono text-[11px] text-brand-accent break-all select-all">
              {referralLink || 'INITIALIZING...'}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Button
              variant="accent"
              onClick={shareReferral}
              disabled={!referralLink}
              className="h-12"
              leftIcon={<Send size={16} />}
            >
              Share Link
            </Button>
            <Button
              variant="secondary"
              onClick={copyToClipboard}
              disabled={!referralLink}
              className="h-12"
              leftIcon={<Copy size={16} />}
            >
              Copy Link
            </Button>
          </div>
        </Card>

        <div className="grid grid-cols-2 gap-3">
          <Card variant="default" className="p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest">
                Friends joined
              </span>
              <UserPlus size={14} className="text-zinc-500" />
            </div>
            <div className="text-2xl font-mono font-bold text-zinc-100">
              {formatNumber(referralCount)}
            </div>
          </Card>

          <Card variant="default" className="p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest">
                Credits
              </span>
              <Gem size={14} className="text-zinc-500" />
            </div>
            <div className="flex items-baseline gap-1.5">
              <span className="text-2xl font-mono font-bold text-zinc-100">
                {formatNumber(earnedShards)}
              </span>
              <span className="text-[9px] font-bold text-zinc-600 uppercase">Coins</span>
            </div>
          </Card>
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest px-1">
          Rewards
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Card variant="default" className="p-4 flex items-center gap-4">
            <div className="w-10 h-10 rounded bg-brand-accent/10 flex items-center justify-center text-brand-accent shrink-0 border border-brand-accent/20">
              <Activity size={18} />
            </div>
            <div>
              <p className="text-[8px] font-bold text-brand-accent uppercase tracking-widest mb-0.5">
                YOU GET
              </p>
              <p className="text-xs font-bold text-zinc-100 uppercase">
                {formatNumber(referrerRewardShards)} Coins + {formatNumber(referrerRewardXp)} XP
              </p>
            </div>
          </Card>
          <Card variant="default" className="p-4 flex items-center gap-4 border-emerald-500/10">
            <div className="w-10 h-10 rounded bg-emerald-500/10 flex items-center justify-center text-emerald-500 shrink-0 border border-emerald-500/20">
              <Gift size={18} />
            </div>
            <div>
              <p className="text-[8px] font-bold text-emerald-500 uppercase tracking-widest mb-0.5">
                THEY GET
              </p>
              <p className="text-xs font-bold text-zinc-100 uppercase">
                {formatNumber(referredRewardShards)} Coins + {referredRewardPet.replace(/_/g, ' ')} pet
              </p>
            </div>
          </Card>
        </div>
      </section>

      <section className="space-y-4">
        <div className="flex items-center justify-between px-1">
          <h2 className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest">
            Invited friends
          </h2>
          <Badge variant="secondary" size="xs">
            {referrals?.length || 0} joined
          </Badge>
        </div>

        <AnimatePresence mode="wait">
          {error ? (
            <div className="py-12">
              <ErrorState
                message="Could not load your invite history."
                onAction={() => window.location.reload()}
              />
            </div>
          ) : referrals && referrals.length > 0 ? (
            <m.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="grid grid-cols-1 gap-2"
            >
              {referrals.map((referral) => (
                <Card
                  key={referral.referred_id}
                  variant="default"
                  className="p-3 flex items-center justify-between group"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-8 h-8 rounded bg-zinc-900 border border-white/5 flex items-center justify-center text-zinc-600 font-mono text-[9px]">
                      ID_{String(referral.referred_id).slice(-4)}
                    </div>
                    <span className="text-sm font-bold text-zinc-100 uppercase tracking-tight truncate">
                      {referral.referred_name}
                    </span>
                  </div>
                  {referral.rewarded && (
                    <Badge variant="success" size="xs">
                      VERIFIED
                    </Badge>
                  )}
                </Card>
              ))}
            </m.div>
          ) : (
            <div className="py-20 border border-dashed border-white/5 rounded-lg bg-zinc-950/50 text-center flex flex-col items-center justify-center space-y-4">
              <div className="w-12 h-12 rounded-full border border-white/5 flex items-center justify-center opacity-10">
                <Share2 size={24} />
              </div>
              <p className="text-[9px] font-bold text-zinc-700 uppercase tracking-widest">
                Network Empty
              </p>
            </div>
          )}
        </AnimatePresence>
      </section>
    </div>
  );
};
