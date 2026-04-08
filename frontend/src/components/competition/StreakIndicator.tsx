// frontend/src/components/competition/StreakIndicator.tsx
export function StreakIndicator({ streak }: { streak: number }) {
  if (streak >= 5) {
    return <span title={`${streak} win streak`}>{'🔥'} {streak}</span>;
  }
  if (streak <= -3) {
    return <span title={`${Math.abs(streak)} loss streak`}>{'❄️'} {streak}</span>;
  }
  if (streak === 0) {
    return <span className="text-gray-500">—</span>;
  }
  return <span>{streak}</span>;
}
