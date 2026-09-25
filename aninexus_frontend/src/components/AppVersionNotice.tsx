import { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { Button } from './ui/Button';

declare const __SOURCE_UI_VERSION__: string;

/** Check on resume, not on every action. Never silently reload purchases or unfinished forms. */
export function AppVersionNotice() {
  const [outdated, setOutdated] = useState(false);
  useEffect(() => {
    let lastCheck = 0;
    let disposed = false;
    let pending = false;
    let controller: AbortController | undefined;
    const check = async () => {
      if (pending || document.visibilityState === 'hidden' || Date.now() - lastCheck < 60000) return;
      controller = new AbortController();
      pending = true;
      lastCheck = Date.now();
      const timeout = window.setTimeout(() => controller?.abort(), 8000);
      try {
        const response = await fetch('/api/native/version', { cache: 'no-store', signal: controller.signal });
        if (!response.ok) return;
        const data = await response.json();
        if (!disposed && /^[a-f0-9]{16}$/.test(data.version || ''))
          setOutdated(data.version !== __SOURCE_UI_VERSION__);
      } catch {
        // Version availability never blocks the app or reauthenticates the account.
      } finally {
        pending = false;
        window.clearTimeout(timeout);
      }
    };
    const resume = () => { void check(); };
    void check();
    const telegram = window.Telegram?.WebApp;
    telegram?.onEvent?.('activated', resume);
    document.addEventListener('visibilitychange', resume);
    window.addEventListener('pageshow', resume);
    window.addEventListener('focus', resume);
    return () => {
      disposed = true;
      controller?.abort();
      telegram?.offEvent?.('activated', resume);
      document.removeEventListener('visibilitychange', resume);
      window.removeEventListener('pageshow', resume);
      window.removeEventListener('focus', resume);
    };
  }, []);
  if (!outdated) return null;
  return (
    <div data-source-version-notice role="status" className="shrink-0 flex flex-wrap items-center justify-between gap-2 border-b border-white/10 bg-zinc-900 px-4 py-2">
      <p className="text-xs text-zinc-300">Há uma versão nova do Source.</p>
      <Button size="sm" variant="secondary" leftIcon={<RefreshCw size={12} />} onClick={() => {
        if (window.confirm('Recarregar o aplicativo? Conclua operações e salve alterações pendentes antes de continuar.')) window.location.reload();
      }}>Atualizar aplicativo</Button>
    </div>
  );
}
