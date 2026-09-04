import { AlertCircle, CheckCircle2, Terminal, X } from 'lucide-react';
import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from 'react';
import { cn } from '../../utils';

interface Toast {
  id: string;
  message: string;
  type: 'success' | 'error' | 'info';
}

interface ToastContextType {
  addToast: (message: string, type?: 'success' | 'error' | 'info') => void;
}

const ToastContext = createContext<ToastContextType | null>(null);

export const ToastProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((message: string, type: 'success' | 'error' | 'info' = 'info') => {
    const id = crypto.randomUUID();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(
      () => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      },
      type === 'error' ? 6000 : 4000,
    );
  }, []);

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      <div className="fixed top-16 left-1/2 -translate-x-1/2 z-[1000] w-full max-w-[400px] px-6 pointer-events-none flex flex-col items-center space-y-2">
        {toasts.map((toast) => (
          <ToastItem key={toast.id} toast={toast} onClose={() => removeToast(toast.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
};

const ToastItem: React.FC<{ toast: Toast; onClose: () => void }> = ({ toast, onClose }) => {
  const [exiting, setExiting] = useState(false);
  const duration = toast.type === 'error' ? 6000 : 4000;

  useEffect(() => {
    const t = setTimeout(() => {
      setExiting(true);
      setTimeout(onClose, 200);
    }, duration);
    return () => clearTimeout(t);
  }, [duration, onClose]);

  return (
    <div
      className={cn(
        'w-full pointer-events-auto transition-all duration-200',
        exiting
          ? 'opacity-0 scale-95'
          : 'opacity-100 scale-100 animate-[toast-in_0.2s_ease-out]',
      )}
    >
      <div className="bg-zinc-900/90 backdrop-blur-md border border-white/10 rounded-md p-3.5 shadow-2xl flex items-center gap-3.5 relative overflow-hidden">
        <div
          className={cn(
            'w-8 h-8 rounded flex items-center justify-center shrink-0 border',
            toast.type === 'success'
              ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20'
              : toast.type === 'error'
                ? 'bg-red-500/10 text-red-500 border-red-500/20'
                : 'bg-brand-accent/10 text-brand-accent border-brand-accent/20',
          )}
        >
          {toast.type === 'success' ? (
            <CheckCircle2 size={16} strokeWidth={2.5} />
          ) : toast.type === 'error' ? (
            <AlertCircle size={16} strokeWidth={2.5} />
          ) : (
            <Terminal size={16} strokeWidth={2.5} />
          )}
        </div>

        <div className="flex-1 min-w-0">
          <p
            title={toast.message}
            className="text-[11px] font-bold text-zinc-100 uppercase tracking-tight line-clamp-2"
          >
            {toast.message}
          </p>
        </div>

        <button
          onClick={onClose}
          className="w-6 h-6 rounded flex items-center justify-center text-zinc-600 hover:text-zinc-100 transition-colors"
        >
          <X size={14} strokeWidth={3} />
        </button>

        <div className="absolute bottom-0 left-0 h-0.5 bg-white/5 w-full">
          <div
            className={cn(
              'h-full origin-left',
              toast.type === 'success'
                ? 'bg-emerald-500/50'
                : toast.type === 'error'
                  ? 'bg-red-500/50'
                  : 'bg-brand-accent/50',
            )}
            style={{
              animation: `toast-bar ${duration}ms linear forwards`,
            }}
          />
        </div>
      </div>
    </div>
  );
};

export const useToast = () => {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
};
