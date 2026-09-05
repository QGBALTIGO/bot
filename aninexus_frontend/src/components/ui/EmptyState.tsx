import 'react';
import { type LucideIcon, PackageOpen } from 'lucide-react';

interface EmptyStateProps {
  icon?: LucideIcon;
  title?: string;
  message?: string;
}

export const EmptyState = ({
  icon: Icon = PackageOpen,
  title = 'Nada por aqui',
  message = 'Nenhum registro encontrado.',
}: EmptyStateProps) => (
  <div className="py-12 px-6 text-center flex flex-col items-center select-none">
    <div className="w-12 h-12 rounded-full bg-zinc-900 border border-white/5 flex items-center justify-center mb-4">
      <Icon size={20} className="text-zinc-500" />
    </div>
    <h3 className="text-xs font-bold text-zinc-300 uppercase tracking-widest mb-1">{title}</h3>
    <p className="text-[10px] text-zinc-500 font-medium uppercase tracking-widest max-w-[200px] leading-relaxed">
      {message}
    </p>
  </div>
);
