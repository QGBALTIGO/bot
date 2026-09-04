import React from 'react';
import { cn } from '../../utils';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  icon?: React.ElementType;
  error?: string | undefined;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, icon: Icon, error, ...props }, ref) => {
    return (
      <div className="space-y-1.5 w-full">
        <div className="relative group">
          {Icon && (
            <Icon
              size={14}
              className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-500 group-focus-within:text-brand-accent transition-colors duration-200"
            />
          )}
          <input
            ref={ref}
            className={cn(
              'w-full bg-zinc-950 border border-white/10 rounded-md py-2.5 text-[11px] font-medium transition-all duration-200 placeholder:text-zinc-600 text-zinc-100 outline-none focus:border-brand-accent focus:ring-4 focus:ring-brand-accent/5 tracking-normal',
              Icon ? 'pl-10 pr-4' : 'px-4',
              error && 'border-red-500/50 focus:border-red-500 focus:ring-red-500/5',
              className,
            )}
            {...props}
          />
        </div>
        {error && (
          <p className="text-[9px] font-bold text-red-500 uppercase tracking-widest pl-1">
            {error}
          </p>
        )}
      </div>
    );
  },
);

Input.displayName = 'Input';
