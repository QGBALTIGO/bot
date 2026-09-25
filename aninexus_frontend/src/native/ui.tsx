import { ArrowLeft, ImageOff, Loader2, X, type LucideIcon } from 'lucide-react';
import { type ReactNode, useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { Skeleton } from '../components/ui/Skeleton';
import { getErrorMessage } from '../api/client';
import { cn } from '../utils';

export function NativePage({
  title,
  subtitle,
  icon: Icon,
  children,
  back,
}: {
  title: string;
  subtitle?: string;
  icon: LucideIcon;
  children: ReactNode;
  back?: () => void;
}) {
  return (
    <div data-native-page className="pt-6 max-w-5xl mx-auto adaptive-px space-y-6 pb-6">
      <header className="space-y-1">
        {back && (
          <Button
            variant="ghost"
            size="sm"
            onClick={back}
            leftIcon={<ArrowLeft size={13} />}
            className="mb-3"
          >
            Voltar
          </Button>
        )}
        <div className="flex items-center gap-2.5">
          <Icon size={20} className="text-brand-accent shrink-0" />
          <h1 className="text-xl font-bold text-zinc-100 uppercase tracking-tight">{title}</h1>
        </div>
        {subtitle && (
          <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest leading-relaxed">
            {subtitle}
          </p>
        )}
      </header>
      {children}
    </div>
  );
}
export function Choices({
  value,
  items,
  onChange,
  label = 'Opções',
}: {
  value: string;
  items: [string, string][];
  onChange: (key: string) => void;
  label?: string;
}) {
  return (
    <div role="group" aria-label={label} className="flex gap-2 overflow-x-auto pb-1 max-w-full">
      {items.map(([id, name]) => (
        <Button
          key={id}
          variant={value === id ? 'primary' : 'secondary'}
          size="sm"
          className="shrink-0 min-h-9"
          aria-pressed={value === id}
          onClick={() => onChange(id)}
        >
          {name}
        </Button>
      ))}
    </div>
  );
}
export function QueryFeedback({
  loading,
  error,
  retry,
  empty = false,
}: {
  loading: boolean;
  error: unknown;
  retry: () => unknown;
  empty?: boolean;
}) {
  if (loading)
    return (
      <div
        role="status"
        aria-label="Carregando"
        className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3"
      >
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="aspect-[2/3] rounded-md" />
        ))}
      </div>
    );
  if (error)
    return (
      <ErrorState
        message={getErrorMessage(error)}
        onAction={() => {
          void retry();
        }}
      />
    );
  if (empty) return <EmptyState />;
  return null;
}
export function Cover({
  src,
  name,
  className = '',
}: {
  src?: string | undefined;
  name: string;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);
  return (
    <div className={cn('relative aspect-[2/3] overflow-hidden bg-zinc-900', className)}>
      {src && !failed ? (
        <img
          src={src}
          alt={name}
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          onError={() => setFailed(true)}
          className="w-full h-full object-cover"
        />
      ) : (
        <div
          className="absolute inset-0 grid place-items-center"
          aria-label={`Sem imagem: ${name}`}
        >
          <ImageOff size={28} className="text-zinc-700" />
        </div>
      )}
    </div>
  );
}
export function Poster({
  src,
  title,
  subtitle,
  onClick,
  children,
}: {
  src?: string | undefined;
  title: string;
  subtitle?: string | undefined;
  onClick?: () => void;
  children?: ReactNode;
}) {
  return (
    <Card hover={Boolean(onClick)} className="min-w-0 h-full flex flex-col">
      <button
        type="button"
        onClick={onClick}
        disabled={!onClick}
        aria-label={title}
        className="block w-full text-left focus-visible:outline-2 focus-visible:outline-brand-accent"
      >
        <Cover src={src} name={title} />
        <div className="p-3 space-y-1 min-h-[76px]">
          <h3 className="text-xs font-bold text-zinc-100 leading-snug line-clamp-2">{title}</h3>
          {subtitle && (
            <p className="text-[9px] text-zinc-500 uppercase tracking-wider line-clamp-2">
              {subtitle}
            </p>
          )}
        </div>
      </button>
      {children && <div className="p-3 pt-0 mt-auto">{children}</div>}
    </Card>
  );
}
export const PosterGrid = ({ children }: { children: ReactNode }) => (
  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
    {children}
  </div>
);
export function More({
  show,
  pending,
  onClick,
}: {
  show: boolean;
  pending: boolean;
  onClick: () => unknown;
}) {
  return show ? (
    <div className="flex justify-center">
      <Button
        variant="secondary"
        isLoading={pending}
        disabled={pending}
        onClick={() => {
          void onClick();
        }}
      >
        Carregar mais
      </Button>
    </div>
  ) : null;
}
export function Dialog({
  title,
  children,
  onClose,
  busy = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  busy?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null),
    closeRef = useRef(onClose),
    busyRef = useRef(busy),
    id = useId();
  closeRef.current = onClose;
  busyRef.current = busy;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    ref.current?.focus();
    window.dispatchEvent(new CustomEvent('source:dialog', { detail: true }));
    const close = (event?: Event) => {
      event?.preventDefault();
      if (!busyRef.current) closeRef.current();
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        close();
      }
      if (e.key === 'Tab') {
        const nodes = Array.from(
          ref.current?.querySelectorAll<HTMLElement>(
            'button:not([disabled]),input:not([disabled]),select,textarea,[href],[tabindex="0"]',
          ) || [],
        );
        const first = nodes[0],
          last = nodes[nodes.length - 1];
        if (!first) {
          e.preventDefault();
          return;
        }
        if (
          e.shiftKey &&
          (document.activeElement === first || document.activeElement === ref.current)
        ) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener('keydown', key);
    window.addEventListener('source:back', close);
    return () => {
      document.removeEventListener('keydown', key);
      window.removeEventListener('source:back', close);
      window.dispatchEvent(new CustomEvent('source:dialog', { detail: false }));
      previous?.focus();
    };
  }, []);
  return createPortal(
    <div
      className="source-safe-overlay fixed inset-0 z-[150] bg-black/70 flex items-end sm:items-center justify-center p-3 sm:p-6 native-dialog-backdrop"
      onClick={() => {
        if (!busy) onClose();
      }}
    >
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={id}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        className="source-safe-panel w-full max-w-lg max-h-[85vh] supports-[height:100dvh]:max-h-[85dvh] overflow-y-auto bg-zinc-950 border border-white/10 rounded-xl p-5 space-y-5 shadow-2xl outline-none"
      >
        <div className="flex items-start justify-between gap-3">
          <h2 id={id} className="min-w-0 break-words text-sm font-bold text-zinc-100 uppercase tracking-tight">
            {title}
          </h2>
          <Button
            variant="ghost"
            size="sm"
            disabled={busy}
            onClick={onClose}
            aria-label="Fechar"
            className="p-0 w-9 shrink-0"
          >
            <X size={18} />
          </Button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  );
}
export const Field = ({ label, children }: { label: string; children: ReactNode }) => (
  <label className="block space-y-2">
    <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">{label}</span>
    {children}
  </label>
);
export const fieldClass =
  'w-full rounded-md border border-white/10 bg-zinc-950 text-zinc-100 p-3 text-xs outline-none focus:border-brand-accent';
export const Busy = () => (
  <Loader2 aria-label="Carregando" className="animate-spin text-zinc-600" size={22} />
);
