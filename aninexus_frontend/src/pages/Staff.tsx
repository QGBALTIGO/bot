import { AnimatePresence, m } from 'framer-motion';
import {
  ChevronDown,
  Coins,
  Gem,
  History,
  Image as ImageIcon,
  PawPrint,
  Sparkles,
  Terminal,
  Users,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import { Avatar } from '../components/Avatar';
import { RarityEditor } from '../components/admin/RarityEditor';
import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { ErrorState } from '../components/ui/ErrorState';
import { Skeleton } from '../components/ui/Skeleton';
import { useUser } from '../context/UserContext';
import { useApi } from '../hooks/useApi';
import { cn, formatNumber } from '../utils';

interface UploadReward {
  balance?: number;
  zenith?: number;
}

interface StaffUploadItem {
  type: 'character' | 'pet';
  id?: string | null;
  name: string;
  subtitle?: string | null;
  rarity?: string | null;
  image?: string | null;
  uploaded_at?: string | null;
  enabled?: boolean;
}

interface StaffMember {
  id: number;
  display_name: string;
  username?: string | null;
  avatar?: string | null;
  role_label: string;
  role_tag: string;
  role_symbol: string;
  upload_reward?: UploadReward | null;
  role_benefits?: string[];
  stats: {
    balance: number;
    zenith: number;
    level: number;
    xp: number;
  };
  contributions: {
    total_uploads: number;
    character_uploads: number;
    pet_uploads: number;
    sources: Record<string, number>;
  };
  uploads: {
    characters: StaffUploadItem[];
    pets: StaffUploadItem[];
    limit?: number;
    truncated?: boolean;
  };
}

interface StaffContributionsResponse {
  summary: {
    total_staff: number;
    total_uploads: number;
    character_uploads: number;
    pet_uploads: number;
  };
  staff: StaffMember[];
}

const getInitials = (name: string) => {
  const parts = name.replace(/^@/, '').split(/\s+/).filter(Boolean);
  return (
    parts
      .slice(0, 2)
      .map((part) => part[0])
      .join('') || 'U'
  ).toUpperCase();
};

const formatDate = (value?: string | null) => {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }).toUpperCase();
};

const allUploadsFor = (member: StaffMember) =>
  [...member.uploads.characters, ...member.uploads.pets].sort((a, b) => {
    const aTime = a.uploaded_at ? new Date(a.uploaded_at).getTime() : 0;
    const bTime = b.uploaded_at ? new Date(b.uploaded_at).getTime() : 0;
    return bTime - aTime;
  });

const StaffDetails = ({ member }: { member: StaffMember }) => {
  const uploads = allUploadsFor(member);

  return (
    <m.div
      initial={{ height: 0, opacity: 0 }}
      animate={{ height: 'auto', opacity: 1 }}
      className="mt-4 pt-4 border-t border-white/5 space-y-6 overflow-hidden"
    >
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {[
          {
            icon: ImageIcon,
            label: 'Characters',
            value: formatNumber(member.contributions.character_uploads),
          },
          { icon: PawPrint, label: 'Pets', value: formatNumber(member.contributions.pet_uploads) },
          { icon: Gem, label: 'Prisms', value: formatNumber(member.stats.zenith) },
          { icon: Coins, label: 'Coins', value: formatNumber(member.stats.balance) },
        ].map((stat, i) => (
          <div key={i} className="bg-zinc-950 p-2.5 rounded border border-white/5">
            <p className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest mb-1">
              {stat.label}
            </p>
            <p className="text-[11px] font-mono font-bold text-zinc-100 leading-none">
              {stat.value}
            </p>
          </div>
        ))}
      </div>

      <div className="space-y-2.5">
        <div className="flex items-center gap-2 px-1">
          <History size={12} className="text-zinc-600" />
          <span className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest">
            Recent Activity
          </span>
        </div>
        {uploads.length > 0 ? (
          <div className="divide-y divide-white/5 bg-zinc-950 border border-white/5 rounded-md overflow-hidden">
            {uploads.map((item) => (
              <div
                key={`${item.type}:${item.id}:${item.name}`}
                className="flex items-center gap-3 p-2.5 hover:bg-white/[0.02] transition-colors"
              >
                <div className="h-9 w-9 shrink-0 overflow-hidden rounded bg-zinc-900 border border-white/10">
                  {item.image ? (
                    <img
                      src={item.image}
                      alt={item.name}
                      loading="lazy"
                      referrerPolicy="no-referrer"
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center text-zinc-800">
                      {item.type === 'pet' ? <PawPrint size={16} /> : <ImageIcon size={16} />}
                    </div>
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="truncate text-[11px] font-bold text-zinc-100 uppercase tracking-tight">
                      {item.name}
                    </p>
                    <Badge variant="secondary" size="xs" className="px-1 py-0 opacity-60">
                      {item.type === 'pet' ? 'PET' : 'CHARACTER'}
                    </Badge>
                  </div>
                  <p className="truncate text-[9px] font-medium text-zinc-600 uppercase tracking-widest mt-0.5">
                    {[item.subtitle, item.rarity, item.id ? `ID_${item.id}` : '']
                      .filter(Boolean)
                      .join(' • ')}
                  </p>
                </div>
                <div className="shrink-0 text-right pr-1">
                  <p className="text-[8px] font-mono font-bold text-zinc-500">
                    {formatDate(item.uploaded_at)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="py-6 text-center bg-zinc-950 border border-dashed border-white/5 rounded-md">
            <p className="text-[9px] font-bold text-zinc-700 uppercase tracking-widest">
              No contribution records
            </p>
          </div>
        )}
      </div>
    </m.div>
  );
};

export const Staff = () => {
  const { user } = useUser();
  const { data, loading, error, execute } = useApi<StaffContributionsResponse>(
    '/admin/sudos/contributions',
  );
  const [openStaffId, setOpenStaffId] = useState<number | null>(null);
  const isSudo = Boolean(user?.is_sudo);

  const rankedStaff = useMemo(() => {
    return [...(data?.staff || [])].sort((a, b) => {
      const totalDiff = b.contributions.total_uploads - a.contributions.total_uploads;
      return totalDiff || a.display_name.localeCompare(b.display_name);
    });
  }, [data]);

  return (
    <div className="pt-6 max-w-4xl mx-auto adaptive-px space-y-8">
      <header className="space-y-1">
        <div className="flex items-center gap-2.5">
          <Users className="text-brand-accent" size={20} />
          <h1 className="text-xl font-bold text-zinc-100 uppercase tracking-tight">
            Staff Panel
          </h1>
        </div>
        <div className="flex items-center gap-2 opacity-60">
          <Terminal size={10} className="text-zinc-500" />
          <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
            Who built the game you're playing
          </p>
        </div>
      </header>

      {isSudo && (
        <div className="space-y-4">
          <div className="flex items-center gap-2.5">
            <Sparkles className="text-brand-accent" size={16} />
            <h2 className="text-[12px] font-bold text-zinc-100 uppercase tracking-tight">
              Admin Tools
            </h2>
          </div>
          <RarityEditor />
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'Staff', value: data?.summary.total_staff || 0, variant: 'primary' },
          { label: 'Uploads', value: data?.summary.total_uploads || 0, variant: 'default' },
          { label: 'Characters', value: data?.summary.character_uploads || 0, variant: 'success' },
          { label: 'Pets', value: data?.summary.pet_uploads || 0, variant: 'warning' },
        ].map((item, i) => (
          <Card key={i} variant="default" className="p-3.5">
            <span className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest block mb-1.5">
              {item.label}
            </span>
            <p className="text-sm font-mono font-bold text-zinc-100 tabular-nums">
              {formatNumber(item.value)}
            </p>
          </Card>
        ))}
      </div>

      <div className="space-y-4">
        <h2 className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest px-1">
          The team
        </h2>

        <AnimatePresence mode="wait">
          {error && !data ? (
            <div className="py-12">
              <ErrorState message={error} onAction={() => execute()} />
            </div>
          ) : loading ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, index) => (
                <Skeleton key={index} className="h-16 w-full rounded-md" />
              ))}
            </div>
          ) : rankedStaff.length > 0 ? (
            <div className="space-y-2">
              {rankedStaff.map((member) => {
                const isOpen = openStaffId === member.id;

                return (
                  <Card
                    key={member.id}
                    variant="default"
                    className={cn('p-3.5 transition-all', isOpen && 'border-brand-accent/30')}
                  >
                    <button
                      type="button"
                      onClick={() => {
                        window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
                        setOpenStaffId(isOpen ? null : member.id);
                      }}
                      className="flex w-full items-center gap-4 text-left"
                    >
                      <Avatar
                        src={member.avatar}
                        alt={member.display_name}
                        fallbackText={getInitials(member.display_name)}
                        className="h-11 w-11 rounded-md border border-white/10 bg-zinc-900"
                      />
                      <div className="min-w-0 flex-1 space-y-0.5">
                        <div className="flex items-center gap-2">
                          <h2 className="truncate text-[13px] font-bold text-zinc-100 uppercase tracking-tight">
                            {member.display_name}
                          </h2>
                          <Badge variant="primary" size="xs">
                            {member.role_tag}
                          </Badge>
                        </div>
                        <p className="truncate text-[9px] font-bold text-zinc-600 uppercase tracking-widest">
                          {[member.username ? `@${member.username}` : '', `ID_${member.id}`]
                            .filter(Boolean)
                            .join(' • ')}
                        </p>
                      </div>
                      <div className="shrink-0 text-right pr-2 hidden xs:block">
                        <p className="text-lg font-mono font-bold text-zinc-100 leading-none">
                          {formatNumber(member.contributions.total_uploads)}
                        </p>
                        <p className="text-[7px] font-bold uppercase tracking-widest text-zinc-700">
                          UPLOADS
                        </p>
                      </div>
                      <div className="shrink-0">
                        <ChevronDown
                          size={16}
                          className={cn(
                            'text-zinc-600 transition-transform',
                            isOpen && 'rotate-180 text-brand-accent',
                          )}
                        />
                      </div>
                    </button>

                    <AnimatePresence>{isOpen && <StaffDetails member={member} />}</AnimatePresence>
                  </Card>
                );
              })}
            </div>
          ) : null}
        </AnimatePresence>
      </div>
    </div>
  );
};
