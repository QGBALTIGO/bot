import { AnimatePresence, m } from 'framer-motion';
import { Check, History, ImagePlus, Link as LinkIcon, Loader2, RefreshCw, Search, ShieldCheck, Undo2, UploadCloud } from 'lucide-react';
import { ChangeEvent, useEffect, useMemo, useState } from 'react';
import { apiFetch, getErrorMessage } from '../api/client';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { Skeleton } from '../components/ui/Skeleton';
import { useToast } from '../components/ui/Toast';
import { cn, FALLBACK_IMAGE } from '../utils';

interface CharacterResult {
  id: number;
  name: string;
  anime: string;
  anime_id: number;
  image: string;
}

interface AssetItem {
  asset_id: number;
  character_id: number;
  source_url?: string | null;
  storage_url: string;
  content_sha256: string;
  output_width: number;
  output_height: number;
  crop_metadata?: {
    source_width?: number;
    source_height?: number;
    crop_retention?: number;
    output_width?: number;
    output_height?: number;
  };
  source_kind: string;
  is_primary: boolean;
  uploaded_by: number;
  created_at?: string | null;
  activated_at?: string | null;
}

interface AssetsResponse {
  character: CharacterResult;
  assets: AssetItem[];
}

type SourceMode = 'url' | 'file';

const dateLabel = (raw?: string | null) => {
  if (!raw) return '—';
  const date = new Date(raw);
  if (!Number.isFinite(date.getTime())) return '—';
  return new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
};

export const MediaAdmin = () => {
  const { addToast } = useToast();
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<CharacterResult[]>([]);
  const [selected, setSelected] = useState<CharacterResult | null>(null);
  const [assets, setAssets] = useState<AssetItem[]>([]);
  const [loadingAssets, setLoadingAssets] = useState(false);
  const [mode, setMode] = useState<SourceMode>('url');
  const [mediaUrl, setMediaUrl] = useState('');
  const [mediaData, setMediaData] = useState('');
  const [filename, setFilename] = useState('');
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [restoring, setRestoring] = useState<number | null>(null);

  const preview = useMemo(() => (mode === 'url' ? mediaUrl.trim() : mediaData), [mode, mediaUrl, mediaData]);

  const runSearch = async () => {
    const value = query.trim();
    if (!value || searching) return;
    setSearching(true);
    try {
      const response = await apiFetch(`/admin/media/search?q=${encodeURIComponent(value)}&limit=40`);
      setResults(Array.isArray(response.items) ? response.items : []);
    } catch (err) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setSearching(false);
    }
  };

  const loadAssets = async (character: CharacterResult) => {
    setSelected(character);
    setLoadingAssets(true);
    setAssets([]);
    setMediaUrl('');
    setMediaData('');
    setFilename('');
    setRightsConfirmed(false);
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    try {
      const response: AssetsResponse = await apiFetch(`/admin/media/${character.id}/assets`);
      setSelected(response.character || character);
      setAssets(response.assets || []);
    } catch (err) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setLoadingAssets(false);
    }
  };

  const handleFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      addToast('Selecione um arquivo de imagem.', 'error');
      event.target.value = '';
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      addToast('A imagem deve ter no máximo 10 MB.', 'error');
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

  const replaceImage = async () => {
    if (!selected || processing || !rightsConfirmed) return;
    if (mode === 'url' && !mediaUrl.trim()) {
      addToast('Informe a URL da nova imagem.', 'error');
      return;
    }
    if (mode === 'file' && !mediaData) {
      addToast('Selecione a nova imagem.', 'error');
      return;
    }

    setProcessing(true);
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred('heavy');
    try {
      const response = await apiFetch(`/admin/media/${selected.id}/replace`, {
        method: 'POST',
        timeoutMs: 90000,
        body: JSON.stringify({
          media_url: mode === 'url' ? mediaUrl.trim() : '',
          media_data: mode === 'file' ? mediaData : '',
          filename: mode === 'file' ? filename : '',
          rights_confirmed: true,
        }),
      });
      const outputWidth = Number(response?.asset?.output_width || 0);
      const outputHeight = Number(response?.asset?.output_height || 0);
      addToast(`Arte atualizada em ${outputWidth}×${outputHeight} sem alterar o ID ${selected.id}.`, 'success');
      setMediaUrl('');
      setMediaData('');
      setFilename('');
      setRightsConfirmed(false);
      await loadAssets({ ...selected, image: response?.character?.image || selected.image });
    } catch (err) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setProcessing(false);
    }
  };

  const restoreAsset = async (asset: AssetItem) => {
    if (!selected || asset.is_primary || restoring) return;
    setRestoring(asset.asset_id);
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    try {
      await apiFetch(`/admin/media/assets/${asset.asset_id}/activate`, { method: 'POST' });
      addToast(`Arte anterior de ${selected.name} restaurada.`, 'success');
      await loadAssets(selected);
    } catch (err) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setRestoring(null);
    }
  };

  useEffect(() => {
    const onlyResult = results[0];
    if (!selected && results.length === 1 && onlyResult) void loadAssets(onlyResult);
  }, [results, selected]);

  return (
    <div className="pt-6 max-w-4xl mx-auto adaptive-px space-y-8">
      <header className="space-y-1">
        <div className="flex items-center gap-2.5">
          <ImagePlus size={20} className="text-brand-accent" />
          <h1 className="text-xl font-bold text-zinc-100 uppercase tracking-tight">Artes 2:3</h1>
        </div>
        <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest opacity-60">
          Troque a mídia mantendo o mesmo personagem, ID e coleção
        </p>
      </header>

      <Card variant="surface" className="p-5 space-y-4">
        <div className="flex items-center gap-2">
          <ShieldCheck size={14} className="text-emerald-500" />
          <p className="text-[9px] font-bold text-zinc-500 uppercase tracking-widest">
            O character_id nunca é alterado neste painel
          </p>
        </div>
        <div className="flex gap-2">
          <Input
            icon={Search}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') void runSearch();
            }}
            placeholder="Nome do personagem ou obra..."
            className="h-11"
          />
          <Button variant="accent" className="h-11 px-5" isLoading={searching} onClick={runSearch}>
            Buscar
          </Button>
        </div>

        <AnimatePresence mode="popLayout">
          {results.length > 0 && (
            <m.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
              {results.map((character) => (
                <button
                  key={character.id}
                  type="button"
                  onClick={() => void loadAssets(character)}
                  className={cn(
                    'relative aspect-[2/3] rounded-lg overflow-hidden border text-left transition-all',
                    selected?.id === character.id ? 'border-brand-accent ring-1 ring-brand-accent/50' : 'border-white/5 hover:border-white/20',
                  )}
                >
                  <img src={character.image || FALLBACK_IMAGE} alt={character.name} className="absolute inset-0 w-full h-full object-cover" referrerPolicy="no-referrer" />
                  <div className="absolute inset-0 bg-gradient-to-t from-black via-black/10 to-transparent" />
                  <div className="absolute bottom-0 inset-x-0 p-3">
                    <p className="text-[10px] font-bold text-white uppercase truncate">{character.name}</p>
                    <p className="text-[8px] font-bold text-zinc-400 uppercase truncate mt-0.5">{character.anime}</p>
                    <p className="text-[8px] font-mono text-zinc-600 mt-1">ID {character.id}</p>
                  </div>
                </button>
              ))}
            </m.div>
          )}
        </AnimatePresence>
      </Card>

      {selected && (
        <section className="space-y-5">
          <Card variant="surface" className="p-5 grid grid-cols-[110px_1fr] sm:grid-cols-[150px_1fr] gap-5 items-start">
            <div className="aspect-[2/3] rounded-lg overflow-hidden border border-white/10 bg-zinc-900">
              <img src={selected.image || FALLBACK_IMAGE} alt={selected.name} className="w-full h-full object-cover" referrerPolicy="no-referrer" />
            </div>
            <div className="min-w-0 space-y-4">
              <div>
                <p className="text-lg font-bold text-zinc-100 uppercase tracking-tight truncate">{selected.name}</p>
                <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mt-1 truncate">{selected.anime}</p>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="bg-zinc-950 border border-white/5 rounded-md p-3">
                  <p className="text-[8px] text-zinc-600 uppercase tracking-widest">Character ID</p>
                  <p className="text-sm font-mono font-bold text-zinc-100 mt-1">{selected.id}</p>
                </div>
                <div className="bg-zinc-950 border border-white/5 rounded-md p-3">
                  <p className="text-[8px] text-zinc-600 uppercase tracking-widest">Anime ID</p>
                  <p className="text-sm font-mono font-bold text-zinc-100 mt-1">{selected.anime_id || '—'}</p>
                </div>
              </div>
            </div>
          </Card>

          <Card variant="surface" className="p-5 space-y-5">
            <div className="flex items-center justify-between gap-4">
              <div>
                <h2 className="text-sm font-bold text-zinc-100 uppercase tracking-tight">Nova arte</h2>
                <p className="text-[9px] text-zinc-600 uppercase tracking-widest mt-1">O servidor valida, recorta e salva em 2:3</p>
              </div>
              <Badge variant="primary" size="xs">2:3 OBRIGATÓRIO</Badge>
            </div>

            <div className="grid grid-cols-2 gap-1 p-1 bg-zinc-950 border border-white/5 rounded-md">
              <button type="button" onClick={() => setMode('url')} className={cn('h-9 rounded text-[9px] font-bold uppercase tracking-widest flex items-center justify-center gap-2', mode === 'url' ? 'bg-zinc-800 text-white' : 'text-zinc-600')}>
                <LinkIcon size={13} /> URL
              </button>
              <button type="button" onClick={() => setMode('file')} className={cn('h-9 rounded text-[9px] font-bold uppercase tracking-widest flex items-center justify-center gap-2', mode === 'file' ? 'bg-zinc-800 text-white' : 'text-zinc-600')}>
                <UploadCloud size={13} /> Arquivo
              </button>
            </div>

            {mode === 'url' ? (
              <Input icon={LinkIcon} value={mediaUrl} onChange={(event) => setMediaUrl(event.target.value)} placeholder="https://..." className="h-11" />
            ) : (
              <label className="h-24 rounded-md border border-dashed border-white/10 bg-zinc-950 flex flex-col items-center justify-center gap-2 cursor-pointer hover:border-brand-accent/30 transition-colors">
                <input type="file" accept="image/jpeg,image/png,image/webp,image/gif" onChange={handleFile} className="hidden" />
                <UploadCloud size={20} className="text-zinc-600" />
                <span className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest">{filename || 'Selecionar imagem — máx. 10 MB'}</span>
              </label>
            )}

            {preview && (
              <div className="mx-auto w-40 aspect-[2/3] rounded-lg overflow-hidden border border-white/10 bg-zinc-950">
                <img src={preview} alt="Prévia" className="w-full h-full object-cover" />
              </div>
            )}

            <label className="flex items-start gap-3 p-4 rounded-md bg-zinc-950 border border-white/5 cursor-pointer">
              <input type="checkbox" checked={rightsConfirmed} onChange={(event) => setRightsConfirmed(event.target.checked)} className="mt-0.5 accent-blue-500" />
              <span className="text-[10px] text-zinc-500 leading-relaxed">
                Confirmo que tenho autorização para usar esta imagem. A arte processada substituirá apenas a imagem primária do personagem ID {selected.id}; a coleção dos usuários não será alterada.
              </span>
            </label>

            <Button variant="accent" className="w-full h-12" onClick={replaceImage} disabled={!rightsConfirmed || !preview || processing} isLoading={processing} leftIcon={<ImagePlus size={15} />}>
              Processar e definir como arte principal
            </Button>
          </Card>

          <Card variant="surface" className="p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <History size={14} className="text-zinc-500" />
                <h2 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Histórico de artes</h2>
              </div>
              <Button variant="ghost" size="sm" className="w-8 h-8 p-0" onClick={() => void loadAssets(selected)} isLoading={loadingAssets}>
                <RefreshCw size={14} />
              </Button>
            </div>

            {loadingAssets ? (
              <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="aspect-[2/3] rounded-md" />)}</div>
            ) : assets.length > 0 ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                {assets.map((asset) => (
                  <div key={asset.asset_id} className={cn('rounded-lg border overflow-hidden bg-zinc-950', asset.is_primary ? 'border-emerald-500/30' : 'border-white/5')}>
                    <div className="aspect-[2/3] relative">
                      <img src={asset.storage_url} alt="Arte" className="absolute inset-0 w-full h-full object-cover" referrerPolicy="no-referrer" />
                      {asset.is_primary && <div className="absolute top-2 right-2 w-6 h-6 rounded-full bg-emerald-500 text-black flex items-center justify-center"><Check size={13} strokeWidth={3} /></div>}
                    </div>
                    <div className="p-3 space-y-2">
                      <p className="text-[8px] font-mono text-zinc-600">{asset.output_width}×{asset.output_height}</p>
                      <p className="text-[8px] text-zinc-700">{dateLabel(asset.activated_at || asset.created_at)}</p>
                      {!asset.is_primary && (
                        <Button variant="outline" size="sm" className="w-full h-8 text-[8px]" isLoading={restoring === asset.asset_id} onClick={() => void restoreAsset(asset)}>
                          <Undo2 size={11} className="mr-1.5" /> Restaurar
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-12 text-center border border-dashed border-white/5 rounded-md">
                <p className="text-[9px] font-bold text-zinc-700 uppercase tracking-widest">Nenhuma arte processada pelo AniNexus ainda</p>
              </div>
            )}
          </Card>
        </section>
      )}
    </div>
  );
};
