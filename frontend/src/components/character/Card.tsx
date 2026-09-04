import { CheckCircle2, Gem } from 'lucide-react';
import React, { forwardRef, memo } from 'react';
import { Character } from '../../context/UserContext';
import { cn, FALLBACK_IMAGE, formatNumber } from '../../utils';
import { Badge } from '../ui/Badge';

interface CardProps {
  character: Character;
  onClick?: (character: Character) => void;
}

export const Card = memo(
  forwardRef<HTMLButtonElement, CardProps>(({ character, onClick }, ref) => {
    const handleClick = () => {
      window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
      if (onClick) onClick(character);
    };

    const [imgError, setImgError] = React.useState(false);
    React.useEffect(() => {
      setImgError(false);
    }, []);

    const rarityLabel = character.rarity
      .replace(
        /[\u2700-\u27bf]|[\u2190-\u21ff]|[\u2000-\u206f]|[\u2600-\u26ff]|[\u2b00-\u2bff]|[\u00a0-\u00bf]|\u2013|\u2014/g,
        '',
      )
      .trim()
      .toUpperCase();
    const hasPrice = typeof character.zenith_price === 'number' && character.zenith_price > 0;
    const stockLimit = typeof character.stock_limit === 'number' ? character.stock_limit : null;
    const stockRemaining =
      typeof character.stock_remaining === 'number'
        ? character.stock_remaining
        : stockLimit !== null && typeof character.sold_count === 'number'
          ? Math.max(0, stockLimit - character.sold_count)
          : null;
    const hasStock = stockLimit !== null && stockRemaining !== null;
    const soldOut = character.sold_out || (hasStock && stockRemaining <= 0);
    const copyCount = Number(character.count || 0);
    const showPrice = hasPrice && !character.owned && !soldOut;
    const characterId = String(character.id || '');

    const getRarityVariant = (rarity: string) => {
      const r = rarity.toLowerCase();
      if (r.includes('common')) return 'secondary';
      if (r.includes('uncommon')) return 'success';
      if (r.includes('rare')) return 'rare';
      if (r.includes('epic')) return 'epic';
      if (r.includes('legendary') || r.includes('limited')) return 'premium';
      if (
        r.includes('mythical') ||
        r.includes('celestial') ||
        r.includes('divine') ||
        r.includes('astral') ||
        r.includes('prestige') ||
        r.includes('cinematic') ||
        r.includes('seraph')
      )
        return 'mythic';
      return 'primary';
    };

    const rarityVariant = getRarityVariant(rarityLabel);

    return (
      <button
        ref={ref}
        type="button"
        onClick={handleClick}
        className={cn(
          'relative rounded-md overflow-hidden aspect-[2/3] group cursor-pointer select-none',
          'bg-zinc-950 border border-white/5 transition-all duration-200 active:scale-[0.98]',
          'hover:border-white/10',
          soldOut && 'border-red-500/10',
        )}
      >
        {!imgError ? (
          <img
            src={character.img_url || FALLBACK_IMAGE}
            alt={character.name}
            loading="lazy"
            decoding="async"
            referrerPolicy="no-referrer"
            onError={() => setImgError(true)}
            className={cn(
              'absolute inset-0 w-full h-full object-cover transition-all duration-500',
              soldOut && 'grayscale opacity-40',
            )}
          />
        ) : (
          <img
            src={FALLBACK_IMAGE}
            alt={character.name}
            className={cn(
              'absolute inset-0 w-full h-full object-cover transition-all duration-500',
              soldOut && 'grayscale opacity-40',
            )}
          />
        )}

        <div className="absolute inset-0 bg-gradient-to-t from-black via-black/10 to-transparent opacity-80" />

        <div className="absolute left-2 top-2 z-20 flex flex-col gap-1.5">
          {characterId && (
            <div className="rounded bg-black/60 px-1.5 py-0.5 text-[9px] font-mono font-bold text-zinc-400 backdrop-blur-md border border-white/5">
              <span className="tabular-nums">#{characterId}</span>
            </div>
          )}
          {character.owned && (
            <div className="w-5 h-5 rounded bg-emerald-500 text-black flex items-center justify-center shadow-lg border border-emerald-500/20">
              <CheckCircle2 size={12} strokeWidth={3} />
            </div>
          )}
        </div>

        <div className="absolute bottom-0 inset-x-0 p-3 space-y-1.5 z-20">
          <div className="min-w-0">
            <h3 className="text-[11px] font-bold text-white line-clamp-1 uppercase tracking-tight">
              {character.name}
            </h3>
            <div className="flex items-center gap-2 mt-0.5">
              <Badge variant={rarityVariant} size="xs" className="opacity-90">
                {rarityLabel || 'STANDARD'}
              </Badge>
            </div>
          </div>

          <div className="flex items-center justify-between gap-2">
            {soldOut ? (
              <Badge variant="danger" size="xs" className="font-bold">
                DEPLETED
              </Badge>
            ) : character.owned && copyCount > 1 ? (
              <div className="text-[9px] font-mono font-bold text-emerald-500 uppercase">
                x{copyCount} Owned
              </div>
            ) : showPrice ? (
              <div className="flex items-center gap-1.5 rounded bg-brand-accent text-white px-2 py-0.5 text-[10px] font-mono font-bold tabular-nums shadow-sm">
                <Gem size={10} fill="currentColor" />
                {formatNumber(character.zenith_price)}
              </div>
            ) : (
              <div />
            )}
          </div>
        </div>
      </button>
    );
  }),
);