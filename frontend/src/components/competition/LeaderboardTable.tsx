// frontend/src/components/competition/LeaderboardTable.tsx
import { useState, useEffect } from 'react';
import type { Competitor, CompetitorType } from '../../lib/api/competition';
import { TierBadge } from './TierBadge';
import { StreakIndicator } from './StreakIndicator';
import { CompetitorCard } from './CompetitorCard';

interface LeaderboardTableProps {
  competitors: Competitor[];
  isLoading: boolean;
  onRowClick?: (id: string) => void;
}

function LoadingSkeleton() {
  return (
    <div className="animate-pulse">
      {Array.from({ length: 10 }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 p-3 border-b border-gray-700">
          <div className="w-6 h-4 bg-gray-700 rounded" />
          <div className="w-12 h-5 bg-gray-700 rounded" />
          <div className="flex-1 h-4 bg-gray-700 rounded" />
          <div className="w-14 h-4 bg-gray-700 rounded" />
          <div className="w-10 h-4 bg-gray-700 rounded" />
        </div>
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="text-center py-12 text-gray-500">
      <p className="text-lg mb-2">No competitors yet</p>
      <p className="text-sm">The arena awaits.</p>
    </div>
  );
}

export function LeaderboardTable({ competitors, isLoading, onRowClick }: LeaderboardTableProps) {
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);

  useEffect(() => {
    const handler = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener('resize', handler);
    return () => window.removeEventListener('resize', handler);
  }, []);

  if (isLoading) return <LoadingSkeleton />;
  if (!competitors.length) return <EmptyState />;

  if (isMobile) {
    return (
      <div>
        {competitors.map((c, i) => (
          <div key={c.id} onClick={() => onRowClick?.(c.id)} className="cursor-pointer">
            <CompetitorCard competitor={c} rank={i + 1} />
          </div>
        ))}
      </div>
    );
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-gray-500 border-b border-gray-700">
          <th className="py-2 px-2 text-left w-8">#</th>
          <th className="py-2 px-2 text-left w-16">Tier</th>
          <th className="py-2 px-2 text-left">Name</th>
          <th className="py-2 px-2 text-left w-14">Type</th>
          <th className="py-2 px-2 text-right w-16">ELO</th>
          <th className="py-2 px-2 text-right w-16">Streak</th>
          <th className="py-2 px-2 text-right w-16">Matches</th>
        </tr>
      </thead>
      <tbody>
        {competitors.map((c, i) => (
          <tr
            key={c.id}
            className="border-b border-gray-800 hover:bg-gray-800/50 cursor-pointer"
            onClick={() => onRowClick?.(c.id)}
          >
            <td className="py-2 px-2 text-gray-500">{i + 1}</td>
            <td className="py-2 px-2"><TierBadge tier={c.tier} /></td>
            <td className="py-2 px-2 font-medium">{c.name}</td>
            <td className="py-2 px-2 text-gray-500 text-xs">{c.type}</td>
            <td className="py-2 px-2 text-right font-mono font-bold">{c.elo}</td>
            <td className="py-2 px-2 text-right"><StreakIndicator streak={c.streak} /></td>
            <td className="py-2 px-2 text-right text-gray-500">{c.matches_count}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
