import {
  ArrowLeftRight,
  BadgeCheck,
  BookOpen,
  ChartNoAxesColumnIncreasing,
  Dices,
  Egg,
  Gamepad2,
  Heart,
  LayoutDashboard,
  ListChecks,
  LogOut,
  PawPrint,
  Repeat2,
  Satellite,
  Store,
  Terminal,
  Ticket,
  UserPlus,
  Users,
  X,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { setSessionToken } from '../api/client';
import { useUser } from '../context/UserContext';
import { cn } from '../utils';
import { Button } from './ui/Button';

interface NavItem {
  id: string;
  label: string;
  icon: any;
}

interface NavSection {
  title: string;
  items: NavItem[];
}

interface NavigationDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  activeTab: string;
  onNavigate: (tabId: string) => void;
}

const SECTIONS: NavSection[] = [
  {
    title: 'PRINCIPAL',
    items: [
      { id: 'profile', label: 'Painel', icon: LayoutDashboard },
      { id: 'dado', label: 'Dado', icon: Dices },
      { id: 'incubation', label: 'Incubadora', icon: Egg },
      { id: 'shop', label: 'Loja', icon: Store },
      { id: 'exchange', label: 'Economia', icon: Repeat2 },
      { id: 'gallery', label: 'Coleção', icon: BookOpen },
    ],
  },
  {
    title: 'RECURSOS',
    items: [
      { id: 'mypets', label: 'Companheiros', icon: PawPrint },
      { id: 'minigames', label: 'Jogos AniNexus', icon: Gamepad2 },
      { id: 'achievements', label: 'Conquistas', icon: BadgeCheck },
    ],
  },
  {
    title: 'SOCIAL',
    items: [
      { id: 'trading', label: 'Trocas', icon: ArrowLeftRight },
      { id: 'referrals', label: 'Indicações', icon: UserPlus },
      { id: 'quests', label: 'Missões', icon: ListChecks },
      { id: 'pass', label: 'Temporada', icon: Ticket },
      { id: 'leaderboard', label: 'Ranking', icon: ChartNoAxesColumnIncreasing },
    ],
  },
];

const ADMIN_ITEMS: NavItem[] = [
  { id: 'upload', label: 'Cadastro', icon: Satellite },
  { id: 'staff', label: 'Equipe', icon: Users },
];

export const NavigationDrawer = ({
  isOpen,
  onClose,
  activeTab,
  onNavigate,
}: NavigationDrawerProps) => {
  const { user } = useUser();
  const panelRef = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setMounted(true);
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      // Trap Tab focus inside the open drawer.
      if (e.key === 'Tab' && panelRef.current) {
        const focusables = panelRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        );
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (!first || !last) return;
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener('keydown', onKey);
    panelRef.current?.focus();
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (!mounted || isOpen) return;
    const t = setTimeout(() => setMounted(false), 250);
    return () => clearTimeout(t);
  }, [mounted, isOpen]);

  const handleItemClick = (id: string) => {
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    onNavigate(id);
    onClose();
  };

  const canUpload = Boolean(user?.can_upload ?? user?.is_sudo);
  const canStaff = Boolean(user?.is_sudo);
  const sections: NavSection[] = [
    ...SECTIONS,
    ...(canUpload || canStaff
      ? [
          {
            title: 'ADMINISTRAÇÃO',
            items: ADMIN_ITEMS.filter((item) =>
              item.id === 'upload' ? canUpload : canStaff,
            ),
          },
        ]
      : []),
  ];

  const [confirmLogout, setConfirmLogout] = useState(false);

  const doLogout = () => {
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    onClose();
    setSessionToken(null);
    window.location.reload();
  };

  const handleLogout = () => {
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    const native = window.Telegram?.WebApp?.showConfirm;
    if (native) {
      native('Log out and clear this session?', (confirmed) => {
        if (confirmed) doLogout();
      });
      return;
    }
    setConfirmLogout(true);
  };

  if (!mounted) return null;

  return (
    <>
      <button
        type="button"
        aria-label="Close navigation drawer"
        onClick={onClose}
        className={cn(
          'fixed inset-0 z-[110] bg-black/60 transition-opacity duration-200',
          isOpen ? 'opacity-100' : 'opacity-0',
        )}
      />

      <div
        className={cn(
          'fixed top-0 right-0 z-[120] h-full w-[min(280px,85vw)] bg-zinc-950 border-l border-white/5 flex flex-col shadow-2xl transition-transform duration-200 ease-out',
          isOpen ? 'translate-x-0' : 'translate-x-full',
        )}
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Navigation"
        tabIndex={-1}
      >
            {/* Header */}
            <div className="p-6 flex items-center justify-between border-b border-white/[0.04]">
              <div className="flex flex-col">
                <div className="flex items-center gap-2">
                  <Terminal size={14} className="text-zinc-500" />
                  <span className="text-[11px] font-bold text-zinc-100 tracking-wider uppercase">
                    SYSTEM
                  </span>
                </div>
                <span className="text-[8px] font-mono text-zinc-500 uppercase mt-0.5">V2.4</span>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={onClose}
                className="w-8 h-8 p-0 rounded-md border border-white/5 bg-zinc-900"
                aria-label="Close"
              >
                <X size={16} />
              </Button>
            </div>

            {/* Scrollable Content */}
            <div className="flex-1 overflow-y-auto px-4 py-6 space-y-8">
              {sections.map((section) => (
                <div key={section.title} className="space-y-3">
                  <h3 className="px-2 text-[9px] font-bold text-zinc-500 uppercase tracking-widest">
                    {section.title}
                  </h3>
                  <div className="space-y-1">
                    {section.items.map((item) => {
                      const Icon = item.icon;
                      const isActive = activeTab === item.id;

                      return (
                        <button
                          key={item.id}
                          onClick={() => handleItemClick(item.id)}
                          className={cn(
                            'group w-full flex items-center justify-between px-3 py-2.5 rounded-md transition-all duration-200 relative',
                            isActive
                              ? 'bg-brand-accent/10 text-brand-accent'
                              : 'text-zinc-500 hover:text-zinc-200 hover:bg-white/5',
                          )}
                        >
                          <div className="flex items-center gap-3">
                            <Icon
                              size={16}
                              className={
                                isActive
                                  ? 'text-brand-accent'
                                  : 'text-zinc-500 transition-colors group-hover:text-zinc-300'
                              }
                            />
                            <span
                              className={cn(
                                'text-[11px] font-bold uppercase tracking-wider',
                                isActive
                                  ? 'text-brand-accent'
                                  : 'text-zinc-500 transition-colors group-hover:text-zinc-300',
                              )}
                            >
                              {item.label}
                            </span>
                          </div>

                          {isActive && <div className="w-1 h-1 rounded-full bg-brand-accent" />}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}

              {/* Account */}
              <div className="space-y-3 pt-4">
                <h3 className="px-2 text-[9px] font-bold text-zinc-600 uppercase tracking-widest">
                  CONTA
                </h3>
                <button
                  onClick={handleLogout}
                  className="w-full flex items-center gap-3 px-3 py-2.5 text-red-500 hover:text-red-400 hover:bg-red-500/5 transition-colors rounded-md"
                >
                  <LogOut size={16} />
                  <span className="text-[11px] font-bold uppercase tracking-wider">Sair</span>
                </button>

                {confirmLogout && (
                  <div className="mt-2 p-3 rounded-md bg-red-500/5 border border-red-500/20 space-y-2">
                    <p className="text-[10px] font-bold text-red-400 uppercase tracking-widest">
                      Log out and clear this session?
                    </p>
                    <div className="flex gap-2">
                      <Button
                        variant="accent"
                        size="sm"
                        onClick={doLogout}
                        className="flex-1 h-8 text-[10px]"
                      >
                        Confirm
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setConfirmLogout(false)}
                        className="flex-1 h-8 text-[10px]"
                      >
                        Cancel
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Footer */}
            <div className="p-6 border-t border-white/[0.04] bg-white/[0.01]">
              <div className="flex items-center gap-3 p-3 rounded-md bg-zinc-900 border border-white/5 mb-5">
                <div className="w-8 h-8 rounded bg-brand-accent/10 flex items-center justify-center shrink-0 border border-brand-accent/20">
                  <Heart size={14} className="text-brand-accent" fill="currentColor" />
                </div>
                <div className="flex flex-col min-w-0">
                  <span className="text-[10px] font-bold text-zinc-100 uppercase tracking-wider truncate">
                    {user?.role_label || user?.role_tag || 'OPERATOR'}
                  </span>
                  <span className="text-[8px] font-bold text-zinc-500 uppercase tracking-widest">
                    Conectado
                  </span>
                </div>
              </div>

              <div className="flex items-center justify-between px-1">
                <div className="text-[8px] font-bold text-zinc-500 uppercase tracking-widest">
                  Status do servidor
                </div>
                <div className="flex items-center gap-1.5">
                  <div className="w-1 h-1 rounded-full bg-emerald-500" />
                  <span className="text-[8px] font-mono text-emerald-500/80 uppercase">ONLINE</span>
                </div>
              </div>

              {/* Legal links — Telegram requires terms + privacy for Mini Apps */}
              <div className="flex items-center justify-center gap-3 mt-3">
                <a
                  href={`https://t.me/${import.meta.env.VITE_BOT_USERNAME || 'SourceBaltigo_Bot'}?start=terms`}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest hover:text-zinc-400 transition-colors"
                >
                  Terms
                </a>
                <span className="text-zinc-800">·</span>
                <a
                  href={`https://t.me/${import.meta.env.VITE_BOT_USERNAME || 'SourceBaltigo_Bot'}?start=privacy`}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest hover:text-zinc-400 transition-colors"
                >
                  Privacy
                </a>
                <span className="text-zinc-800">·</span>
                <a
                  href={`https://t.me/${import.meta.env.VITE_BOT_USERNAME || 'SourceBaltigo_Bot'}?start=dmca`}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest hover:text-zinc-400 transition-colors"
                >
                  DMCA
                </a>
              </div>
            </div>
          </div>
    </>
  );
};
