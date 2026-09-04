import React from 'react';
import { cn } from '../../utils';

type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger' | 'accent' | 'glass';
type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  isLoading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant = 'primary',
      size = 'md',
      isLoading,
      children,
      disabled,
      leftIcon,
      rightIcon,
      ...props
    },
    ref,
  ) => {
    const variants: Record<ButtonVariant, string> = {
      primary: 'bg-white text-zinc-950 hover:bg-zinc-200 active:scale-[0.98]',
      secondary:
        'bg-zinc-900 text-zinc-100 border border-white/10 hover:bg-zinc-800 active:scale-[0.98]',
      outline:
        'bg-transparent border border-white/10 text-zinc-300 hover:bg-white/5 active:scale-[0.98]',
      ghost: 'bg-transparent text-zinc-500 hover:text-zinc-200 hover:bg-white/5',
      danger:
        'bg-red-500/10 text-red-500 border border-red-500/20 hover:bg-red-500/20 active:scale-[0.98]',
      accent:
        'bg-brand-accent text-white hover:bg-brand-accent/90 shadow-[0_4px_12px_rgba(59,130,246,0.2)] active:scale-[0.98]',
      glass: 'glass-panel text-white hover:bg-white/10 active:scale-[0.98]',
    };

    const sizes: Record<ButtonSize, string> = {
      sm: 'h-8 px-3 text-[10px] font-bold uppercase tracking-wider rounded-sm',
      md: 'h-10 px-5 text-[11px] font-extrabold uppercase tracking-widest rounded-md',
      lg: 'h-12 px-7 text-xs font-black uppercase tracking-[0.15em] rounded-lg',
    };

    return (
      <button
        ref={ref}
        disabled={isLoading || disabled}
        className={cn(
          'inline-flex items-center justify-center gap-2.5 transition-all focus:outline-none focus:ring-2 focus:ring-brand-accent/40 disabled:opacity-40 disabled:pointer-events-none whitespace-nowrap overflow-hidden relative',
          variants[variant],
          sizes[size],
          className,
        )}
        {...props}
      >
        <div
          className={cn(
            'flex items-center justify-center gap-2 transition-all duration-200',
            isLoading ? 'opacity-0 scale-95' : 'opacity-100 scale-100',
          )}
        >
          {leftIcon && <span className="shrink-0 opacity-80">{leftIcon}</span>}
          {children}
          {rightIcon && <span className="shrink-0 opacity-80">{rightIcon}</span>}
        </div>

        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent opacity-40" />
          </div>
        )}
      </button>
    );
  },
);

Button.displayName = 'Button';
