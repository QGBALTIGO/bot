import 'react';
import { cn } from '../../utils';

export const Skeleton = ({ className }: { className?: string }) => (
  <div className={cn('bg-zinc-900 overflow-hidden relative rounded shimmer', className)} />
);

export const CardSkeleton = () => (
  <div className="rounded-md bg-zinc-950 border border-white/5 overflow-hidden aspect-[3/4.2] relative">
    <div className="absolute bottom-0 inset-x-0 p-3 space-y-2">
      <Skeleton className="h-3 w-4/5 rounded-sm" />
      <Skeleton className="h-2 w-1/2 rounded-sm opacity-50" />
      <div className="flex justify-between items-center gap-2 pt-1">
        <Skeleton className="h-4 w-10 rounded-sm" />
      </div>
    </div>
  </div>
);
