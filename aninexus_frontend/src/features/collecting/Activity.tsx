import { ArrowRight, CalendarDays, Check, HelpCircle, Sparkles } from 'lucide-react';
import { useState } from 'react';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { NativePage, QueryFeedback } from '../../native/ui';
import { nativeParams, navigateNative } from '../../native/navigation';
import { useFeatureAction, useFeatureQuery } from './api';
interface Calendar {
  today: string;
  streak: number;
  claimed_today: boolean;
  days: { date: string; claimed: boolean }[];
  reward_rules: string;
  milestone: { eligible: boolean; claimed?: boolean; label: string };
}
export function Activity() {
  const now = useFeatureQuery<{
    items: {
      id: string;
      title: string;
      description: string;
      ready: boolean;
      tab: string;
      section?: string;
    }[];
  }>('/now');
  const calendar = useFeatureQuery<Calendar>('/calendar'),
    { perform, pending } = useFeatureAction();
  return (
    <NativePage
      title="Disponível agora"
      subtitle="Acompanhe suas ações sem sair do Source."
      icon={Sparkles}
    >
      <QueryFeedback
        loading={now.isPending || calendar.isPending}
        error={now.error || calendar.error}
        retry={() => {
          void now.refetch();
          void calendar.refetch();
        }}
      />
      <Card className="p-5 space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-bold text-zinc-100">Presença diária</h2>
            <p className="text-xs text-zinc-500 mt-1">
              {calendar.data?.streak || 0} dia(s) consecutivo(s) · horário de São Paulo
            </p>
          </div>
          <CalendarDays size={20} className="shrink-0 text-zinc-500" />
        </div>
        <div className="grid grid-cols-7 gap-1">
          {calendar.data?.days.map((day) => (
            <div
              key={day.date}
              className={`min-w-0 rounded-md border p-2 text-center ${day.claimed ? 'border-brand-accent/40 bg-brand-accent/10' : 'border-white/5 bg-zinc-900'}`}
            >
              <p className="text-[10px] text-zinc-400">{day.date.slice(8)}</p>
              <div className="h-5 flex items-center justify-center">
                {day.claimed ? (
                  <Check size={14} className="text-brand-accent" />
                ) : (
                  <span className="text-zinc-700">·</span>
                )}
              </div>
            </div>
          ))}
        </div>
        <p className="text-xs text-zinc-500 leading-relaxed">
          {calendar.data?.reward_rules} Quando o saldo de dados está cheio, o resgate equivalente é
          entregue em Coins.
        </p>
        <Button
          className="w-full"
          disabled={pending || !calendar.data || calendar.data.claimed_today}
          onClick={() =>
            void perform(
              '/daily/claim',
              {},
              { economic: true, success: 'Resgate diário conferido.' },
            )
          }
        >
          {calendar.data?.claimed_today ? 'Resgatado hoje' : 'Resgatar recompensa diária'}
        </Button>
        <div className="border-t border-white/5 pt-3">
          <p className="text-xs text-zinc-400 mb-2">
            Sete dias consecutivos liberam um emblema para o perfil.
          </p>
          <Button
            variant="secondary"
            size="sm"
            disabled={
              pending || !calendar.data?.milestone.eligible || calendar.data?.milestone.claimed
            }
            onClick={() =>
              void perform(
                '/daily/milestone',
                {},
                { success: 'Emblema semanal disponível na Oficina.' },
              )
            }
          >
            {calendar.data?.milestone.claimed ? 'Emblema resgatado' : 'Resgatar emblema semanal'}
          </Button>
        </div>
      </Card>
      <div className="grid sm:grid-cols-2 gap-3">
        {now.data?.items
          .filter((i) => i.id !== 'daily')
          .map((item) => (
            <Card key={item.id} className="p-4 flex flex-col gap-3">
              <div className="flex items-center gap-2">
                <span
                  className={`w-1.5 h-1.5 rounded-full ${item.ready ? 'bg-brand-accent' : 'bg-zinc-700'}`}
                />
                <h2 className="text-sm font-bold text-zinc-200">{item.title}</h2>
              </div>
              <p className="text-xs text-zinc-500 flex-1">{item.description}</p>
              <Button
                variant="ghost"
                size="sm"
                className="self-start"
                rightIcon={<ArrowRight size={13} />}
                onClick={() => navigateNative(item.tab)}
              >
                Abrir
              </Button>
            </Card>
          ))}
      </div>
    </NativePage>
  );
}
export function Help() {
  const query = useFeatureQuery<{
    items: { id: string; title: string; text: string; tab: string; command: string }[];
  }>('/help');
  const [open, setOpen] = useState(nativeParams().get('section') || 'collection');
  return (
    <NativePage
      title="Central de ajuda"
      subtitle="Regras e atalhos do próprio Source."
      icon={HelpCircle}
    >
      <QueryFeedback loading={query.isPending} error={query.error} retry={query.refetch} />
      {query.data?.items.map((t) => (
        <Card key={t.id} className="p-4 space-y-3">
          <button
            className="w-full text-left text-sm font-bold text-zinc-200"
            aria-expanded={open === t.id}
            onClick={() => setOpen(open === t.id ? '' : t.id)}
          >
            {t.title}
          </button>
          {open === t.id && (
            <>
              <p className="text-sm text-zinc-400 leading-relaxed">{t.text}</p>
              <Button variant="secondary" size="sm" onClick={() => navigateNative(t.tab)}>
                Abrir recurso · {t.command}
              </Button>
            </>
          )}
        </Card>
      ))}
    </NativePage>
  );
}
