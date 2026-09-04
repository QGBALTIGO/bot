import { AnimatePresence, m } from 'framer-motion';
import { Box, Clock3, Dices, Loader2, Sparkles, Zap } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { apiFetch, getErrorMessage } from '../api/client';
import type { Character } from '../context/UserContext';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { GachaReveal } from '../components/ui/GachaReveal';
import { useToast } from '../components/ui/Toast';
import { haptics } from '../utils';

type DadoOption = { id: number; title: string; cover: string };
type ActiveRoll = { roll_id: number; dice_value: number; options: DadoOption[]; status?: string };
type DadoState = {
  balance: number;
  max_balance: number;
  next_recharge_hhmm: string;
  next_recharge_iso?: string | null;
  active_roll?: ActiveRoll | null;
};

const dotLayouts: Record<number, number[]> = {
  1: [4],
  2: [0, 8],
  3: [0, 4, 8],
  4: [0, 2, 6, 8],
  5: [0, 2, 4, 6, 8],
  6: [0, 2, 3, 5, 6, 8],
};

const DieFace = ({ value, rolling }: { value: number; rolling: boolean }) => {
  const dots = new Set(dotLayouts[Math.max(1, Math.min(6, value))] || [4]);
  return (
    <m.div
      animate={rolling ? { rotate: [0, 95, 190, 285, 360], scale: [1, 0.86, 1.08, 0.94, 1] } : { rotate: 0, scale: 1 }}
      transition={{ duration: 1.15, ease: [0.2, 0.8, 0.2, 1] }}
      className="w-36 h-36 rounded-[28px] bg-zinc-100 border border-white shadow-[0_24px_80px_rgba(0,0,0,0.55)] p-5 grid grid-cols-3 grid-rows-3 gap-2"
    >
      {Array.from({ length: 9 }).map((_, index) => (
        <div key={index} className="flex items-center justify-center">
          {dots.has(index) && <div className="w-5 h-5 rounded-full bg-zinc-950 shadow-inner" />}
        </div>
      ))}
    </m.div>
  );
};

export const Dado = () => {
  const { addToast } = useToast();
  const [state, setState] = useState<DadoState | null>(null);
  const [activeRoll, setActiveRoll] = useState<ActiveRoll | null>(null);
  const [loading, setLoading] = useState(true);
  const [rolling, setRolling] = useState(false);
  const [picking, setPicking] = useState<number | null>(null);
  const [revealed, setRevealed] = useState<Character | null>(null);
  const [displayValue, setDisplayValue] = useState(1);

  const refresh = useCallback(async () => {
    try {
      const data = await apiFetch('/dado/state');
      setState(data);
      setActiveRoll(data.active_roll || null);
      if (data.active_roll?.dice_value) setDisplayValue(data.active_roll.dice_value);
    } catch (err) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setLoading(false);
    }
  }, [addToast]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const roll = async () => {
    if (rolling || (state?.balance || 0) <= 0) return;
    setRolling(true);
    haptics.heavy();
    const ticker = window.setInterval(() => setDisplayValue(1 + Math.floor(Math.random() * 6)), 90);
    try {
      const data = await apiFetch('/dado/roll', { method: 'POST' });
      if (!data?.ok) throw new Error(data?.error || 'Não foi possível rolar o dado.');
      await new Promise((resolve) => window.setTimeout(resolve, 900));
      setDisplayValue(Number(data.dice_value || 1));
      setActiveRoll({
        roll_id: Number(data.roll_id),
        dice_value: Number(data.dice_value),
        options: Array.isArray(data.options) ? data.options : [],
      });
      setState((prev) => (prev ? { ...prev, balance: Number(data.balance ?? prev.balance) } : prev));
      haptics.notification('success');
    } catch (err) {
      addToast(getErrorMessage(err), 'error');
      haptics.notification('error');
    } finally {
      window.clearInterval(ticker);
      setRolling(false);
    }
  };

  const pick = async (option: DadoOption) => {
    if (!activeRoll || picking !== null) return;
    setPicking(option.id);
    haptics.selection();
    try {
      const data = await apiFetch('/dado/pick', {
        method: 'POST',
        body: JSON.stringify({ roll_id: activeRoll.roll_id, anime_id: option.id }),
      });
      if (!data?.ok) throw new Error(data?.error || 'Não foi possível resgatar o personagem.');
      const character = data.character || {};
      setRevealed({
        id: String(character.id || ''),
        name: String(character.name || 'Personagem'),
        anime: String(character.anime_title || option.title || 'Anime'),
        rarity: String(character.tier || 'COMUM'),
        img_url: String(character.image || ''),
        zenith_price: 0,
        owned: true,
        count: 1,
      });
      setState((prev) => (prev ? { ...prev, balance: Number(data.balance ?? prev.balance) } : prev));
      setActiveRoll(null);
      haptics.notification('success');
    } catch (err) {
      addToast(getErrorMessage(err), 'error');
      haptics.notification('error');
    } finally {
      setPicking(null);
    }
  };

  if (loading && !state) {
    return (
      <div className="min-h-[65vh] flex items-center justify-center">
        <Loader2 size={28} className="animate-spin text-zinc-700" />
      </div>
    );
  }

  return (
    <div className="pt-6 max-w-3xl mx-auto adaptive-px space-y-8 select-none">
      <header className="space-y-1">
        <div className="flex items-center gap-2.5">
          <Dices size={20} className="text-brand-accent" />
          <h1 className="text-xl font-bold text-zinc-100 uppercase tracking-tight">Dado AniNexus</h1>
        </div>
        <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest opacity-60">
          Role, escolha uma obra e revele um personagem para sua coleção
        </p>
      </header>

      <section className="grid grid-cols-2 gap-3">
        <Card className="p-4 bg-zinc-900/50 border-white/[0.04]">
          <div className="flex items-center gap-2 text-zinc-500 mb-2">
            <Zap size={12} className="text-brand-accent" />
            <span className="text-[9px] font-bold uppercase tracking-widest">Dados disponíveis</span>
          </div>
          <div className="text-2xl font-mono font-bold text-zinc-100">
            {state?.balance || 0}<span className="text-sm text-zinc-600"> / {state?.max_balance || 24}</span>
          </div>
        </Card>
        <Card className="p-4 bg-zinc-900/50 border-white/[0.04]">
          <div className="flex items-center gap-2 text-zinc-500 mb-2">
            <Clock3 size={12} />
            <span className="text-[9px] font-bold uppercase tracking-widest">Próxima recarga</span>
          </div>
          <div className="text-2xl font-mono font-bold text-zinc-100">{state?.next_recharge_hhmm || '--:--'}</div>
        </Card>
      </section>

      <Card className="relative overflow-hidden p-8 border-white/[0.05] bg-zinc-900/30 min-h-[320px] flex flex-col items-center justify-center gap-8">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(59,130,246,0.10),transparent_65%)]" />
        <div className="relative z-10">
          <DieFace value={displayValue} rolling={rolling} />
        </div>
        <div className="relative z-10 w-full max-w-sm text-center space-y-3">
          <div className="text-[10px] font-bold text-zinc-500 uppercase tracking-[0.25em]">
            {activeRoll ? `${activeRoll.dice_value} obra${activeRoll.dice_value === 1 ? '' : 's'} liberada${activeRoll.dice_value === 1 ? '' : 's'}` : 'Pronto para rolar'}
          </div>
          {!activeRoll && (
            <Button
              onClick={roll}
              disabled={rolling || (state?.balance || 0) <= 0}
              className="w-full h-14 bg-zinc-100 text-zinc-950 font-bold uppercase tracking-[0.18em] text-[10px] rounded-xl"
            >
              {rolling ? 'Rolando...' : (state?.balance || 0) > 0 ? 'Rolar dado' : 'Sem dados disponíveis'}
            </Button>
          )}
        </div>
      </Card>

      <AnimatePresence mode="popLayout">
        {activeRoll && (
          <m.section
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            className="space-y-4"
          >
            <div className="flex items-center gap-2 px-1">
              <Sparkles size={14} className="text-brand-accent" />
              <h2 className="text-[10px] font-bold text-zinc-100 uppercase tracking-widest">Escolha uma obra</h2>
              <Badge variant="secondary" size="xs">1 escolha</Badge>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {activeRoll.options.map((option, index) => (
                <m.button
                  type="button"
                  key={option.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.05 }}
                  onClick={() => pick(option)}
                  disabled={picking !== null}
                  className="relative aspect-[2/3] rounded-xl overflow-hidden border border-white/[0.07] bg-zinc-900 text-left group disabled:opacity-50"
                >
                  {option.cover ? (
                    <img src={option.cover} alt={option.title} className="absolute inset-0 w-full h-full object-cover" referrerPolicy="no-referrer" />
                  ) : (
                    <div className="absolute inset-0 flex items-center justify-center"><Box className="text-zinc-700" /></div>
                  )}
                  <div className="absolute inset-0 bg-gradient-to-t from-black via-black/10 to-transparent" />
                  <div className="absolute bottom-0 left-0 right-0 p-3">
                    <div className="text-[10px] font-bold text-white uppercase tracking-tight line-clamp-2">{option.title}</div>
                    <div className="mt-2 text-[8px] font-bold text-brand-accent uppercase tracking-widest">
                      {picking === option.id ? 'Revelando...' : 'Selecionar'}
                    </div>
                  </div>
                </m.button>
              ))}
            </div>
          </m.section>
        )}
      </AnimatePresence>

      <GachaReveal character={revealed} onClose={() => { setRevealed(null); refresh(); }} />
    </div>
  );
};
