import React from 'react';
import { cn } from '../../utils';

type BadgeVariant =
  | 'primary'
  | 'secondary'
  | 'outline'
  | 'success'
  | 'warning'
  | 'danger'
  | 'premium'
  | 'rare'
  | 'epic'
  | 'mythic';
type BadgeSize = 'xs' | 'sm';

interface BadgeProps {
  children: React.ReactNode;
  variant?: BadgeVariant;
  size?: BadgeSize;
  className?: string;
  icon?: React.ElementType;
}

export const Badge = ({
  children,
  variant = 'primary',
  size = 'sm',
  className,
  icon: Icon,
}: BadgeProps) => {
  const variants: Record<BadgeVariant, string> = {
    primary: 'bg-brand-accent/10 text-brand-accent border-brand-accent/20',
    secondary: 'bg-white/5 text-zinc-400 border-white/10',
    outline: 'bg-transparent text-zinc-500 border-white/10',
    success: 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20',
    warning: 'bg-amber-500/10 text-amber-500 border-amber-500/20',
    danger: 'bg-red-500/10 text-red-500 border-red-500/20',
    premium: 'bg-amber-400/10 text-amber-400 border-amber-400/20',
    rare: 'bg-cyan-500/10 text-cyan-500 border-cyan-500/20',
    epic: 'bg-purple-500/10 text-purple-500 border-purple-500/20',
    mythic: 'bg-fuchsia-500/10 text-fuchsia-400 border-fuchsia-500/30',
  };

  const sizes: Record<BadgeSize, string> = {
    xs: 'px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-wider rounded-[2px]',
    sm: 'px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-widest rounded-sm',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 border whitespace-nowrap select-none transition-colors duration-200',
        variants[variant],
        sizes[size],
        className,
      )}
    >
      {Icon && <Icon size={size === 'xs' ? 8 : 10} strokeWidth={2.5} className="shrink-0" />}
      <span className="leading-none">{children}</span>
    </span>
  );
};
