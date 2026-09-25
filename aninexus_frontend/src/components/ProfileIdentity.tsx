import { Crown, Pencil, Ticket } from 'lucide-react';
import type { User } from '../context/UserContext';
import { navigateNative } from '../native/navigation';
import { Avatar } from './Avatar';
import { Badge } from './ui/Badge';
import { Card } from './ui/Card';
import { ProgressBar } from './ui/ProgressBar';

/** One profile identity, derived from the existing shared favorite. No extra requests. */
export function ProfileIdentity({ user }: { user: User }) {
  const favorite = user.favorite;
  const accountName =
    user.nickname || [user.first_name, user.last_name].filter(Boolean).join(' ') || 'Usuário';
  const displayName = favorite ? favorite.name?.trim() || 'Personagem favorito' : accountName;
  const username = user.username ? `@${user.username}` : `ID ${user.id}`;
  const stats = user.stats;
  const passType = stats?.pass_type || 'free';
  const passLabel =
    passType === 'free' ? 'PASSE GRÁTIS' : passType === 'premium' ? 'PASSE PREMIUM' : 'PASSE ELITE';
  const editLabel = favorite ? 'Alterar personagem favorito' : 'Escolher personagem favorito';

  return (
    <Card
      variant="surface"
      data-profile-identity
      data-profile-favorite={favorite ? '' : undefined}
      className="md:col-span-2 min-w-0 grid grid-cols-[80px_minmax(0,1fr)] xs:grid-cols-[96px_minmax(0,1fr)] sm:grid-cols-[112px_minmax(0,1fr)] items-start gap-4 sm:gap-x-6 p-4 sm:p-6"
    >
      <button
        type="button"
        data-profile-avatar
        aria-label={editLabel}
        title={editLabel}
        onClick={() => navigateNative('settings', { section: 'favorite' })}
        className="group relative col-start-1 row-start-1 sm:row-span-2 min-w-0 w-full rounded-lg text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-900"
      >
        <Avatar
          src={favorite ? favorite.image || null : user.avatar}
          alt={displayName}
          fallbackText={displayName.slice(0, 2)}
          className={`w-full rounded-lg border border-white/10 shadow-lg ${favorite ? 'aspect-[2/3]' : 'aspect-square'}`}
        />
        <span className="absolute top-1.5 right-1.5 grid w-6 h-6 place-items-center rounded-md border border-white/10 bg-zinc-950/80 text-zinc-300 group-hover:text-white" aria-hidden="true">
          <Pencil size={12} />
        </span>
        <span className="absolute -bottom-1.5 -right-1.5 pointer-events-none">
          <Badge variant="secondary" size="xs" className="bg-zinc-950 border-white/10 shadow-lg px-2 py-1">
            LVL {stats?.level || 1}
          </Badge>
        </span>
      </button>

      <div className="col-start-2 row-start-1 min-w-0 space-y-3 text-left">
        <div className="min-w-0 space-y-1.5">
          <h1 className="text-xl sm:text-2xl font-bold leading-tight text-zinc-100 tracking-tight [overflow-wrap:anywhere]">
            {displayName}
          </h1>
          {favorite?.anime && (
            <p data-profile-work className="text-[11px] sm:text-xs text-zinc-400 uppercase tracking-wide [overflow-wrap:anywhere]">
              {favorite.anime}
            </p>
          )}
          <p data-profile-username className="text-[10px] font-mono font-medium text-zinc-500 tracking-wider [overflow-wrap:anywhere]">
            {username}
          </p>
        </div>

        <div data-profile-badges className="flex flex-wrap items-center gap-2 min-w-0 [&>span]:max-w-full [&>span]:whitespace-normal [&>span]:[overflow-wrap:anywhere]">
          {user.role_tag && <Badge variant="primary" size="xs">{user.role_tag}</Badge>}
          <Badge variant="epic" size="xs" icon={Crown}>
            {user.titles?.current || 'USUÁRIO'}
          </Badge>
          <Badge variant="secondary" size="xs" icon={Ticket}>
            {passLabel}
          </Badge>
        </div>
      </div>

      <div data-profile-experience className="col-span-2 sm:col-span-1 sm:col-start-2 min-w-0 w-full pt-2 self-end">
        <ProgressBar
          current={stats?.xp_current || 0}
          total={Math.max(1, stats?.xp_needed || 1000)}
          label="EXPERIÊNCIA"
          compact
        />
      </div>
    </Card>
  );
}
