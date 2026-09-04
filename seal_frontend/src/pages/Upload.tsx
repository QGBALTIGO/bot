import { AnimatePresence, m } from 'framer-motion';
import {
  ChevronRight,
  FileImage,
  Image as ImageIcon,
  Link as LinkIcon,
  PawPrint,
  Terminal,
  UploadCloud,
} from 'lucide-react';
import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from 'react';
import { apiFetch, getErrorMessage } from '../api/client';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { useToast } from '../components/ui/Toast';
import { useUser } from '../context/UserContext';
import { cn } from '../utils';

type UploadMode = 'character' | 'pet';
type MediaSource = 'file' | 'url';

interface UploadOptions {
  max_size_mb: number;
  character_rarities: Array<{ value: number; label: string }>;
  pet_defaults: {
    rarity: string;
    hp: number;
    atk: number;
    spd: number;
    luck: number;
    ability: string;
    zenith_price: number;
    req_level: number;
    sort_order: number;
    enabled: boolean;
  };
}

const initialCharacter = {
  name: '',
  anime: '',
  rarity: '1',
};

const initialPet = {
  name: '',
  petid: '',
  rarity: 'Common',
  hp: '100',
  atk: '20',
  spd: '20',
  luck: '0.08',
  ability: 'None',
  desc: '',
  zenith_price: '0',
  req_level: '0',
  sort_order: '100',
  enabled: true,
};

const numberFrom = (value: string, fallback: number) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const isVideoSrc = (src: string) => /\.(mp4|webm)(\?|#|$)/i.test(src);

export const Upload = () => {
  const { addToast } = useToast();
  const { refreshUser } = useUser();
  const [mode, setMode] = useState<UploadMode>('character');
  const [source, setSource] = useState<MediaSource>('file');
  const [options, setOptions] = useState<UploadOptions | null>(null);
  const [character, setCharacter] = useState(initialCharacter);
  const [pet, setPet] = useState(initialPet);
  const [mediaUrl, setMediaUrl] = useState('');
  const [mediaData, setMediaData] = useState<string | null>(null);
  const [filename, setFilename] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [rightsConfirmed, setRightsConfirmed] = useState(false);

  useEffect(() => {
    apiFetch('/admin/upload/options')
      .then((data: UploadOptions) => {
        setOptions(data);
        setPet((prev) => ({
          ...prev,
          rarity: data.pet_defaults.rarity,
          hp: String(data.pet_defaults.hp),
          atk: String(data.pet_defaults.atk),
          spd: String(data.pet_defaults.spd),
          luck: String(data.pet_defaults.luck),
          ability: data.pet_defaults.ability,
          zenith_price: String(data.pet_defaults.zenith_price),
          req_level: String(data.pet_defaults.req_level),
          sort_order: String(data.pet_defaults.sort_order),
          enabled: data.pet_defaults.enabled,
        }));
      })
      .catch((err) => console.warn(err));
  }, []);

  const previewSrc = useMemo(() => {
    if (source === 'file') return mediaData || '';
    const url = mediaUrl.trim();
    // Block dangerous schemes (data:, javascript:, vbscript:) from reaching
    // img/video src — they are reinterpreted as HTML (XSS via DOM). Only
    // http(s) or relative URLs are safe to render here.
    if (url && /^[a-z][a-z0-9+.-]*:/i.test(url) && !/^https?:/i.test(url)) return '';
    return url;
  }, [mediaData, mediaUrl, source]);

  const clearMedia = () => {
    setMediaData(null);
    setFilename(null);
    setMediaUrl('');
  };

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const maxBytes = (options?.max_size_mb || 10) * 1024 * 1024;
    if (file.size > maxBytes) {
      addToast(`File too large (Max ${options?.max_size_mb || 10}MB)`, 'error');
      event.target.value = '';
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      setMediaData(String(reader.result || ''));
      setFilename(file.name);
    };
    reader.readAsDataURL(file);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting) return;

    setSubmitting(true);
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();

    try {
      const mediaPayload =
        source === 'url' ? { media_url: mediaUrl.trim() } : { media_data: mediaData, filename };

      if (source === 'url' && !mediaUrl.trim()) throw new Error('Enter a media URL');
      if (source === 'file' && !mediaData) throw new Error('Choose a file');

      const endpoint = mode === 'character' ? '/admin/upload/character' : '/admin/upload/pet';
      const payload =
        mode === 'character'
          ? {
              ...mediaPayload,
              name: character.name.trim(),
              anime: character.anime.trim(),
              rarity: Number(character.rarity),
              rights_confirmed: rightsConfirmed,
            }
          : {
              ...mediaPayload,
              name: pet.name.trim(),
              petid: pet.petid.trim() || null,
              rarity: pet.rarity.trim() || 'Common',
              hp: numberFrom(pet.hp, 100),
              atk: numberFrom(pet.atk, 20),
              spd: numberFrom(pet.spd, 20),
              luck: pet.luck.trim(),
              ability: pet.ability.trim() || 'None',
              desc: pet.desc.trim(),
              zenith_price: numberFrom(pet.zenith_price, 0),
              req_level: numberFrom(pet.req_level, 0),
              sort_order: numberFrom(pet.sort_order, 100),
              enabled: pet.enabled,
            };

      await apiFetch(endpoint, {
        method: 'POST',
        body: JSON.stringify(payload),
        timeoutMs: 90000,
      });

      addToast('Upload successful.', 'success');
      refreshUser().catch(() => undefined);
      clearMedia();
      if (mode === 'character') {
        setCharacter(initialCharacter);
      } else {
        setPet((prev) => ({ ...initialPet, rarity: prev.rarity }));
      }
    } catch (err) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="pt-6 max-w-3xl mx-auto adaptive-px space-y-8 select-none">
      <header className="space-y-1">
        <div className="flex items-center gap-2.5">
          <UploadCloud className="text-brand-accent" size={20} />
          <h1 className="text-xl font-bold text-zinc-100 uppercase tracking-tight">Upload</h1>
        </div>
        <div className="flex items-center gap-2 opacity-60">
          <Terminal size={10} className="text-zinc-500" />
          <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
            Add new characters and pets to the game
          </p>
        </div>
      </header>

      <div className="p-1 bg-zinc-900 border border-white/5 rounded-md flex gap-1">
        {[
          { id: 'character' as const, label: 'Character', icon: ImageIcon },
          { id: 'pet' as const, label: 'Companion', icon: PawPrint },
        ].map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => {
              window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
              setMode(item.id);
            }}
            className={cn(
              'flex-1 h-9 rounded text-[10px] font-bold uppercase tracking-widest flex items-center justify-center gap-2 transition-all',
              mode === item.id ? 'bg-zinc-100 text-zinc-950' : 'text-zinc-500 hover:text-zinc-300',
            )}
          >
            <item.icon size={14} />
            {item.label}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <section className="space-y-4">
          <h2 className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest px-1">
            Image
          </h2>
          <Card variant="surface" className="p-5 space-y-5">
            <div className="grid grid-cols-2 gap-1 p-1 bg-zinc-950 rounded-md border border-white/5">
              {[
                { id: 'file' as const, label: 'File', icon: FileImage },
                { id: 'url' as const, label: 'URL', icon: LinkIcon },
              ].map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
                    setSource(item.id);
                    clearMedia();
                  }}
                  className={cn(
                    'h-8 rounded text-[9px] font-bold uppercase tracking-widest flex items-center justify-center gap-2 transition-all',
                    source === item.id
                      ? 'bg-zinc-800 text-zinc-100'
                      : 'text-zinc-600 hover:text-zinc-400',
                  )}
                >
                  <item.icon size={12} />
                  {item.label}
                </button>
              ))}
            </div>

            {source === 'file' ? (
              <div className="relative">
                <input
                  type="file"
                  accept="image/*,video/mp4,video/webm"
                  onChange={handleFileChange}
                  className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
                />
                <div className="h-24 rounded-md border border-dashed border-white/10 bg-zinc-950 flex flex-col items-center justify-center gap-2 hover:border-brand-accent/20 transition-colors">
                  <UploadCloud size={20} className="text-zinc-600" />
                  <p className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest">
                    {filename || 'Select file (Max 10MB)'}
                  </p>
                </div>
              </div>
            ) : (
              <Input
                icon={LinkIcon}
                value={mediaUrl}
                onChange={(event) => setMediaUrl(event.target.value)}
                placeholder="Remote URL..."
                className="h-10"
              />
            )}

            <AnimatePresence>
              {previewSrc && (
                <m.div
                  initial={{ opacity: 0, scale: 0.98 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="rounded-md overflow-hidden border border-white/5 bg-zinc-950"
                >
                  {isVideoSrc(previewSrc) ? (
                    // codeql[js/xss-through-dom] previewSrc is scheme-gated to http(s) or a same-user file blob
                    <video src={previewSrc} controls className="w-full max-h-64 object-contain" />
                  ) : (
                    // codeql[js/xss-through-dom] previewSrc is scheme-gated to http(s) or a same-user file blob
                    <img
                      src={previewSrc}
                      alt="Preview"
                      className="w-full max-h-64 object-contain"
                    />
                  )}
                </m.div>
              )}
            </AnimatePresence>
          </Card>
        </section>

        <section className="space-y-4">
          <h2 className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest px-1">
            Character details
          </h2>
          <Card variant="surface" className="p-5 space-y-6">
            {mode === 'character' ? (
              <div className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <span className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest pl-1">
                      Name
                    </span>
                    <Input
                      value={character.name}
                      onChange={(event) =>
                        setCharacter((prev) => ({ ...prev, name: event.target.value }))
                      }
                      required
                      placeholder="Character name..."
                    />
                  </div>
                  <div className="space-y-1.5">
                    <span className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest pl-1">
                      Source
                    </span>
                    <Input
                      value={character.anime}
                      onChange={(event) =>
                        setCharacter((prev) => ({ ...prev, anime: event.target.value }))
                      }
                      required
                      placeholder="Origin source..."
                    />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <span className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest pl-1">
                    Rarity
                  </span>
                  <div className="relative group">
                    <select
                      aria-label="Rarity class"
                      value={character.rarity}
                      onChange={(event) =>
                        setCharacter((prev) => ({ ...prev, rarity: event.target.value }))
                      }
                      className="w-full h-10 bg-zinc-950 border border-white/10 rounded-md px-3.5 text-[11px] font-bold text-zinc-100 uppercase tracking-widest outline-none focus:border-brand-accent appearance-none cursor-pointer"
                    >
                      {(options?.character_rarities || []).map((rarity) => (
                        <option key={rarity.value} value={rarity.value}>
                          Class {rarity.value}: {rarity.label.toUpperCase()}
                        </option>
                      ))}
                    </select>
                    <ChevronRight
                      size={14}
                      className="absolute right-3.5 top-1/2 -translate-y-1/2 text-zinc-600 pointer-events-none"
                    />
                  </div>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <span className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest pl-1">
                      Name
                    </span>
                    <Input
                      value={pet.name}
                      onChange={(event) =>
                        setPet((prev) => ({ ...prev, name: event.target.value }))
                      }
                      required
                      placeholder="Pet name..."
                    />
                  </div>
                  <div className="space-y-1.5">
                    <span className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest pl-1">
                      ID
                    </span>
                    <Input
                      value={pet.petid}
                      onChange={(event) =>
                        setPet((prev) => ({ ...prev, petid: event.target.value }))
                      }
                      placeholder="Optional ID..."
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {[
                    { key: 'hp', label: 'HP' },
                    { key: 'atk', label: 'ATK' },
                    { key: 'spd', label: 'SPD' },
                    { key: 'luck', label: 'LUCK' },
                  ].map((stat) => (
                    <div key={stat.key} className="space-y-1.5">
                      <span className="text-[9px] font-bold text-zinc-700 uppercase tracking-widest pl-1">
                        {stat.label}
                      </span>
                      <Input
                        value={pet[stat.key as keyof typeof pet] as string}
                        onChange={(event) =>
                          setPet((prev) => ({ ...prev, [stat.key]: event.target.value }))
                        }
                        inputMode="decimal"
                        className="font-mono text-center h-10 px-2"
                      />
                    </div>
                  ))}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <span className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest pl-1">
                      Class
                    </span>
                    <Input
                      value={pet.rarity}
                      onChange={(event) =>
                        setPet((prev) => ({ ...prev, rarity: event.target.value }))
                      }
                      placeholder="Rarity..."
                    />
                  </div>
                  <div className="space-y-1.5">
                    <span className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest pl-1">
                      Ability
                    </span>
                    <Input
                      value={pet.ability}
                      onChange={(event) =>
                        setPet((prev) => ({ ...prev, ability: event.target.value }))
                      }
                      placeholder="Special perk..."
                    />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <span className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest pl-1">
                    Description
                  </span>
                  <textarea
                    value={pet.desc}
                    onChange={(event) => setPet((prev) => ({ ...prev, desc: event.target.value }))}
                    rows={3}
                    placeholder="Pet details..."
                    className="w-full rounded-md bg-zinc-950 border border-white/10 px-3.5 py-2.5 text-[11px] font-medium text-zinc-100 outline-none focus:border-brand-accent transition-all resize-none"
                  />
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 items-end">
                  {[
                    { key: 'zenith_price', label: 'COST' },
                    { key: 'req_level', label: 'LVL REQ' },
                    { key: 'sort_order', label: 'ORDER' },
                  ].map((item) => (
                    <div key={item.key} className="space-y-1.5">
                      <span className="text-[9px] font-bold text-zinc-700 uppercase tracking-widest pl-1">
                        {item.label}
                      </span>
                      <Input
                        value={pet[item.key as keyof typeof pet] as string}
                        onChange={(event) =>
                          setPet((prev) => ({ ...prev, [item.key]: event.target.value }))
                        }
                        inputMode="numeric"
                        className="font-mono text-center h-10 px-2"
                      />
                    </div>
                  ))}
                  <div className="flex items-center gap-3 h-10 pl-2">
                    <input
                      type="checkbox"
                      checked={pet.enabled}
                      onChange={(event) =>
                        setPet((prev) => ({ ...prev, enabled: event.target.checked }))
                      }
                      className="h-5 w-5 rounded border-white/10 bg-zinc-950 accent-brand-accent cursor-pointer"
                      id="pet-enabled"
                    />
                    <label
                      htmlFor="pet-enabled"
                      className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest cursor-pointer select-none"
                    >
                      Enabled
                    </label>
                  </div>
                </div>
              </div>
            )}
          </Card>
        </section>

        <div className="pt-4">
          {mode === 'character' && (
            <div className="flex items-start gap-3 mb-4 p-3 rounded-md bg-zinc-900/50 border border-white/5">
              <input
                type="checkbox"
                checked={rightsConfirmed}
                onChange={(event) => setRightsConfirmed(event.target.checked)}
                className="h-4 w-4 mt-0.5 rounded border-white/10 bg-zinc-950 accent-brand-accent cursor-pointer shrink-0"
                id="rights-confirm"
              />
              <label
                htmlFor="rights-confirm"
                className="text-[10px] font-medium text-zinc-400 leading-relaxed cursor-pointer select-none"
              >
                I confirm I have the right to share this media, and it follows the content
                rules: no adult/NSFW content, no content meant to harass or defame.
              </label>
            </div>
          )}
          <Button
            type="submit"
            disabled={submitting || (mode === 'character' && !rightsConfirmed)}
            variant="accent"
            className="w-full h-14"
            isLoading={submitting}
            leftIcon={<UploadCloud size={18} />}
          >
            Authorize Intake
          </Button>
        </div>
      </form>
    </div>
  );
};
