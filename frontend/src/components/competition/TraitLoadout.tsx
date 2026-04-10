import { AgentTrait, TraitLoadout as TraitLoadoutType } from '@/lib/api/competition';
import { TraitBadge } from './TraitBadge';

interface TraitLoadoutProps {
  loadout: TraitLoadoutType;
  unlockedTraits: AgentTrait[];
  onEquip: (trait: AgentTrait) => void;
  onUnequip: (trait: AgentTrait) => void;
  loading?: boolean;
}

const SLOT_LABELS: Record<string, string> = {
  primary: 'Primary',
  secondary: 'Secondary',
  tertiary: 'Tertiary',
};

export function TraitLoadout({ loadout, unlockedTraits, onEquip, onUnequip, loading }: TraitLoadoutProps) {
  const slots: Array<{ key: 'primary' | 'secondary' | 'tertiary'; trait: AgentTrait | null }> = [
    { key: 'primary', trait: loadout.primary },
    { key: 'secondary', trait: loadout.secondary },
    { key: 'tertiary', trait: loadout.tertiary },
  ];

  const filledSlots = slots.filter(s => s.trait !== null).length;
  const availableTraits = unlockedTraits.filter(
    t => t !== loadout.primary && t !== loadout.secondary && t !== loadout.tertiary
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
          Active Loadout
        </h3>
        <span className="text-xs text-gray-500">
          {filledSlots}/3 slots filled
        </span>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {slots.map(({ key, trait }) => (
          <div
            key={key}
            className={`
              flex flex-col items-center p-3 rounded-lg border transition-all
              ${trait
                ? 'border-cyan-700/50 bg-cyan-900/10'
                : 'border-gray-800 bg-gray-900/30 border-dashed'
              }
            `}
          >
            <span className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">
              {SLOT_LABELS[key]}
            </span>
            {trait ? (
              <div className="flex flex-col items-center gap-2">
                <TraitBadge trait={trait} unlocked size="md" />
                <button
                  type="button"
                  onClick={() => onUnequip(trait)}
                  disabled={loading}
                  className="text-[10px] text-red-400 hover:text-red-300 transition-colors disabled:opacity-50"
                >
                  Unequip
                </button>
              </div>
            ) : (
              <div className="text-gray-700 text-sm">Empty</div>
            )}
          </div>
        ))}
      </div>

      {availableTraits.length > 0 && (
        <div className="pt-3 border-t border-gray-800">
          <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">
            Available Traits
          </div>
          <div className="flex flex-wrap gap-2">
            {availableTraits.map(trait => (
              <TraitBadge
                key={trait}
                trait={trait}
                unlocked
                size="sm"
                onClick={() => filledSlots < 3 ? onEquip(trait) : undefined}
              />
            ))}
          </div>
          {filledSlots >= 3 && (
            <p className="text-xs text-yellow-500 mt-2">
              Unequip a trait first to make room
            </p>
          )}
        </div>
      )}
    </div>
  );
}
