import { AnimatePresence, m } from 'framer-motion';
import { Loader2, Pencil, Plus, Sparkles, Trash2, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { apiFetch, getErrorMessage } from '../../api/client';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { Input } from '../ui/Input';
import { useToast } from '../ui/Toast';
import { cn } from '../../utils';

export interface RarityDoc {
  _id: number;
  emoji: string;
  name: string;
  spawn_weight: number;
  active_spawn_weight: number;
  shop_weight: number;
  claim_weight: number;
  shop_price: number;
  stock_limit: number;
  sell_price: number;
}

interface RaritiesResponse {
  rarities: RarityDoc[];
  fields: string[];
}

const NUMERIC_FIELDS = [
  { key: 'spawn_weight', label: 'Spawn Wt' },
  { key: 'active_spawn_weight', label: 'Active Wt' },
  { key: 'shop_weight', label: 'Shop Wt' },
  { key: 'claim_weight', label: 'Claim Wt' },
  { key: 'shop_price', label: 'Price' },
  { key: 'stock_limit', label: 'Stock' },
  { key: 'sell_price', label: 'Sell' },
] as const;

const label = (r: RarityDoc) => `${r.emoji} ${r.name}`.trim();

const RarityRow = ({
  rarity,
  onSaved,
  onDeleted,
}: {
  rarity: RarityDoc;
  onSaved: (r: RarityDoc) => void;
  onDeleted: (id: number) => void;
}) => {
  const { addToast } = useToast();
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [emoji, setEmoji] = useState(rarity.emoji);
  const [name, setName] = useState(rarity.name);
  const [values, setValues] = useState<Record<string, number>>(() =>
    Object.fromEntries(NUMERIC_FIELDS.map((f) => [f.key, Number(rarity[f.key]) || 0])),
  );

  const dirty =
    emoji !== rarity.emoji ||
    name !== rarity.name ||
    NUMERIC_FIELDS.some((f) => (values[f.key] ?? 0) !== (Number(rarity[f.key]) || 0));

  const save = async () => {
    setSaving(true);
    try {
      if (emoji !== rarity.emoji || name !== rarity.name) {
        await apiFetch(`/admin/rarities/${rarity._id}/rename`, {
          method: 'POST',
          body: JSON.stringify({ emoji: emoji.trim(), name: name.trim() }),
        });
      }
      for (const f of NUMERIC_FIELDS) {
        const v = values[f.key] ?? 0;
        if (v !== (Number(rarity[f.key]) || 0)) {
          await apiFetch(`/admin/rarities/${rarity._id}`, {
            method: 'PATCH',
            body: JSON.stringify({ field: f.key, value: v }),
          });
        }
      }
      addToast(`${label(rarity)} updated.`, 'success');
      onSaved({ ...rarity, emoji: emoji.trim(), name: name.trim(), ...values });
      setEditing(false);
    } catch (err) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!window.confirm(`Delete rarity ${label(rarity)}? Only works if no characters use it.`)) {
      return;
    }
    setSaving(true);
    try {
      await apiFetch(`/admin/rarities/${rarity._id}`, { method: 'DELETE' });
      addToast(`${label(rarity)} deleted.`, 'success');
      onDeleted(rarity._id);
    } catch (err) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card variant="default" className={cn('p-3.5', editing && 'border-brand-accent/30')}>
      <div className="flex items-center gap-3">
        <span className="text-lg leading-none w-6 text-center shrink-0">{rarity.emoji}</span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-[12px] font-bold text-zinc-100 uppercase tracking-tight">
              {rarity.name}
            </h3>
            <Badge variant="secondary" size="xs">
              ID_{rarity._id}
            </Badge>
          </div>
          <p className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest truncate">
            {NUMERIC_FIELDS.map((f) => `${f.label} ${rarity[f.key]}`).join(' • ')}
          </p>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            aria-label={editing ? 'Close editor' : 'Edit rarity'}
            onClick={() => setEditing((v) => !v)}
            className="w-8 h-8 flex items-center justify-center rounded-md text-zinc-500 hover:text-zinc-200 hover:bg-white/5 transition-colors"
          >
            {editing ? <X size={14} /> : <Pencil size={14} />}
          </button>
          <button
            type="button"
            aria-label="Delete rarity"
            onClick={remove}
            disabled={saving}
            className="w-8 h-8 flex items-center justify-center rounded-md text-zinc-500 hover:text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-40"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      <AnimatePresence>
        {editing && (
          <m.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="mt-3 pt-3 border-t border-white/5 space-y-3">
              <div className="flex gap-2">
                <Input
                  value={emoji}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setEmoji(e.target.value)}
                  className="w-16 text-center"
                  aria-label="Rarity emoji"
                  maxLength={8}
                />
                <Input
                  value={name}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setName(e.target.value)}
                  className="flex-1"
                  aria-label="Rarity name"
                  maxLength={40}
                />
              </div>
              <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
                {NUMERIC_FIELDS.map((f) => (
                  <label key={f.key} className="space-y-1">
                    <span className="text-[8px] font-bold text-zinc-600 uppercase tracking-widest block">
                      {f.label}
                    </span>
                    <input
                      type="number"
                      min={0}
                      value={values[f.key] ?? 0}
                      onChange={(e) =>
                        setValues((prev) => ({ ...prev, [f.key]: Math.max(0, Number(e.target.value) || 0) }))
                      }
                      className="w-full h-9 px-2.5 bg-zinc-950 border border-white/10 rounded-md text-[11px] font-mono font-bold text-zinc-100 tabular-nums outline-none focus:border-brand-accent transition-colors"
                    />
                  </label>
                ))}
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>
                  Cancel
                </Button>
                <Button variant="accent" size="sm" onClick={save} disabled={!dirty || saving}>
                  {saving ? <Loader2 size={12} className="animate-spin" /> : null}
                  Save
                </Button>
              </div>
            </div>
          </m.div>
        )}
      </AnimatePresence>
    </Card>
  );
};

export const RarityEditor = () => {
  const { addToast } = useToast();
  const [rarities, setRarities] = useState<RarityDoc[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [newId, setNewId] = useState('');
  const [newEmoji, setNewEmoji] = useState('');
  const [newName, setNewName] = useState('');

  const load = async () => {
    try {
      const data: RaritiesResponse = await apiFetch('/admin/rarities');
      setRarities(data.rarities);
      setError(null);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  useEffect(() => {
    load();
  }, []);

  const add = async () => {
    setAdding(true);
    try {
      await apiFetch('/admin/rarities', {
        method: 'POST',
        body: JSON.stringify({
          rarity_id: Number(newId),
          emoji: newEmoji.trim(),
          name: newName.trim(),
        }),
      });
      addToast(`${newEmoji.trim()} ${newName.trim()} added.`, 'success');
      setShowAdd(false);
      setNewId('');
      setNewEmoji('');
      setNewName('');
      load();
    } catch (err) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setAdding(false);
    }
  };

  const validAdd = Number(newId) >= 1 && newEmoji.trim() && newName.trim();

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest px-1">
          Rarity Registry
        </h2>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowAdd((v) => !v)}
          aria-expanded={showAdd}
        >
          {showAdd ? <X size={12} /> : <Plus size={12} />}
          {showAdd ? 'Cancel' : 'Add'}
        </Button>
      </div>

      <AnimatePresence>
        {showAdd && (
          <m.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <Card variant="default" className="p-3.5 space-y-3">
              <div className="flex gap-2">
                <Input
                  value={newId}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewId(e.target.value)}
                  className="w-20"
                  placeholder="ID"
                  type="number"
                  min={1}
                  aria-label="New rarity ID"
                />
                <Input
                  value={newEmoji}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewEmoji(e.target.value)}
                  className="w-16 text-center"
                  placeholder="🙂"
                  maxLength={8}
                  aria-label="New rarity emoji"
                />
                <Input
                  value={newName}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewName(e.target.value)}
                  className="flex-1"
                  placeholder="Name"
                  maxLength={40}
                  aria-label="New rarity name"
                />
              </div>
              <div className="flex justify-end">
                <Button variant="accent" size="sm" onClick={add} disabled={!validAdd || adding}>
                  {adding ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
                  Create
                </Button>
              </div>
            </Card>
          </m.div>
        )}
      </AnimatePresence>

      {error ? (
        <p className="text-[10px] font-bold text-red-500 uppercase tracking-widest px-1">{error}</p>
      ) : rarities === null ? (
        <div className="flex justify-center py-8">
          <Loader2 size={20} className="animate-spin text-zinc-700" />
        </div>
      ) : (
        <div className="space-y-2">
          {rarities.map((r) => (
            <RarityRow
              key={r._id}
              rarity={r}
              onSaved={(updated) =>
                setRarities((prev) => prev?.map((x) => (x._id === updated._id ? updated : x)) ?? null)
              }
              onDeleted={(id) => setRarities((prev) => prev?.filter((x) => x._id !== id) ?? null)}
            />
          ))}
        </div>
      )}
    </div>
  );
};
