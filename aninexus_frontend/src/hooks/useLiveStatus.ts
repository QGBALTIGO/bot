import { useEffect, useState } from 'react';

const HEALTH_PATH = `/api/${import.meta.env.VITE_API_PREFIX ?? 'v1_7b82'}/healthz`;
const PROBE_INTERVAL_MS = 30000;

/**
 * Shared backend liveness probe. Pings the public /healthz endpoint —
 * works on every host (some block or misroute WebSocket upgrades, which
 * made the old WS probe show OFFLINE forever). Rechecks every 30s.
 */
export const useLiveStatus = () => {
  const [live, setLive] = useState(false);

  useEffect(() => {
    const apiBase = import.meta.env.VITE_API_URL ?? '';
    let cancelled = false;
    let timer: number | undefined;

    const probe = async () => {
      try {
        const res = await fetch(`${apiBase}${HEALTH_PATH}`, {
          signal: AbortSignal.timeout(5000),
        });
        if (!cancelled) setLive(res.ok);
      } catch {
        if (!cancelled) setLive(false);
      } finally {
        if (!cancelled) timer = window.setTimeout(probe, PROBE_INTERVAL_MS);
      }
    };

    probe();

    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, []);

  return live;
};
