import { m } from 'framer-motion';
import { Coins, Gem, History, Image as ImageIcon, Loader2, Lock, Pencil } from 'lucide-react';
import { useEffect, useState } from 'react';
import { apiFetch, getErrorMessage, invalidateQueries } from '../../api/client';
import { type Character, type User, useUser } from '../../context/UserContext';
import { formatNumber } from '../../utils';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { useToast } from '../ui/Toast';
import { Modal } from './Modal';

interface CharActionModalProps {
  selectedChar: Character | null;
  setSelectedChar: (char: Character | null) => void;
  activeTab: string;
  user: User | null;
  onPurchaseSuccess?: (char: Character) => void;
}

interface RarityOption {
  value: number;
  label: string;
}

interface CharacterEditForm {
  name: string;
  anime: string;
  rarity: string;
  img_url: string;
}

const buildEditForm = (character: Character | null): CharacterEditForm => ({
  name: character?.name || '',
  anime: character?.anime || '',
  rarity: character?.rarity || '',
  img_url: character?.img_url || '',
});

const EDIT_TEXT_MAX = 120;
const EDIT_URL_MAX = 1000;
// biome-ignore lint/suspicious/noControlCharactersInRegex: control chars are exactly what we strip
const CONTROL_CHAR_RE = /[\x00-\x1f\x7f]/;

type EditErrors = Partial<Record<keyof CharacterEditForm, string>>;

const validateEditForm = (
  form: CharacterEditForm,
  rarityOptions: RarityOption[],
): EditErrors => {
  const errors: EditErrors = {};

  const name = form.name.trim();
  if (!name) errors.name = 'Name is required.';
  else if (name.length > EDIT_TEXT_MAX) errors.name = `Max ${EDIT_TEXT_MAX} characters.`;
  else if (CONTROL_CHAR_RE.test(name)) errors.name = 'Invalid control characters.';

  const anime = form.anime.trim();
  if (!anime) errors.anime = 'Source is required.';
  else if (anime.length > EDIT_TEXT_MAX) errors.anime = `Max ${EDIT_TEXT_MAX} characters.`;
  else if (CONTROL_CHAR_RE.test(anime)) errors.anime = 'Invalid control characters.';

  const rarity = form.rarity.trim();
  if (!rarity) errors.rarity = 'Rarity is required.';
  else if (rarityOptions.length > 0 && !rarityOptions.some((o) => o.label === rarity))
    errors.rarity = 'Unknown rarity class.';

  const img_url = form.img_url.trim();
  if (!img_url) errors.img_url = 'Image URL is required.';
  else if (img_url.length > EDIT_URL_MAX) errors.img_url = 'URL too long.';
  else {
    try {
      const parsed = new URL(img_url);
      if (parsed.protocol !== 'https:') errors.img_url = 'Must be an https:// URL.';
      else if (!parsed.hostname) errors.img_url = 'Missing hostname.';
      else if (parsed.username || parsed.password) errors.img_url = 'Credentials not allowed.';
    } catch {
      errors.img_url = 'Invalid URL.';
    }
  }

  return errors;
};

// Isolated so keystrokes only re-render the form, not the whole modal.
const CharacterEditPanel = ({
  character,
  rarityOptions,
  saving,
  onCancel,
  onSave,
}: {
  character: Character;
  rarityOptions: RarityOption[];
  saving: boolean;
  onCancel: () => void;
  onSave: (form: CharacterEditForm) => void;
}) => {
  const [form, setForm] = useState<CharacterEditForm>(() => buildEditForm(character));
  const [errors, setErrors] = useState<EditErrors>({});

  const updateField = (field: keyof CharacterEditForm, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
    if (errors[field]) setErrors((prev) => ({ ...prev, [field]: undefined }));
  };

  const submit = () => {
    if (saving) return;
    const nextErrors = validateEditForm(form, rarityOptions);
    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      return;
    }
    onSave(form);
  };

  return (
    <m.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-4 p-4 rounded-md border border-white/5 bg-zinc-900"
    >
      <div className="space-y-3">
        <div className="space-y-1">
          <span className="text-[9px] font-bold uppercase text-zinc-600 tracking-widest pl-0.5">
            Character Name
          </span>
          <Input
            value={form.name}
            onChange={(event) => updateField('name', event.target.value)}
            disabled={saving}
            maxLength={EDIT_TEXT_MAX}
            error={errors.name}
            placeholder="Name..."
          />
        </div>
        <div className="space-y-1">
          <span className="text-[9px] font-bold uppercase text-zinc-600 tracking-widest pl-0.5">
            Source
          </span>
          <Input
            value={form.anime}
            onChange={(event) => updateField('anime', event.target.value)}
            disabled={saving}
            maxLength={EDIT_TEXT_MAX}
            error={errors.anime}
            placeholder="Source..."
          />
        </div>
        <div className="space-y-1">
          <span className="text-[9px] font-bold uppercase text-zinc-600 tracking-widest pl-0.5">
            Rarity Class
          </span>
          <div className="relative group">
            <select
              aria-label="Rarity class"
              value={form.rarity}
              onChange={(event) => updateField('rarity', event.target.value)}
              disabled={saving}
              className="w-full h-10 bg-zinc-950 border border-white/10 rounded-md px-3.5 text-[11px] font-bold text-zinc-100 uppercase tracking-widest outline-none focus:border-brand-accent transition-all appearance-none cursor-pointer"
            >
              {!rarityOptions.some((option) => option.label === form.rarity) && form.rarity && (
                <option value={form.rarity}>{form.rarity.toUpperCase()}</option>
              )}
              {rarityOptions.map((option) => (
                <option key={option.value} value={option.label}>
                  Tier {option.value}: {option.label.toUpperCase()}
                </option>
              ))}
            </select>
          </div>
          {errors.rarity && (
            <p className="text-[9px] font-bold text-red-500 uppercase tracking-widest pl-1">
              {errors.rarity}
            </p>
          )}
        </div>
        <div className="space-y-1">
          <span className="text-[9px] font-bold uppercase text-zinc-600 tracking-widest pl-0.5">
            Visual Manifest
          </span>
          <Input
            icon={ImageIcon}
            value={form.img_url}
            onChange={(event) => updateField('img_url', event.target.value)}
            disabled={saving}
            maxLength={EDIT_URL_MAX}
            error={errors.img_url}
            placeholder="Image URL..."
          />
        </div>
      </div>

      <div className="flex gap-2 pt-1">
        <Button variant="outline" size="sm" onClick={onCancel} disabled={saving} className="flex-1">
          Cancel
        </Button>
        <Button
          onClick={submit}
          variant="secondary"
          size="sm"
          isLoading={saving}
          className="flex-[1.5]"
        >
          Update Character
        </Button>
      </div>
    </m.div>
  );
};

export const CharActionModal = ({
  selectedChar,
  setSelectedChar,
  activeTab,
  user,
  onPurchaseSuccess,
}: CharActionModalProps) => {
  const { addToast } = useToast();
  const { triggerRefresh } = useUser();
  const [purchaseStage, setPurchaseStage] = useState('idle');
  const [sellStage, setSellStage] = useState('idle');
  const [confirm, setConfirm] = useState<null | { kind: 'recycle' | 'sell'; message: string }>(
    null,
  );
  const [editMode, setEditMode] = useState(false);
  const [editStage, setEditStage] = useState<'idle' | 'saving'>('idle');
  const [rarityOptions, setRarityOptions] = useState<RarityOption[]>([]);
  const canEdit = Boolean(user?.can_edit_character ?? user?.is_sudo);
  const selectedCharId = selectedChar?.id;

  // biome-ignore lint/correctness/useExhaustiveDependencies: id is the reset trigger, not a body dep
  useEffect(() => {
    setPurchaseStage('idle');
    setSellStage('idle');
    setEditStage('idle');
    setEditMode(false);
  }, [selectedCharId]);

  useEffect(() => {
    if (!canEdit || rarityOptions.length > 0) return;

    let cancelled = false;
    apiFetch('/admin/upload/options')
      .then((data) => {
        if (!cancelled) setRarityOptions(data?.character_rarities || []);
      })
      .catch((err) => console.warn('Registry error:', err));

    return () => {
      cancelled = true;
    };
  }, [canEdit, rarityOptions.length]);

  if (!selectedChar) return null;

  const isOwned = (user?.characters || []).some(
    (c: Character) => String(c.id) === String(selectedChar.id),
  );
  const zenithBalance = Number(user?.stats.zenith ?? user?.zenith ?? 0);
  const price = Number(selectedChar.zenith_price || 0);
  const stockRemaining =
    typeof selectedChar.stock_remaining === 'number'
      ? selectedChar.stock_remaining
      : typeof selectedChar.stock_limit === 'number' && typeof selectedChar.sold_count === 'number'
        ? Math.max(0, selectedChar.stock_limit - selectedChar.sold_count)
        : null;
  const isSoldOut =
    Boolean(selectedChar.sold_out) || (stockRemaining !== null && stockRemaining <= 0);
  const canAfford = zenithBalance >= price;

  const handleEditSave = async (form: CharacterEditForm) => {
    if (editStage !== 'idle') return;

    const payload = {
      name: form.name.trim(),
      anime: form.anime.trim(),
      rarity: form.rarity.trim(),
      img_url: form.img_url.trim(),
    };

    setEditStage('saving');
    try {
      const result = await apiFetch(`/admin/character/${selectedChar.id}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      });
      const updatedChar = {
        ...selectedChar,
        ...(result?.character || payload),
        id: selectedChar.id,
      };

      setSelectedChar(updatedChar);
      setEditMode(false);
      addToast('Registry updated.', 'success');
      triggerRefresh();
      invalidateQueries(['/gallery', '/harem', '/shop/characters', '/shop/hub']);
    } catch (err: any) {
      addToast(getErrorMessage(err), 'error');
    } finally {
      setEditStage('idle');
    }
  };

  const handleBuy = async () => {
    setPurchaseStage('buying');
    try {
      await apiFetch(`/shop/buy/character/${selectedChar.id}`, { method: 'POST' });
      triggerRefresh();
      invalidateQueries(['/shop/characters', '/shop/hub']);
      setSelectedChar(null);
      if (onPurchaseSuccess) onPurchaseSuccess(selectedChar);
    } catch (err: any) {
      addToast(getErrorMessage(err), 'error');
      setPurchaseStage('idle');
    }
  };

  const doRecycle = async () => {
    setConfirm(null);
    setSellStage('selling');
    try {
      const res = await apiFetch('/recycle', {
        method: 'POST',
        body: JSON.stringify([selectedChar.id]),
      });
      addToast(`Character recycled: +${res.reward} Coins`, 'success');
      triggerRefresh();
      setSelectedChar(null);
    } catch (err: any) {
      addToast(getErrorMessage(err), 'error');
      setSellStage('idle');
    }
  };

  const doSell = async () => {
    setConfirm(null);
    setSellStage('selling');
    try {
      const res = await apiFetch(`/character/sell/${selectedChar.id}`, { method: 'POST' });
      addToast(`Character sold: +${res.reward} Coins`, 'success');
      triggerRefresh();
      setSelectedChar(null);
    } catch (err: any) {
      addToast(getErrorMessage(err), 'error');
      setSellStage('idle');
    }
  };

  // Prefer Telegram's native confirm when present; otherwise fall back to an
  // in-app confirm (setConfirm) so destructive actions still prompt outside
  // the Telegram WebApp where showConfirm is undefined.
  const askConfirm = (kind: 'recycle' | 'sell', message: string) => {
    const native = window.Telegram?.WebApp?.showConfirm;
    if (native) {
      native(message, async (confirmed) => {
        if (!confirmed) {
          setSellStage('idle');
          return;
        }
        if (kind === 'recycle') await doRecycle();
        else await doSell();
      });
      return;
    }
    setConfirm({ kind, message });
  };

  const handleRecycle = async () => {
    setSellStage('previewing');
    try {
      const preview = await apiFetch('/recycle/preview', {
        method: 'POST',
        body: JSON.stringify([selectedChar.id]),
      });
      askConfirm(
        'recycle',
        `Recycle ${selectedChar.name.toUpperCase()} for ${preview.reward} Coins?`,
      );
    } catch (err: any) {
      addToast(getErrorMessage(err), 'error');
      setSellStage('idle');
    }
  };

  const handleSell = () => {
    setSellStage('selling');
    askConfirm('sell', `Sell ${selectedChar.name.toUpperCase()} for Coins?`);
  };

  const actions = (
    <div className="w-full space-y-4">
      {canEdit && (
        <div className="w-full">
          {editMode ? (
            <CharacterEditPanel
              character={selectedChar}
              rarityOptions={rarityOptions}
              saving={editStage === 'saving'}
              onCancel={() => setEditMode(false)}
              onSave={handleEditSave}
            />
          ) : (
            <Button
              variant="secondary"
              onClick={() => setEditMode(true)}
              className="w-full group h-10"
              leftIcon={
                <Pencil
                  size={14}
                  className="text-zinc-500 transition-colors group-hover:text-brand-accent"
                />
              }
            >
              Modify Records
            </Button>
          )}
        </div>
      )}

      {!editMode && activeTab === 'shop' && !isOwned && (
        <div className="w-full">
          {isSoldOut ? (
            <Badge
              variant="danger"
              icon={Lock}
              className="w-full py-4 rounded-md justify-center font-bold border-none bg-red-500/10 text-red-500"
            >
              DEPLETED
            </Badge>
          ) : !canAfford ? (
            <div className="flex flex-col gap-2">
              <Badge
                variant="secondary"
                icon={Gem}
                className="w-full py-4 rounded-md justify-center font-bold border-white/5 opacity-50"
              >
                {formatNumber(price - zenithBalance)} Prisms Needed
              </Badge>
              <p className="text-[8px] font-bold text-center text-zinc-700 uppercase tracking-widest">
                Insufficient funds
              </p>
            </div>
          ) : purchaseStage === 'idle' ? (
            <Button
              onClick={() => setPurchaseStage('confirm')}
              variant="accent"
              className="w-full h-11"
            >
              Summon Character ({formatNumber(price)} Prisms)
            </Button>
          ) : (
            <m.div
              initial={{ opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
              className="flex gap-3"
            >
              <Button
                variant="outline"
                onClick={() => setPurchaseStage('idle')}
                className="flex-1 h-11"
              >
                Abort
              </Button>
              <Button
                variant="accent"
                onClick={handleBuy}
                isLoading={purchaseStage === 'buying'}
                className="flex-[2] h-11"
              >
                Confirm Summon
              </Button>
            </m.div>
          )}
        </div>
      )}

      {!editMode && isOwned && !confirm && (
        <div className="flex gap-3">
          <Button
            variant="danger"
            onClick={handleRecycle}
            disabled={sellStage !== 'idle'}
            className="flex-1 h-11"
            leftIcon={
              sellStage === 'previewing' || sellStage === 'selling' ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <History size={14} />
              )
            }
          >
            Recycle
          </Button>

          <Button
            variant="secondary"
            onClick={handleSell}
            disabled={sellStage !== 'idle'}
            className="flex-1 h-11"
            leftIcon={
              sellStage === 'selling' ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Coins size={14} />
              )
            }
          >
            Liquidate
          </Button>
        </div>
      )}

      {confirm && (
        <m.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          className="flex flex-col gap-3"
        >
          <p className="text-center text-[10px] font-bold uppercase tracking-widest text-zinc-300 px-2">
            {confirm.message}
          </p>
          <div className="flex gap-3">
            <Button
              variant="outline"
              onClick={() => {
                setConfirm(null);
                setSellStage('idle');
              }}
              className="flex-1 h-11"
            >
              Abort
            </Button>
            <Button
              variant="danger"
              onClick={confirm.kind === 'recycle' ? doRecycle : doSell}
              isLoading={sellStage === 'selling'}
              className="flex-[2] h-11"
            >
              Confirm
            </Button>
          </div>
        </m.div>
      )}
    </div>
  );

  return <Modal character={selectedChar} onClose={() => setSelectedChar(null)} actions={actions} />;
};
