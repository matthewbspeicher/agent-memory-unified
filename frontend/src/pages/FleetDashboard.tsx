import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useFleet, useSeasons, type CardRarity } from '../lib/api/competition';
import { AgentCard } from '../components/competition/AgentCard';
import { MissionPanel } from '../components/competition/MissionPanel';
import { SeasonBadge } from '../components/competition/SeasonBadge';
import { GlassCard } from '../components/GlassCard';

type SortKey = 'level' | 'elo' | 'xp';
type SortDir = 'asc' | 'desc';

const RARITY_OPTIONS: CardRarity[] = ['legendary', 'epic', 'rare', 'uncommon', 'common'];
const RARITY_LABELS: Record<CardRarity, string> = {
  legendary: 'Legendary',
  epic: 'Epic',
  rare: 'Rare',
  uncommon: 'Uncommon',
  common: 'Common',
};

export default function FleetDashboard() {
  const navigate = useNavigate();
  const { data: fleet, isLoading, error } = useFleet('BTC');
  const { data: seasonsData } = useSeasons();

  const [searchQuery, setSearchQuery] = useState('');
  const [rarityFilter, setRarityFilter] = useState<CardRarity | 'all'>('all');
  const [sortKey, setSortKey] = useState<SortKey>('elo');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [showSidePanel, setShowSidePanel] = useState(true);

  const currentSeason = seasonsData?.current ?? null;

  const filteredCards = useMemo(() => {
    if (!fleet?.cards) return [];

    let cards = [...fleet.cards];

    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      cards = cards.filter(c => c.name.toLowerCase().includes(query));
    }

    if (rarityFilter !== 'all') {
      cards = cards.filter(c => c.rarity === rarityFilter);
    }

    cards.sort((a, b) => {
      let aVal: number, bVal: number;
      switch (sortKey) {
        case 'level':
          aVal = a.level;
          bVal = b.level;
          break;
        case 'elo':
          aVal = a.elo;
          bVal = b.elo;
          break;
        case 'xp':
          aVal = a.stats.total_xp;
          bVal = b.stats.total_xp;
          break;
        default:
          aVal = a.elo;
          bVal = b.elo;
      }
      return sortDir === 'desc' ? bVal - aVal : aVal - bVal;
    });

    return cards;
  }, [fleet?.cards, searchQuery, rarityFilter, sortKey, sortDir]);

  const handleCardClick = (agentId: string) => {
    setSelectedAgentId(agentId);
    if (!showSidePanel) setShowSidePanel(true);
  };

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center">
          <p className="text-rose-400 text-lg font-bold mb-2">Fleet Data Unavailable</p>
          <p className="text-gray-500 text-sm">Unable to load fleet data. The backend may be offline.</p>
        </div>
      </div>
    );
  }

  const stats = fleet?.stats;
  const selectedAgent = filteredCards.find(c => c.competitor_id === selectedAgentId);

  return (
    <div className="min-h-screen pb-20">
      <header className="mb-8">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-4xl font-black tracking-tight mb-2 bg-clip-text text-transparent bg-gradient-to-r from-cyan-400 via-blue-500 to-purple-500">
              Fleet Command
            </h1>
            <p className="text-gray-400 text-sm font-mono uppercase tracking-widest">
              Agent Management // Trading Competition Hub
            </p>
          </div>
          <div className="flex items-center gap-4">
            <SeasonBadge season={currentSeason} />
            {stats && stats.mission_claimable > 0 && (
              <span className="px-3 py-1.5 rounded-lg bg-emerald-500/20 border border-emerald-500/40 text-emerald-400 text-xs font-bold animate-pulse">
                {stats.mission_claimable} missions claimable
              </span>
            )}
          </div>
        </div>
      </header>

      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-3 mb-8">
          <StatCard label="Total Agents" value={stats.total_agents} icon="🤖" color="cyan" />
          <StatCard label="Avg Level" value={stats.avg_level.toFixed(1)} icon="📊" color="violet" />
          <StatCard label="Total XP" value={formatNumber(stats.total_xp)} icon="⚡" color="amber" />
          <StatCard label="Total Matches" value={formatNumber(stats.total_matches)} icon="⚔️" color="rose" />
          <StatCard label="Avg ELO" value={stats.avg_elo.toFixed(0)} icon="📈" color="cyan" />
          <StatCard label="Legendaries" value={stats.legendary_count} icon="🌟" color="amber" />
          <StatCard label="Claimable" value={stats.mission_claimable} icon="🎁" color="emerald" />
        </div>
      )}

      <div className="flex gap-6">
        <div className={`flex-1 min-w-0 ${showSidePanel && selectedAgentId ? 'lg:max-w-[calc(100%-380px)]' : ''}`}>
          <div className="flex flex-wrap items-center gap-3 mb-6 p-4 rounded-xl bg-gray-900/50 border border-gray-800">
            <div className="relative flex-1 min-w-[200px]">
              <input
                type="text"
                placeholder="Search agents..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-4 py-2 rounded-lg bg-gray-800 border border-gray-700 text-gray-200 text-sm placeholder:text-gray-500 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/20"
              />
              <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>

            <select
              value={rarityFilter}
              onChange={(e) => setRarityFilter(e.target.value as CardRarity | 'all')}
              className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-gray-300 text-sm focus:outline-none focus:border-cyan-500/50"
            >
              <option value="all">All Rarities</option>
              {RARITY_OPTIONS.map(r => (
                <option key={r} value={r}>{RARITY_LABELS[r]}</option>
              ))}
            </select>

            <select
              value={sortKey}
              onChange={(e) => setSortKey(e.target.value as SortKey)}
              className="px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-gray-300 text-sm focus:outline-none focus:border-cyan-500/50"
            >
              <option value="elo">Sort by ELO</option>
              <option value="level">Sort by Level</option>
              <option value="xp">Sort by XP</option>
            </select>

            <button
              onClick={() => setSortDir(d => d === 'desc' ? 'asc' : 'desc')}
              className="p-2 rounded-lg bg-gray-800 border border-gray-700 text-gray-300 hover:border-cyan-500/50 transition-colors"
              title={sortDir === 'desc' ? 'Descending' : 'Ascending'}
            >
              <svg className={`w-4 h-4 transition-transform ${sortDir === 'asc' ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            <button
              onClick={() => setShowSidePanel(p => !p)}
              className={`p-2 rounded-lg border transition-colors ${
                showSidePanel
                  ? 'bg-cyan-500/20 border-cyan-500/40 text-cyan-400'
                  : 'bg-gray-800 border-gray-700 text-gray-400 hover:border-cyan-500/50'
              }`}
              title="Toggle Missions Panel"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
            </button>
          </div>

          <div className="flex items-center justify-between mb-4">
            <span className="text-xs text-gray-500 font-mono uppercase tracking-wider">
              {filteredCards.length} agent{filteredCards.length !== 1 ? 's' : ''} in fleet
            </span>
            {rarityFilter !== 'all' && (
              <button
                onClick={() => setRarityFilter('all')}
                className="text-xs text-cyan-400 hover:text-cyan-300 flex items-center gap-1"
              >
                Clear filter
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>

          {isLoading ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {[...Array(6)].map((_, i) => (
                <div
                  key={i}
                  className="w-72 h-80 rounded-xl border-2 border-gray-800 bg-gray-900/30 animate-pulse"
                />
              ))}
            </div>
          ) : filteredCards.length === 0 ? (
            <div className="text-center py-16 rounded-xl bg-gray-900/30 border border-gray-800">
              <p className="text-gray-500 text-lg mb-2">No agents found</p>
              <p className="text-gray-600 text-sm">
                {searchQuery ? 'Try adjusting your search query' : 'No agents match the selected filters'}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {filteredCards.map((card) => (
                <div
                  key={card.competitor_id}
                  className={`transition-all duration-200 ${
                    selectedAgentId === card.competitor_id
                      ? 'ring-2 ring-cyan-500/50 rounded-xl'
                      : ''
                  }`}
                >
                  <AgentCard
                    card={card}
                    onClick={() => handleCardClick(card.competitor_id)}
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {showSidePanel && selectedAgentId && (
          <aside className="hidden lg:block w-[360px] flex-shrink-0">
            <div className="sticky top-6">
              {selectedAgent && (
                <div className="mb-4 p-4 rounded-xl bg-gray-900/50 border border-gray-800">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm text-gray-400">Selected Agent</p>
                      <p className="text-lg font-bold text-white truncate">{selectedAgent.name}</p>
                    </div>
                    <button
                      onClick={() => navigate(`/arena/competitors/${selectedAgentId}`)}
                      className="text-xs text-cyan-400 hover:text-cyan-300 px-3 py-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/20"
                    >
                      View Profile
                    </button>
                  </div>
                  <div className="flex gap-4 mt-3 text-xs">
                    <span className="text-gray-400">ELO: <span className="text-cyan-400 font-bold">{selectedAgent.elo}</span></span>
                    <span className="text-gray-400">Level: <span className="text-violet-400 font-bold">{selectedAgent.level}</span></span>
                    <span className="text-gray-400">Tier: <span className="text-amber-400 font-bold capitalize">{selectedAgent.tier}</span></span>
                  </div>
                </div>
              )}

              <GlassCard variant="cyan" className="overflow-hidden">
                <div className="-m-6">
                  <MissionPanel competitorId={selectedAgentId} asset="BTC" />
                </div>
              </GlassCard>
            </div>
          </aside>
        )}
      </div>

      {showSidePanel && selectedAgentId && (
        <div className="lg:hidden fixed bottom-0 left-0 right-0 z-40 p-4 bg-gray-950/95 backdrop-blur-xl border-t border-gray-800">
          <div className="flex items-center justify-between mb-3">
            <div>
              <p className="text-xs text-gray-500">Selected Agent</p>
              <p className="text-base font-bold text-white">{selectedAgent?.name}</p>
            </div>
            <button
              onClick={() => setSelectedAgentId(null)}
              className="p-2 rounded-lg bg-gray-800 text-gray-400"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div className="max-h-[40vh] overflow-y-auto">
            <MissionPanel competitorId={selectedAgentId} asset="BTC" />
          </div>
        </div>
      )}
    </div>
  );
}

interface StatCardProps {
  label: string;
  value: string | number;
  icon: string;
  color: 'cyan' | 'violet' | 'amber' | 'rose' | 'emerald';
}

function StatCard({ label, value, icon, color }: StatCardProps) {
  const colorClasses = {
    cyan: 'border-cyan-500/20 bg-cyan-500/5',
    violet: 'border-violet-500/20 bg-violet-500/5',
    amber: 'border-amber-500/20 bg-amber-500/5',
    rose: 'border-rose-500/20 bg-rose-500/5',
    emerald: 'border-emerald-500/20 bg-emerald-500/5',
  };

  return (
    <div className={`p-3 rounded-lg border ${colorClasses[color]}`}>
      <div className="text-xs text-gray-500 uppercase tracking-wider mb-1 flex items-center gap-1.5">
        <span>{icon}</span>
        {label}
      </div>
      <div className="text-xl font-black font-mono text-white">{value}</div>
    </div>
  );
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}
