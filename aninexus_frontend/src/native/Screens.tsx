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
const CollectionTools = lazy(() => import('../features/collecting/CollectionTools').then(m => ({default:m.CollectionTools})));
const Workshop = lazy(() => import('../features/collecting/Workshop').then(m => ({default:m.Workshop})));
const Marketplace = lazy(() => import('../features/collecting/Marketplace').then(m => ({default:m.Marketplace})));
const Events = lazy(() => import('../features/collecting/Events').then(m => ({default:m.Events})));
const Activity = lazy(() => import('../features/collecting/Activity').then(m => ({default:m.Activity})));
const Help = lazy(() => import('../features/collecting/Activity').then(m => ({default:m.Help})));
const Identify = lazy(() => import('../features/collecting/Discovery').then(m => ({default:m.Identify})));
const DiceInfo = lazy(() => import('../features/collecting/Discovery').then(m => ({default:m.DiceInfo})));
export function NativeScreens({ tab }: { tab: string }) {
  switch (tab) {
    case 'collecting': return <CollectionTools/>;
    case 'workshop': return <Workshop/>;
    case 'marketplace': return <Marketplace/>;
    case 'events': return <Events/>;
    case 'activity': return <Activity/>;
    case 'help': return <Help/>;
    case 'identify': return <Identify/>;
    case 'dice_info': return <DiceInfo/>;
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
