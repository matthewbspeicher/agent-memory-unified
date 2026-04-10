// frontend/src/components/competition/XpBar.tsx

export function XpBar({
  xp,
  xpToNext,
  level,
  compact = false,
}: {
  xp: number;
  xpToNext: number;
  level: number;
  compact?: boolean;
}) {
  const progress = Math.min(1, (xp % xpToNext) / xpToNext);
  const width = compact ? 'w-16' : 'w-24';

  return (
    <div className={`flex items-center gap-2 ${compact ? '' : 'flex-col'}`}>
      <div
        className={`h-2 ${width} bg-gray-700 rounded-full overflow-hidden`}
        title={`${xp} XP — ${xpToNext} to Level ${level + 1}`}
      >
        <div
          className="h-full bg-gradient-to-r from-blue-500 to-cyan-400 rounded-full transition-all duration-500"
          style={{ width: `${progress * 100}%` }}
        />
      </div>
      {!compact && (
        <span className="text-xs text-gray-400">
          {xpToNext} XP to Lv.{level + 1}
        </span>
      )}
    </div>
  );
}
