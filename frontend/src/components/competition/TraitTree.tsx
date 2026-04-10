import { AgentTrait, TraitInfo } from '@/lib/api/competition';
import { TraitBadge } from './TraitBadge';

interface TraitTreeProps {
  traitTree: TraitInfo[];
  currentLevel: number;
  onTraitClick?: (trait: AgentTrait) => void;
}

const TREE_CHILDREN: Record<string, string[]> = {
  genesis: ['risk_manager', 'trend_follower', 'mean_reversion'],
  risk_manager: ['tail_hedged'],
  trend_follower: ['momentum', 'breakout'],
  mean_reversion: ['range_bound', 'statistical'],
  statistical: ['cointegration', 'kalman_filter'],
};

export function TraitTree({ traitTree, currentLevel, onTraitClick }: TraitTreeProps) {
  const traitMap = new Map(traitTree.map(t => [t.trait, t]));

  const renderNode = (traitId: string, depth = 0) => {
    const info = traitMap.get(traitId as AgentTrait);
    if (!info) return null;

    const children = TREE_CHILDREN[traitId] || [];

    return (
      <div key={traitId} className="flex flex-col items-center">
        <div className="relative">
          <TraitBadge
            trait={traitId as AgentTrait}
            unlocked={info.unlocked}
            size="md"
            onClick={onTraitClick ? () => onTraitClick(traitId as AgentTrait) : undefined}
          />
          {info.unlocked && (
            <div className="absolute -top-1 -right-1 w-3 h-3 bg-green-500 rounded-full border-2 border-gray-900" />
          )}
          {!info.unlocked && (
            <div className="absolute -top-1 -right-1 w-3 h-3 bg-gray-700 rounded-full border-2 border-gray-900 flex items-center justify-center">
              <span className="text-[6px] text-gray-400">{info.required_level}</span>
            </div>
          )}
        </div>

        {children.length > 0 && (
          <>
            <div className="w-px h-4 bg-gray-700" />
            <div className="flex gap-4 relative">
              <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[calc(100%-1rem)] h-px bg-gray-700" />
              {children.map((child) => (
                <div key={child} className="flex flex-col items-center">
                  <div className="w-px h-4 bg-gray-700" />
                  {renderNode(child, depth + 1)}
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    );
  };

  return (
    <div className="flex flex-col items-center p-4 overflow-x-auto">
      <div className="text-xs text-gray-500 uppercase tracking-wider mb-4">
        Trait Tree — Level {currentLevel}
      </div>
      {renderNode('genesis')}
    </div>
  );
}
