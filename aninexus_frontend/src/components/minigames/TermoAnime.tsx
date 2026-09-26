import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { apiFetch, getErrorMessage } from '../../api/client';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { Input } from '../ui/Input';

type Guess = { guess: string; result: string };
type Game = {
  status: string;
  guesses: Guess[];
  attempts: number;
  seconds_left?: number;
  word?: string;
  category?: string;
  source?: string;
  reward_coins?: number;
  reward_xp?: number;
};

export function TermoAnime() {
  const [game, setGame] = useState<Game | null>(null);
  const [guess, setGuess] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    try { setGame(await apiFetch('/termo/state')); } catch (err) { setError(getErrorMessage(err)); }
  };
  useEffect(() => { void load(); }, []);

  const start = async () => {
    setPending(true); setError('');
    try { setGame(await apiFetch('/termo/start', { method: 'POST' })); }
    catch (err) { setError(getErrorMessage(err)); }
    finally { setPending(false); }
  };

  const submit = async () => {
    const word = guess.trim().toLocaleLowerCase('pt-BR');
    if (word.length !== 6 || pending) return;
    setPending(true); setError('');
    try {
      const data = await apiFetch('/termo/guess', { method: 'POST', body: JSON.stringify({ guess: word }) });
      setGame(data.game); setGuess('');
    } catch (err) { setError(getErrorMessage(err)); }
    finally { setPending(false); }
  };

  if (!game) return <div className="flex justify-center p-8"><Loader2 className="animate-spin text-zinc-700" /></div>;
  if (game.status === 'idle') {
    return <Card className="p-5 space-y-4"><p className="text-sm font-bold text-zinc-100">Termo Anime</p><p className="text-xs text-zinc-500">Descubra a palavra de seis letras em até seis tentativas.</p><Button onClick={start} isLoading={pending}>Jogar palavra de hoje</Button></Card>;
  }

  return (
    <Card className="p-5 space-y-4">
      <div className="flex items-center justify-between"><div><p className="text-sm font-bold text-zinc-100">Termo Anime</p><p className="text-[9px] uppercase tracking-widest text-zinc-600">{game.attempts}/6 tentativas</p></div>{game.status === 'playing' && <span className="font-mono text-xs text-zinc-400">{game.seconds_left ?? 0}s</span>}</div>
      <div className="space-y-2">
        {Array.from({ length: 6 }).map((_, row) => {
          const item = game.guesses?.[row];
          const letters = item?.guess?.toUpperCase().split('') || Array(6).fill('');
          const marks = item?.result ? Array.from(item.result) : [];
          return <div key={row} className="grid grid-cols-6 gap-1.5">{letters.map((letter, col) => <div key={col} className="aspect-square rounded-md border border-white/10 bg-zinc-950 flex flex-col items-center justify-center font-mono font-bold text-zinc-100"><span>{letter}</span>{marks[col] && <span className="text-[8px] leading-none">{marks[col]}</span>}</div>)}</div>;
        })}
      </div>
      {game.status === 'playing' ? <div className="flex gap-2"><Input aria-label="Palavra de seis letras" maxLength={6} value={guess} onChange={(e) => setGuess(e.target.value.replace(/[^A-Za-zÀ-ÿ]/g, ''))} onKeyDown={(e) => { if (e.key === 'Enter') void submit(); }} placeholder="6 letras" /><Button onClick={submit} disabled={guess.trim().length !== 6 || pending} isLoading={pending}>Enviar</Button></div> : <div className="space-y-2"><p className="text-sm font-bold text-zinc-100">{game.status === 'win' ? 'Você acertou.' : 'Partida encerrada.'}</p><p className="font-mono text-xl text-brand-accent">{game.word}</p><p className="text-xs text-zinc-500">{game.category} · {game.source}</p>{game.status === 'win' && <p className="text-xs text-emerald-400">+{game.reward_coins || 0} Coins · +{game.reward_xp || 0} XP</p>}</div>}
      {error && <p className="text-xs text-red-400">{error}</p>}
    </Card>
  );
}
