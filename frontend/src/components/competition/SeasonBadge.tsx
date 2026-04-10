import type { Season } from '../../lib/api/competition';

const STATUS_STYLES = {
  active: {
    bg: 'bg-cyan-500/15',
    border: 'border-cyan-500/40',
    text: 'text-cyan-400',
    dot: 'bg-cyan-400',
  },
  ended: {
    bg: 'bg-gray-500/15',
    border: 'border-gray-600/40',
    text: 'text-gray-400',
    dot: 'bg-gray-500',
  },
  upcoming: {
    bg: 'bg-purple-500/15',
    border: 'border-purple-500/40',
    text: 'text-purple-400',
    dot: 'bg-purple-400',
  },
};

interface SeasonBadgeProps {
  season: Season | null;
  compact?: boolean;
}

export function SeasonBadge({ season, compact = false }: SeasonBadgeProps) {
  if (!season) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-gray-800 border border-gray-700 text-gray-500 text-xs">
        No Season
      </span>
    );
  }

  const style = STATUS_STYLES[season.status];

  if (compact) {
    return (
      <span
        className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md border ${style.bg} ${style.border} ${style.text}`}
        title={`Season ${season.number}: ${season.name} (${season.days_remaining}d remaining)`}
      >
        <span className={`w-1.5 h-1.5 rounded-full ${style.dot} ${season.status === 'active' ? 'animate-pulse' : ''}`} />
        <span className="text-xs font-semibold">S{season.number}</span>
        {season.your_rank && (
          <span className="text-xs opacity-75">#{season.your_rank}</span>
        )}
      </span>
    );
  }

  return (
    <span
      className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border ${style.bg} ${style.border}`}
      title={season.name}
    >
      <span className={`w-2 h-2 rounded-full ${style.dot} ${season.status === 'active' ? 'animate-pulse' : ''}`} />
      <span className={`text-sm font-bold ${style.text}`}>
        Season {season.number}
      </span>
      <span className="text-xs text-gray-400">
        {season.days_remaining}d left
      </span>
      {season.your_rank && (
        <span className="text-xs text-gray-400">
          Rank <span className="font-bold text-gray-200">#{season.your_rank}</span>
        </span>
      )}
    </span>
  );
}

interface SeasonCountdownProps {
  endsAt: string;
  className?: string;
}

export function SeasonCountdown({ endsAt, className = '' }: SeasonCountdownProps) {
  const now = new Date();
  const end = new Date(endsAt);
  const diff = end.getTime() - now.getTime();

  if (diff <= 0) {
    return (
      <span className={`text-xs text-gray-500 ${className}`}>
        Season ended
      </span>
    );
  }

  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));

  return (
    <span className={`font-mono text-sm ${className}`}>
      {days > 0 && <>{days}d </>}
      {hours}h {minutes}m
    </span>
  );
}
