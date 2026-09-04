import { User } from 'lucide-react';
import { memo, useEffect, useState } from 'react';
import { cn } from '../utils';

interface AvatarProps {
  src?: string | null | undefined;
  alt?: string | undefined;
  className?: string | undefined;
  fallbackText?: string | undefined;
}

export const Avatar = memo(({ src, alt = 'Avatar', className = '', fallbackText }: AvatarProps) => {
  const [error, setError] = useState(false);
  const [loaded, setLoaded] = useState(false);

  // biome-ignore lint/correctness/useExhaustiveDependencies: reset load state when src changes
  useEffect(() => {
    setError(false);
    setLoaded(false);
  }, [src]);

  return (
    <div
      className={cn(
        'relative overflow-hidden bg-zinc-900 flex items-center justify-center shrink-0',
        className,
      )}
    >
      {!error && src ? (
        <>
          <img
            src={src}
            alt={alt}
            onLoad={() => setLoaded(true)}
            onError={() => setError(true)}
            className={cn(
              'w-full h-full object-cover transition-opacity duration-300',
              loaded ? 'opacity-100' : 'opacity-0',
            )}
          />
          {!loaded && <div className="absolute inset-0 bg-zinc-900 animate-pulse" />}
        </>
      ) : fallbackText ? (
        <span className="text-xs font-bold uppercase text-zinc-600">{fallbackText}</span>
      ) : (
        <User className="text-zinc-800 w-1/2 h-1/2" />
      )}
    </div>
  );
});
