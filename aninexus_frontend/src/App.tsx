import {
  legacyRoute,
  NATIVE_ALIASES,
  NATIVE_TABS,
  nativeRouteKey,
  navigateNative,
  navigationDepth,
} from './native/navigation';
import { NativeScreens } from './native/Screens';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import React, { lazy, ReactNode, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { CharActionModal } from './components/character/CharActionModal';
import { Header } from './components/Header';
import { IntroLoading, type IntroStatus } from './components/IntroLoading';
import { NavigationDrawer } from './components/NavigationDrawer';
import { PetActionModal } from './components/pet/PetActionModal';
import { GachaReveal } from './components/ui/GachaReveal';
import { ToastProvider } from './components/ui/Toast';
import { UserProvider, useUser } from './context/UserContext';
import { Forbidden } from './pages/Forbidden';
import { NotFound } from './pages/NotFound';
import { Profile } from './pages/Profile';
import { ServerError } from './pages/ServerError';

// Lazy load all pages
const Shop = lazy(() => import('./native/ShopExtras').then((m) => ({ default: m.Shop })));
const Gallery = lazy(() => import('./pages/Gallery').then((m) => ({ default: m.Gallery })));
const PetShop = lazy(() => import('./pages/PetShop').then((m) => ({ default: m.PetShop })));
const Hatchery = lazy(() => import('./pages/Hatchery').then((m) => ({ default: m.Hatchery })));
const Quests = lazy(() => import('./pages/Quests').then((m) => ({ default: m.Quests })));
const Pass = lazy(() => import('./pages/Pass').then((m) => ({ default: m.Pass })));
const Leaderboard = lazy(() =>
  import('./pages/Leaderboard').then((m) => ({ default: m.Leaderboard })),
);
const Referrals = lazy(() => import('./pages/Referrals').then((m) => ({ default: m.Referrals })));
const Achievements = lazy(() =>
  import('./pages/Achievements').then((m) => ({ default: m.Achievements })),
);
const MyPets = lazy(() => import('./pages/MyPets').then((m) => ({ default: m.MyPets })));
const Exchange = lazy(() => import('./pages/Exchange').then((m) => ({ default: m.Exchange })));
const Upload = lazy(() => import('./pages/MediaAdmin').then((m) => ({ default: m.MediaAdmin })));
const Staff = lazy(() => import('./pages/Staff').then((m) => ({ default: m.Staff })));
const Minigames = lazy(() => import('./pages/Minigames').then((m) => ({ default: m.Minigames })));
const Trading = lazy(() => import('./pages/Trading').then((m) => ({ default: m.Trading })));
const Dado = lazy(() => import('./pages/Dado').then((m) => ({ default: m.Dado })));
const Duels = lazy(() => import('./pages/Duels').then((m) => ({ default: m.Duels })));
const Bonds = lazy(() => import('./pages/Bonds').then((m) => ({ default: m.Bonds })));

const VALID_TABS = [
  ...NATIVE_TABS,
  'profile',
  'dado',
  'incubation',
  'shop',
  'exchange',
  'gallery',
  'pets',
  'referrals',
  'quests',
  'pass',
  'leaderboard',
  'achievements',
  'mypets',
  'upload',
  'staff',
  'minigames',
  'trading',
  'duels',
  'bonds',
];
const TAB_ALIASES: Record<string, string> = {
  ...NATIVE_ALIASES,
  profile: 'profile',
  dado: 'dado',
  dice: 'dado',
  roll: 'dado',
  home: 'profile',
  me: 'profile',
  harem: 'profile',
  collection: 'profile',
  inventory: 'profile',
  eggs: 'incubation',
  egg: 'incubation',
  hatch: 'incubation',
  hatching: 'incubation',
  incubation: 'incubation',
  incubator: 'incubation',
  shop: 'shop',
  market: 'shop',
  cshop: 'shop',
  store: 'shop',
  daily_shop: 'shop',
  dailyshop: 'shop',
  exchange: 'exchange',
  currency: 'exchange',
  currencies: 'exchange',
  conversion: 'exchange',
  convert: 'exchange',
  zenith: 'exchange',
  shard: 'exchange',
  shards: 'exchange',
  gallery: 'gallery',
  catalog: 'gallery',
  characters: 'gallery',
  pets: 'pets',
  petshop: 'pets',
  pet_store: 'pets',
  companionshop: 'pets',
  mypets: 'mypets',
  mypet: 'mypets',
  pet: 'mypets',
  companions: 'mypets',
  upload: 'upload',
  uploads: 'upload',
  admin: 'upload',
  sudo: 'staff',
  sudos: 'staff',
  staff: 'staff',
  contributors: 'staff',
  contributions: 'staff',
  referrals: 'referrals',
  referral: 'referrals',
  invite: 'referrals',
  quests: 'quests',
  quest: 'quests',
  tasks: 'quests',
  task: 'quests',
  missions: 'quests',
  pass: 'pass',
  battlepass: 'pass',
  battle_pass: 'pass',
  bp: 'pass',
  leaderboard: 'leaderboard',
  leaderboards: 'leaderboard',
  top: 'leaderboard',
  ranks: 'leaderboard',
  achievements: 'achievements',
  achievement: 'achievements',
  badges: 'achievements',
  minigames: 'minigames',
  games: 'minigames',
  nexus_games: 'minigames',
  trading: 'trading',
  trade: 'trading',
  trades: 'trading',
  swap: 'trading',
  duel: 'duels',
  duels: 'duels',
  battle: 'duels',
  combat: 'duels',
  bond: 'bonds',
  bonds: 'bonds',
  relationship: 'bonds',
  relationships: 'bonds',
  marriage: 'bonds',
  vinculo: 'bonds',
  vinculos: 'bonds',
};

interface RouteTarget {
  tab: string;
  alias: string;
}

const normalizeRouteToken = (value?: string | null) => {
  if (!value) return null;

  let token = value.trim();
  try {
    token = decodeURIComponent(token);
  } catch {
    // ignore
  }

  token =
    token
      .toLowerCase()
      .replace(/^https?:\/\/[^/]+/i, '')
      .replace(/^#/, '')
      .replace(/^[?/]+/, '')
      .split(/[?&#=]/)[0] ?? ''.replace(/^\/+|\/+$/g, '');

  const lastSegment = token.split('/').filter(Boolean).pop() || token;
  return lastSegment.replace(/[-\s]+/g, '_').replace(/[^a-z0-9_]/g, '') || null;
};

const resolveRouteToken = (value?: string | null): RouteTarget | null => {
  const alias = normalizeRouteToken(value);
  if (!alias) return null;

  const tab = TAB_ALIASES[alias] || alias;
  return { tab, alias };
};

const getCandidates = () => {
  const params = new URLSearchParams(window.location.search);
  const hashParts = window.location.hash.replace(/^#/, '').split(/[?&]/);
  // Telegram injects its own data into the URL fragment
  // (#tgWebAppData=...&tgWebAppStartParam=...&tgWebAppVersion=...).
  // Those are key=value pairs, while our route tokens are plain segments,
  // so only accept segments without '=' as routes to avoid a false 404.
  const routeHash = hashParts.find((part) => part && !part.includes('=')) ?? null;
  const startParamFromHash =
    hashParts.map((part) => part.split('=')).find(([key]) => key === 'tgWebAppStartParam')?.[1] ??
    null;
  return [
    routeHash,
    startParamFromHash,
    params.get('tgWebAppStartParam'),
    params.get('startapp'),
    params.get('tab'),
    params.get('route'),
  ];
};

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return <ServerError onRetry={() => window.location.reload()} />;
    }
    return this.props.children;
  }
}

// Restores the saved scroll position for a tab after its content mounts.
// Rendered inside the keyed page wrapper so it remounts on every tab switch.
const ScrollRestore = ({ tab, positions }: { tab: string; positions: Map<string, number> }) => {
  useEffect(() => {
    const saved = positions.get(tab);
    const scroller = document.querySelector<HTMLElement>('.app-scroller');
    if (saved !== undefined && scroller) {
      scroller.scrollTop = saved;
    }
  }, [tab, positions]);
  return null;
};

const AppContent = () => {
  const { user, loading, error } = useUser();

  // Returning visitors within the same session skip the full intro — only a
  // brief fade so the app never hard-cuts between boots.
  const [introDone, setIntroDone] = useState(
    () => sessionStorage.getItem('aninexus_intro_seen') === '1',
  );

  const finishIntro = useCallback(() => {
    sessionStorage.setItem('aninexus_intro_seen', '1');
    setIntroDone(true);
  }, []);

  const getInitialRoute = useCallback((): RouteTarget => {
    const startParam = window.Telegram?.WebApp?.initDataUnsafe?.start_param;
    const candidates = [...getCandidates(), startParam];

    for (const candidate of candidates) {
      const route = resolveRouteToken(candidate);
      if (route) return route;
    }

    return legacyRoute() || { tab: 'profile', alias: 'profile' };
  }, []);

  const [activeRoute, setActiveRoute] = useState(getInitialRoute());
  const activeTab = activeRoute.tab;
  const publicTab = [
    'cards',
    'catalog_anime',
    'catalog_manga',
    'subscription',
    'terms',
    'contribute',
    'requests',
  ].includes(activeTab);
  const introStatus: IntroStatus =
    error && !publicTab ? 'error' : loading && !publicTab ? 'loading' : 'ready';
  const showIntro = !publicTab && (!introDone || introStatus === 'error');
  const routeKey = nativeRouteKey(activeTab);
  const routeKeyRef = useRef(routeKey);
  routeKeyRef.current = routeKey;
  const [nativeDialog, setNativeDialog] = useState(false);
  const [accountDeleted, setAccountDeleted] = useState(false);
  const [depth, setDepth] = useState(navigationDepth);

  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [selectedChar, setSelectedChar] = useState<any>(null);
  const [selectedPet, setSelectedPet] = useState<any>(null);
  const [revealedChar, setRevealedChar] = useState<any>(null);

  const backHandlerRef = useRef<(() => void) | null>(null);
  // Per-tab scroll positions so switching tabs restores where you were.
  const scrollPositions = useRef(new Map<string, number>());
  const activeRouteRef = useRef(activeRoute);
  activeRouteRef.current = activeRoute;

  useEffect(() => {
    const saveScroll = () => {
      const scroller = document.querySelector<HTMLElement>('.app-scroller');
      if (scroller) scrollPositions.current.set(routeKeyRef.current, scroller.scrollTop);
    };
    const onRoute = () => {
      saveScroll();
      setActiveRoute(getInitialRoute());
      setDepth(navigationDepth());
      setSelectedChar(null);
      setSelectedPet(null);
      setIsMenuOpen(false);
    };
    const onDialog = (event: Event) => setNativeDialog(Boolean((event as CustomEvent).detail));
    const onDeleted = () => setAccountDeleted(true);
    window.addEventListener('hashchange', onRoute);
    window.addEventListener('popstate', onRoute);
    window.addEventListener('source:navigate', onRoute);
    window.addEventListener('source:willnavigate', saveScroll);
    window.addEventListener('source:dialog', onDialog);
    window.addEventListener('source:account-deleted', onDeleted);
    return () => {
      window.removeEventListener('hashchange', onRoute);
      window.removeEventListener('popstate', onRoute);
      window.removeEventListener('source:navigate', onRoute);
      window.removeEventListener('source:willnavigate', saveScroll);
      window.removeEventListener('source:dialog', onDialog);
      window.removeEventListener('source:account-deleted', onDeleted);
    };
  }, [getInitialRoute]);

  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    if (!tg) return;
    if (accountDeleted) {
      tg.BackButton?.hide?.();
      return;
    }
    const hasDialog = Boolean(selectedChar || selectedPet || isMenuOpen || nativeDialog);
    const handleBack = () => {
      if (nativeDialog) window.dispatchEvent(new Event('source:back'));
      else if (selectedChar || selectedPet || isMenuOpen) {
        setSelectedChar(null);
        setSelectedPet(null);
        setIsMenuOpen(false);
      } else if (navigationDepth() > 0) window.history.back();
      else navigateNative('profile');
    };
    backHandlerRef.current = handleBack;
    if (hasDialog || depth > 0 || activeTab !== 'profile') {
      tg.BackButton?.show?.();
      tg.BackButton?.onClick?.(handleBack);
    } else tg.BackButton?.hide?.();
    if (hasDialog) tg.disableVerticalSwipes?.();
    else tg.enableVerticalSwipes?.();
    tg.expand?.();
    return () => {
      tg.BackButton?.offClick?.(handleBack);
    };
  }, [selectedChar, selectedPet, isMenuOpen, nativeDialog, depth, activeTab, accountDeleted]);

  // Harmonize the Telegram chrome (header bar + overscroll area) and the
  // native control scheme with the user's Telegram theme instead of forcing
  // a hardcoded dark palette. Re-applies when the user switches themes.
  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    if (!tg) return;

    tg.ready?.();

    const applyTheme = () => {
      const params = tg.themeParams || {};
      const bg = params.bg_color || params.secondary_bg_color || '#09090b';
      tg.setHeaderColor?.(bg);
      tg.setBackgroundColor?.(bg);
      document.documentElement.style.colorScheme = tg.colorScheme === 'light' ? 'light' : 'dark';
    };

    applyTheme();
    tg.onEvent?.('themeChanged', applyTheme);
    return () => {
      tg.offEvent?.('themeChanged', applyTheme);
    };
  }, []);

  const handleNavigate = useCallback((tab: string) => {
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    navigateNative(tab);
  }, []);

  if (accountDeleted) {
    return (
      <div
        data-source-shell
        className="flex-1 flex flex-col bg-zinc-950 p-6 justify-center items-center gap-5 text-center"
      >
        <h1 className="text-xl font-bold text-zinc-100">Conta excluída</h1>
        <p className="text-sm text-zinc-400">
          Seus dados foram removidos. Feche a MiniApp para encerrar esta sessão.
        </p>
        <button
          type="button"
          className="bg-white text-zinc-950 px-6 py-3 rounded-md text-xs font-bold"
          onClick={() => window.Telegram?.WebApp?.close?.()}
        >
          Fechar MiniApp
        </button>
      </div>
    );
  }

  if (showIntro) {
    return <IntroLoading status={introStatus} onFinish={finishIntro} />;
  }

  if (!publicTab && !accountDeleted && (error || (!loading && !user))) {
    return <ServerError onRetry={() => window.location.reload()} />;
  }

  const canViewUpload = Boolean(user?.can_upload ?? user?.is_sudo);
  const canViewStaff = Boolean(user?.is_sudo);
  const isBlockedTab =
    (activeTab === 'upload' && !canViewUpload) || (activeTab === 'staff' && !canViewStaff);

  return (
    <div data-source-shell className="flex-1 flex flex-col min-h-0 overflow-hidden bg-zinc-950">
      {!accountDeleted && (
        <div inert={nativeDialog || isMenuOpen}>
          <Header onMenuClick={() => setIsMenuOpen(true)} onNavigate={handleNavigate} />
        </div>
      )}

      <main
        className="app-scroller"
        inert={nativeDialog || isMenuOpen}
        style={nativeDialog || isMenuOpen ? { overflow: 'hidden' } : undefined}
      >
        <Suspense
          fallback={
            <div className="flex flex-col items-center justify-center h-full gap-4">
              <Loader2 size={24} className="animate-spin text-zinc-700" />
            </div>
          }
        >
          <div key={routeKey} className="page-transition-wrapper">
            <ScrollRestore tab={routeKey} positions={scrollPositions.current} />
            {activeTab === 'profile' && (
              <Profile
                onCharClick={setSelectedChar}
                focusCollection={
                  activeRoute.alias === 'harem' || activeRoute.alias === 'collection'
                }
              />
            )}
            {NATIVE_TABS.includes(activeTab) && <NativeScreens tab={activeTab} />}
            {activeTab === 'dado' && <Dado />}
            {activeTab === 'incubation' && <Hatchery />}
            {activeTab === 'shop' && <Shop onCharClick={setSelectedChar} />}
            {activeTab === 'exchange' && <Exchange />}
            {activeTab === 'gallery' && <Gallery onCharClick={setSelectedChar} />}
            {activeTab === 'pets' && <PetShop onPetClick={setSelectedPet} />}
            {activeTab === 'referrals' && <Referrals />}
            {activeTab === 'quests' && <Quests />}
            {activeTab === 'pass' && <Pass />}
            {activeTab === 'leaderboard' && <Leaderboard />}
            {activeTab === 'achievements' && <Achievements />}
            {activeTab === 'mypets' && <MyPets onPetClick={setSelectedPet} />}
            {activeTab === 'minigames' && <Minigames />}
            {activeTab === 'trading' && <Trading />}
            {activeTab === 'duels' && <Duels />}
            {activeTab === 'bonds' && <Bonds />}
            {activeTab === 'upload' && canViewUpload && <Upload />}
            {activeTab === 'staff' && canViewStaff && <Staff />}

            {isBlockedTab ? (
              <Forbidden onReset={() => handleNavigate('profile')} />
            ) : !VALID_TABS.includes(activeTab) ? (
              <NotFound onReset={() => handleNavigate('profile')} />
            ) : null}
          </div>
        </Suspense>
      </main>

      {selectedChar && (
        <CharActionModal
          selectedChar={selectedChar}
          setSelectedChar={setSelectedChar}
          activeTab={activeTab}
          user={user}
          onPurchaseSuccess={setRevealedChar}
        />
      )}
      {selectedPet && (
        <PetActionModal selectedPet={selectedPet} setSelectedPet={setSelectedPet} user={user} />
      )}
      {revealedChar && (
        <GachaReveal character={revealedChar} onClose={() => setRevealedChar(null)} />
      )}

      <NavigationDrawer
        isOpen={isMenuOpen}
        onClose={() => setIsMenuOpen(false)}
        activeTab={activeTab}
        onNavigate={handleNavigate}
      />
    </div>
  );
};

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5,
      gcTime: 1000 * 60 * 30,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

// Bridge invalidateQueries() events to the react-query cache.
// Replaces the old per-page window event listeners.
const QueryInvalidationBridge = () => {
  useEffect(() => {
    const onInvalidate = (event: Event) => {
      const endpoints = (event as CustomEvent<string[]>).detail || [];
      for (const endpoint of endpoints) {
        queryClient.invalidateQueries({ queryKey: ['api', endpoint] });
        queryClient.invalidateQueries({ queryKey: ['grid', endpoint] });
      }
    };
    window.addEventListener('query-invalidate', onInvalidate);
    return () => window.removeEventListener('query-invalidate', onInvalidate);
  }, []);
  return null;
};

function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <QueryInvalidationBridge />
        <ToastProvider>
          <UserProvider>
            <AppContent />
          </UserProvider>
        </ToastProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}

export default App;
