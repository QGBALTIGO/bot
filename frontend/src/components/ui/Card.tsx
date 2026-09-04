import { HTMLMotionProps, m } from 'framer-motion';
import React from 'react';
import { cn } from '../../utils';

type CardVariant = 'default' | 'glass' | 'outline' | 'surface' | 'accent';

interface CardProps
  extends Omit<
    React.HTMLAttributes<HTMLDivElement>,
    'onAnimationStart' | 'onDrag' | 'onDragStart' | 'onDragEnd'
  > {
  variant?: CardVariant;
  hover?: boolean;
  withCorner?: boolean;
}

export const Card = React.forwardRef<HTMLDivElement, CardProps>(
  (
    { className, variant = 'default', hover = false, withCorner = false, children, ...props },
    ref,
  ) => {
    const variants: Record<CardVariant, string> = {
      default: 'bg-brand-deep border border-white/5',
      glass: 'glass-panel',
      outline: 'bg-transparent border border-white/10',
      surface: 'bg-brand-surface border border-white/5',
      accent: 'bg-brand-accent/5 border border-brand-accent/20',
    };

    return (
      <m.div
        ref={ref as any}
        className={cn(
          'rounded-md transition-all relative overflow-hidden',
          variants[variant],
          hover && 'hover:border-white/20 active:scale-[0.995]',
          withCorner && 'corner-accent',
          className,
        )}
        {...(props as HTMLMotionProps<'div'>)}
      >
        {children}
      </m.div>
    );
  },
);

Card.displayName = 'Card';
