// frontend/src/components/competition/MetaLearnerPanel.tsx
import { useMetaLearnerStatus } from '../../lib/api/competition';

export function MetaLearnerPanel() {
  const { data, isLoading } = useMetaLearnerStatus();

  if (isLoading) {
    return (
      <div className="p-3 bg-gray-800/50 rounded border border-gray-700 animate-pulse">
        <div className="h-4 bg-gray-700 rounded w-1/2 mb-2" />
        <div className="h-3 bg-gray-700 rounded w-3/4" />
      </div>
    );
  }

  const mode = data?.mode || 'baseline';
  const importance = data?.feature_importance || {};
  const topFeatures = Object.entries(importance)
    .sort(([, a], [, b]) => (b as number) - (a as number))
    .slice(0, 5);

  return (
    <div className="p-3 bg-gray-800/50 rounded border border-gray-700 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-400">Meta-Learner</h3>
        <span className={`text-xs px-2 py-0.5 rounded ${
          mode === 'meta' ? 'bg-cyan-500/20 text-cyan-400' : 'bg-gray-600/20 text-gray-500'
        }`}>
          {mode === 'meta' ? 'XGBoost Active' : 'Linear Baseline'}
        </span>
      </div>
      
      {!data?.has_model ? (
        <p className="text-xs text-gray-500">
          Model training after 30 days of match data.
        </p>
      ) : topFeatures.length > 0 ? (
        <div className="space-y-1">
          <p className="text-xs text-gray-500 mb-2">Top Features:</p>
          {topFeatures.map(([feature, importance]) => (
            <div key={feature} className="flex items-center gap-2 text-xs">
              <div className="flex-1 truncate text-gray-400">
                {feature.replace(/_/g, ' ')}
              </div>
              <div className="w-16 h-1 bg-gray-700 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-cyan-500 rounded-full"
                  style={{ width: `${(importance as number) * 100}%` }}
                />
              </div>
              <span className="text-gray-500 w-8 text-right">
                {((importance as number) * 100).toFixed(0)}%
              </span>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-gray-500">No feature importance data yet.</p>
      )}
    </div>
  );
}
