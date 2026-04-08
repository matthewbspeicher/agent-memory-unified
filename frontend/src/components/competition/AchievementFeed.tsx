// frontend/src/components/competition/AchievementFeed.tsx
import { useAchievementFeed } from '../../hooks/useAchievementFeed';
import { AchievementBadge } from './AchievementBadge';

export function AchievementFeed() {
  const { events, isConnected } = useAchievementFeed();

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-400">Recent Activity</h3>
        <span 
          className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}
          title={isConnected ? 'Connected' : 'Disconnected'} 
        />
      </div>
      {events.length === 0 && (
        <p className="text-xs text-gray-600">No recent activity</p>
      )}
      {events.map((event, i) => (
        <div key={i} className="flex items-center gap-2 text-xs">
          <AchievementBadge type={event.type} earnedAt={event.earned_at} />
          <span className="text-gray-500">{event.competitor}</span>
        </div>
      ))}
    </div>
  );
}
