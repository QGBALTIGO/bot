/** One viewport controller for every Source entry route (Bot API 8.0+).
 * https://core.telegram.org/bots/webapps#initializing-mini-apps
 * The OS safe area and the Telegram content area are separate margins.
 * Neither expand() nor CSS 100vh is a replacement for requestFullscreen().
 */
export function installTelegramViewport(): () => void {
  const root = document.documentElement;
  let tg: TelegramWebApp | undefined;
  let disposed = false;
  let frame = 0;
  let requestTimer = 0;
  let requested = false;
  let waiting = false;
  let contentReported = false;
  const events: Array<[string, (...args: any[]) => void]> = [];

  const write = (name: string, value: string) => {
    if (root.style.getPropertyValue(name) !== value) root.style.setProperty(name, value);
  };
  const pixels = (value: unknown) =>
    typeof value === 'number' && Number.isFinite(value) ? Math.max(0, value) : 0;
  const supports = (version: string) => {
    try {
      if (tg?.isVersionAtLeast) return tg.isVersionAtLeast(version);
      const current = (tg?.version || '0').split('.').map(Number);
      const needed = version.split('.').map(Number);
      return (current[0] || 0) > (needed[0] || 0) ||
        ((current[0] || 0) === (needed[0] || 0) && (current[1] || 0) >= (needed[1] || 0));
    } catch { return false; }
  };
  const invoke = (action: (() => unknown) | undefined) => {
    try { action?.(); } catch { /* An old/native client may expose unsupported stubs. */ }
  };

  const sync = () => {
    frame = 0;
    if (disposed) return;
    const native = Boolean(tg && (tg.initData || (tg.platform && tg.platform !== 'unknown')));
    const fullscreen = native && Boolean(tg?.isFullscreen);
    root.dataset.sourceFullscreen = fullscreen ? 'true' : 'false';
    root.dataset.sourceViewport = native ? (fullscreen ? 'fullscreen' : 'expanded') : 'browser';
    const mobile = tg?.platform === 'ios' || tg?.platform === 'android';
    for (const side of ['top', 'bottom', 'left', 'right'] as const) {
      const device = native ? pixels(tg?.safeAreaInset?.[side]) : 0;
      let content = native ? pixels(tg?.contentSafeAreaInset?.[side]) : 0;
      // Protect controls during the first native transition, before insets arrive.
      // A reported zero is authoritative; don't impose a permanent guessed margin.
      if (side === 'top' && mobile && (waiting || fullscreen) && !contentReported && !content) content = 56;
      write(`--source-device-${side}`, `${device}px`);
      write(`--source-content-${side}`, `${content}px`);
    }
    const visual = window.visualViewport;
    const input = document.activeElement;
    const editing = input instanceof HTMLElement &&
      (input.matches('input, textarea, select') || input.isContentEditable);
    let height = native && pixels(tg?.viewportStableHeight)
      ? pixels(tg?.viewportStableHeight) : window.innerHeight;
    let top = 0;
    // Keyboard-only visual resizing: don't reflow the app while pinch-zooming.
    if (editing && visual && Math.abs(visual.scale - 1) < 0.05 && visual.height > 0) {
      height = Math.min(height, visual.height);
      top = Math.max(0, visual.offsetTop);
    }
    write('--source-viewport-height', `${Math.max(1, height)}px`);
    write('--source-viewport-top', `${top}px`);
  };
  const schedule = () => { if (!disposed && !frame) frame = requestAnimationFrame(sync); };
  const colors = () => {
    // The shared Source canvas is dark even when Telegram itself uses light mode.
    // A matching header color gives native Close/status controls correct contrast.
    const bg = supports('6.9') ? '#09090b' : (tg?.themeParams?.bg_color || '#09090b');
    invoke(() => tg?.setHeaderColor?.(bg));
    invoke(() => tg?.setBackgroundColor?.('#09090b'));
    if (supports('7.10')) invoke(() => tg?.setBottomBarColor?.('#09090b'));
    root.style.colorScheme = 'dark';
  };
  const listen = (event: string, handler: (...args: any[]) => void) => {
    invoke(() => tg?.onEvent?.(event, handler));
    events.push([event, handler]);
  };
  const connect = () => {
    if (disposed || tg) return;
    const candidate = window.Telegram?.WebApp;
    if (!candidate) return;
    tg = candidate;
    listen('viewportChanged', schedule);
    listen('safeAreaChanged', schedule);
    listen('contentSafeAreaChanged', () => { contentReported = true; schedule(); });
    listen('fullscreenChanged', () => {
      waiting = false;
      window.clearTimeout(requestTimer);
      colors();
      schedule();
      // Respect manual exit. Never re-enter on navigation, focus or resize.
    });
    listen('fullscreenFailed', () => {
      waiting = false;
      window.clearTimeout(requestTimer);
      if (!tg?.isFullscreen) invoke(() => tg?.expand?.());
      schedule();
    });
    listen('activated', schedule);
    listen('themeChanged', colors);
    colors();
    sync();
    invoke(() => tg?.ready?.());
    const native = Boolean(tg.initData || (tg.platform && tg.platform !== 'unknown'));
    if (!native) return;
    if (tg.isFullscreen) return;
    invoke(() => tg?.expand?.());
    if (!requested && supports('8.0') && typeof tg.requestFullscreen === 'function') {
      requested = true;
      waiting = true;
      sync();
      requestTimer = window.setTimeout(() => { waiting = false; schedule(); }, 1800);
      try { tg.requestFullscreen(); }
      catch { waiting = false; window.clearTimeout(requestTimer); schedule(); }
    }
  };
  const onScriptLoad = (event: Event) => {
    if (event.target instanceof HTMLScriptElement &&
        event.target.src.includes('telegram.org/js/telegram-web-app.js')) connect();
  };
  window.addEventListener('resize', schedule, { passive: true });
  window.addEventListener('orientationchange', schedule, { passive: true });
  window.visualViewport?.addEventListener('resize', schedule, { passive: true });
  window.visualViewport?.addEventListener('scroll', schedule, { passive: true });
  document.addEventListener('focusin', schedule);
  document.addEventListener('focusout', schedule);
  document.addEventListener('load', onScriptLoad, true);
  document.addEventListener('DOMContentLoaded', connect, { once: true });
  window.addEventListener('load', connect, { once: true });
  sync();
  connect();
  return () => {
    disposed = true;
    if (frame) cancelAnimationFrame(frame);
    window.clearTimeout(requestTimer);
    events.forEach(([event, handler]) => invoke(() => tg?.offEvent?.(event, handler)));
    window.removeEventListener('resize', schedule);
    window.removeEventListener('orientationchange', schedule);
    window.visualViewport?.removeEventListener('resize', schedule);
    window.visualViewport?.removeEventListener('scroll', schedule);
    document.removeEventListener('focusin', schedule);
    document.removeEventListener('focusout', schedule);
    document.removeEventListener('load', onScriptLoad, true);
    document.removeEventListener('DOMContentLoaded', connect);
    window.removeEventListener('load', connect);
  };
}
