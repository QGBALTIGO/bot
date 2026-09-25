import { Heart, LockKeyhole } from 'lucide-react';
import { Button } from '../../components/ui/Button';
import { navigateNative } from '../../native/navigation';
import { useFeatureAction } from './api';

export function CharacterTools({ id, owned }: { id: number; owned: boolean }) {
  return (
    <div className="grid grid-cols-2 gap-2">
      <QuickWish id={id} />
      {owned && (
        <Button
          variant="outline"
          size="sm"
          leftIcon={<LockKeyhole size={13} />}
          onClick={() => navigateNative('collecting', { character_id: id })}
        >
          Cofre e proteção
        </Button>
      )}
    </div>
  );
}
function QuickWish({ id }: { id: number }) {
  const { perform, pending } = useFeatureAction();
  return (
    <Button
      size="sm"
      variant="secondary"
      disabled={pending}
      leftIcon={<Heart size={13} />}
      onClick={() =>
        void perform(
          '/wishes',
          { ids: [id], enabled: true },
          { success: 'Personagem adicionado aos desejos.' },
        )
      }
    >
      Adicionar aos desejos
    </Button>
  );
}
export function WishWork({ animeId }: { animeId: number }) {
  const { perform, pending } = useFeatureAction();
  return (
    <Button
      variant="secondary"
      size="sm"
      disabled={pending}
      leftIcon={<Heart size={13} />}
      onClick={() =>
        void perform(
          `/wishes/work/${animeId}`,
          {},
          { success: 'Personagens que faltam adicionados aos desejos.' },
        )
      }
    >
      Desejar os que faltam
    </Button>
  );
}
