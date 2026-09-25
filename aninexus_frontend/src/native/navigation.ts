import routeManifest from './routes.json';

export const NATIVE_TABS = [
  'cards',
  'catalog_anime',
  'catalog_manga',
  'album',
  'requests',
  'contribute',
  'memory',
  'subscription',
  'settings',
  'terms',
];
export const NATIVE_ALIASES: Record<string, string> = {
  cards: 'cards',
  catalogo: 'catalog_anime',
  animes: 'catalog_anime',
  mangas: 'catalog_manga',
  cccolecao: 'album',
  album: 'album',
  pedido: 'requests',
  pedidos: 'requests',
  contrib: 'contribute',
  memoria: 'memory',
  memory: 'memory',
  baltigoflix: 'subscription',
  loja: 'shop',
  settings: 'settings',
  configuracoes: 'settings',
  terms: 'terms',
};
const routes: Record<string, { tab: string; params?: Record<string, string> }> = routeManifest;
const path = () => window.location.pathname.replace(/\/+$/, '') || '/';

export function legacyRoute() {
  const entry = routes[path()];
  return entry ? { tab: entry.tab, alias: entry.tab } : null;
}
export function nativeParams() {
  const params = new URLSearchParams(routes[path()]?.params || {});
  new URLSearchParams(window.location.search).forEach((value, key) => params.set(key, value));
  const hashQuery = window.location.hash.split('?')[1];
  if (hashQuery) new URLSearchParams(hashQuery).forEach((value, key) => params.set(key, value));
  return params;
}
export function nativeRouteKey(tab: string) {
  const params = nativeParams();
  return [
    tab,
    ...['anime_id', 'name', 'view', 'q', 'level', 'character_id', 'pending', 'section', 'lang'].map(
      (k) => params.get(k) || '',
    ),
  ].join(':');
}
export function navigationDepth() {
  return Number(window.history.state?.sourceDepth || 0);
}
export function navigateNative(tab: string, params: Record<string, string | number> = {}) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) query.set(key, String(value));
  const target = `/menu${query.size ? `?${query}` : ''}#${encodeURIComponent(tab)}`;
  if (`${window.location.pathname}${window.location.search}${window.location.hash}` === target)
    return;
  window.dispatchEvent(new Event('source:willnavigate'));
  window.history.pushState({ sourceDepth: navigationDepth() + 1 }, '', target);
  window.dispatchEvent(new Event('source:navigate'));
}
export function openExternal(url: string) {
  const parsed = new URL(url);
  if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:')
    throw new Error('Link inválido.');
  const tg = window.Telegram?.WebApp;
  if (['t.me', 'telegram.me'].includes(parsed.hostname) && tg?.openTelegramLink)
    tg.openTelegramLink(parsed.href);
  else if (tg?.openLink) tg.openLink(parsed.href);
  else window.open(parsed.href, '_blank', 'noopener,noreferrer');
}
