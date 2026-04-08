// frontend/src/components/competition/MetaLearnerPanel.tsx
export function MetaLearnerPanel() {
  return (
    <div className="p-3 bg-gray-800/50 rounded border border-gray-700">
      <h3 className="text-sm font-semibold text-gray-400 mb-2">Meta-Learner</h3>
      <p className="text-xs text-gray-500">
        Coming in Sprint 7 — XGBoost meta-learner will show ensemble weights and feature importance here.
      </p>
    </div>
  );
}
