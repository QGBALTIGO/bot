import 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { Button } from './Button';

interface ErrorStateProps {
  title?: string;
  message?: string;
  actionLabel?: string;
  onAction?: () => void;
}

export const ErrorState = ({
  title = 'Connection failed',
  message = 'Could not reach the ANINEXUS server. Check your connection and retry.',
  actionLabel = 'Try again',
  onAction,
}: ErrorStateProps) => (
  <div className="py-10 px-6 bg-red-500/5 border border-red-500/10 rounded-md text-center flex flex-col items-center">
    <div className="w-10 h-10 rounded-full bg-red-500/10 border border-red-500/20 flex items-center justify-center mb-4">
      <AlertCircle size={20} className="text-red-500" />
    </div>
    <h3 className="text-sm font-bold text-zinc-100 uppercase tracking-widest mb-1">{title}</h3>
    <p className="text-[10px] text-zinc-500 font-medium uppercase tracking-widest max-w-[220px] leading-relaxed">
      {message}
    </p>
    {onAction && (
      <Button
        variant="outline"
        size="sm"
        onClick={onAction}
        className="mt-6 border-red-500/20 text-red-500 hover:bg-red-500/10 h-9 px-6"
      >
        <RefreshCw size={12} className="mr-2" />
        {actionLabel}
      </Button>
    )}
  </div>
);
