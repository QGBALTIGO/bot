import { lazy } from 'react';
const Catalog = lazy(() => import('./Catalogs').then((m) => ({ default: m.Catalog })));
const Cards = lazy(() => import('./Catalogs').then((m) => ({ default: m.Cards })));
const Album = lazy(() => import('./Catalogs').then((m) => ({ default: m.Album })));
const Requests = lazy(() => import('./Requests').then((m) => ({ default: m.Requests })));
const Contribute = lazy(() => import('./Requests').then((m) => ({ default: m.Contribute })));
const Memory = lazy(() => import('./Memory').then((m) => ({ default: m.Memory })));
const Settings = lazy(() => import('./Account').then((m) => ({ default: m.Settings })));
const Terms = lazy(() => import('./Services').then((m) => ({ default: m.Terms })));
const Subscription = lazy(() => import('./Services').then((m) => ({ default: m.Subscription })));
export function NativeScreens({ tab }: { tab: string }) {
  switch (tab) {
    case 'catalog_anime':
      return <Catalog />;
    case 'catalog_manga':
      return <Catalog manga />;
    case 'cards':
      return <Cards />;
    case 'album':
      return <Album />;
    case 'requests':
      return <Requests />;
    case 'contribute':
      return <Contribute />;
    case 'memory':
      return <Memory />;
    case 'settings':
      return <Settings />;
    case 'terms':
      return <Terms />;
    case 'subscription':
      return <Subscription />;
    default:
      return null;
  }
}
