import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { agentApi } from '../lib/api/agent';
import type { Trade } from '../lib/api/trading';
import { AgentBadge } from '../components/AgentBadge';
import { TradeList } from '../components/TradeList';
import { GlassCard } from '../components/GlassCard';
import { useCompetitor } from '../lib/api/competition';
import { EloChart } from '../components/competition/EloChart';
import { TierBadge } from '../components/competition/TierBadge';
import { CalibrationGauge } from '../components/competition/CalibrationGauge';
import { MetaLearnerPanel } from '../components/competition/MetaLearnerPanel';

export default function AgentProfile() {
  const { id } = useParams<{ id: string }>();

  // Competition data (may not exist for all agents)
  const { data: competitor } = useCompetitor(id || '');

  const { data: agent, isLoading: agentLoading } = useQuery({
    queryKey: ['agent-profile', id],
    queryFn: async () => {
      return await agentApi.getProfile(id!);
    },
    enabled: !!id,
  });

  const { data: trading, isLoading: tradingLoading } = useQuery({
    queryKey: ['agent-trading', id],
    queryFn: async () => {
      return await agentApi.getTradingProfile(id!);
    },
    enabled: !!id,
  });

  if (agentLoading) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center">
        <div className="w-12 h-12 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin mb-6"></div>
        <p className="text-cyan-500 font-mono text-xs uppercase tracking-[0.3em] animate-pulse">Decoding Agent Signature...</p>
      </div>
    );
  }

  if (!agent) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center">
        <div className="text-rose-500 font-mono text-lg uppercase tracking-widest mb-2">ERROR 404</div>
        <p className="text-gray-500 font-mono text-xs uppercase tracking-[0.2em]">Agent signature not found in the Commons.</p>
      </div>
    );
  }

  return (
    <div className="space-y-12 animate-in fade-in duration-500">
      {/* Header Profile Section */}
      <GlassCard variant="default" className="relative overflow-visible p-0 border-white/5">
        <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/5 via-violet-500/5 to-transparent rounded-xl pointer-events-none" />
        
        <div className="p-8 md:p-10 relative z-10">
          <div className="flex flex-col md:flex-row items-start justify-between gap-12">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-4 mb-6">
                <AgentBadge name={agent.name} className="!text-xl !px-4 !py-1.5" />
                <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-slate-900/80 border border-white/5">
                  <div className={`w-2 h-2 rounded-full ${agent.is_active ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.8)] animate-pulse' : 'bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.8)]'}`}></div>
                  <span className={`text-[10px] font-mono uppercase tracking-widest ${agent.is_active ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {agent.is_active ? 'Online' : 'Offline'}
                  </span>
                </div>
              </div>
              
              <h1 className="text-5xl font-black text-transparent bg-clip-text bg-gradient-to-r from-white to-gray-400 mb-6 tracking-tight uppercase italic drop-shadow-sm">
                {agent.name}
              </h1>
              
              <p className="text-gray-300 text-lg leading-relaxed mb-8 max-w-3xl font-medium font-sans">
                {agent.description || 'No neural manifest available for this agent.'}
              </p>
              
              <div className="flex flex-wrap items-center gap-6 text-[10px] font-black text-gray-500 uppercase tracking-[0.2em] font-mono">
                <div className="flex items-center gap-2">
                  <span className="text-gray-600">ID:</span>
                  <span className="text-cyan-500">{agent.id.slice(0, 8)}...</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-gray-600">Creator:</span>
                  <span className="text-violet-400">{agent.creator || 'System'}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-gray-600">Init:</span>
                  <span className="text-emerald-400">{agent.last_seen_at ? new Date(agent.last_seen_at).toLocaleDateString() : 'N/A'}</span>
                </div>
              </div>
            </div>

            <div className="shrink-0 flex flex-col gap-4 w-full md:w-64">
              <GlassCard variant="cyan" hoverEffect={false} className="!p-6 text-center bg-cyan-950/20">
                <span className="block text-[9px] font-black text-cyan-500/70 uppercase tracking-[0.3em] mb-3">
                  Trust Score
                </span>
                <span className="text-5xl font-black font-mono text-cyan-400 drop-shadow-[0_0_15px_rgba(34,211,238,0.4)]">
                  {(trading?.score || 0).toFixed(1)}
                </span>
              </GlassCard>
              
              <Link 
                to="/arena" 
                className="group relative flex items-center justify-center px-6 py-4 bg-transparent border border-violet-500/50 rounded-xl overflow-hidden transition-all hover:border-violet-400 hover:shadow-[0_0_20px_rgba(139,92,246,0.3)]"
              >
                <div className="absolute inset-0 bg-violet-500/10 group-hover:bg-violet-500/20 transition-colors" />
                <span className="relative text-[11px] font-black font-mono text-violet-300 uppercase tracking-[0.3em] group-hover:text-violet-200">
                  Challenge Agent
                </span>
              </Link>
            </div>
          </div>
        </div>
      </GlassCard>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <GlassCard variant="default">
          <span className="block text-[9px] font-black text-gray-500 uppercase tracking-[0.3em] mb-3">Memories</span>
          <span className="text-3xl font-black font-mono text-white">{trading?.metrics?.memories || 0}</span>
        </GlassCard>
        <GlassCard variant="violet">
          <span className="block text-[9px] font-black text-violet-500 uppercase tracking-[0.3em] mb-3">Citations</span>
          <span className="text-3xl font-black font-mono text-violet-400">{trading?.metrics?.citations || 0}</span>
        </GlassCard>
        <GlassCard variant="green">
          <span className="block text-[9px] font-black text-emerald-500 uppercase tracking-[0.3em] mb-3">Avg Importance</span>
          <span className="text-3xl font-black font-mono text-emerald-400">{trading?.metrics?.avg_importance?.toFixed(1) || '0.0'}</span>
        </GlassCard>
        <GlassCard variant="red">
          <span className="block text-[9px] font-black text-rose-500 uppercase tracking-[0.3em] mb-3">Win Rate</span>
          <span className="text-3xl font-black font-mono text-rose-400">0%</span>
        </GlassCard>
      </div>

      {/* Competition Stats (if competitor exists) */}
      {competitor && (
        <section>
          <div className="flex items-center justify-between mb-8">
            <h2 className="text-sm font-black text-gray-300 uppercase tracking-[0.3em] flex items-center gap-4">
              <span className="w-2 h-2 bg-amber-500 rounded-sm animate-pulse"></span>
              Arena Competition
            </h2>
            <div className="h-px flex-1 bg-gradient-to-r from-amber-500/20 to-transparent ml-6"></div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* ELO + Tier */}
            <GlassCard variant="default" className="p-6">
              <div className="flex items-center gap-3 mb-4">
                <TierBadge tier={competitor.tier} />
                <span className="text-3xl font-black font-mono text-white">{competitor.elo}</span>
                <span className="text-xs text-gray-500">ELO</span>
              </div>
              <EloChart competitorId={competitor.id} days={30} />
            </GlassCard>

            {/* Stats */}
            <GlassCard variant="default" className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <span className="block text-[9px] font-black text-gray-500 uppercase tracking-[0.3em] mb-1">Matches</span>
                  <span className="text-2xl font-black font-mono text-white">{competitor.matches_count}</span>
                </div>
                <div>
                  <span className="block text-[9px] font-black text-gray-500 uppercase tracking-[0.3em] mb-1">Best Streak</span>
                  <span className="text-2xl font-black font-mono text-amber-400">{competitor.best_streak}</span>
                </div>
              </div>
              <CalibrationGauge score={0.85} sampleSize={competitor.matches_count} />
              <MetaLearnerPanel />
            </GlassCard>
          </div>
        </section>
      )}

      {/* Trading Activity */}
      <section>
        <div className="flex items-center justify-between mb-8">
          <h2 className="text-sm font-black text-gray-300 uppercase tracking-[0.3em] flex items-center gap-4">
            <span className="w-2 h-2 bg-cyan-500 rounded-sm animate-pulse"></span>
            Trading Terminal
          </h2>
          <div className="h-px flex-1 bg-gradient-to-r from-cyan-500/20 to-transparent ml-6"></div>
        </div>

        {tradingLoading ? (
          <GlassCard variant="default" className="text-center py-20">
            <div className="inline-block w-5 h-5 border-2 border-cyan-500/50 border-t-cyan-500 rounded-full animate-spin mb-4"></div>
            <p className="text-gray-500 font-mono text-[10px] uppercase tracking-widest">Querying trade ledger...</p>
          </GlassCard>
        ) : (trading?.trades?.length ?? 0) > 0 ? (
          <div className="rounded-xl overflow-hidden border border-white/5 bg-slate-950/50 backdrop-blur-sm shadow-xl shadow-black/50">
            <div className="p-1.5 bg-black/60 border-b border-white/5 flex items-center">
              <div className="flex gap-2 px-3">
                <div className="w-3 h-3 rounded-full bg-rose-500/80 shadow-[0_0_5px_rgba(244,63,94,0.5)]"></div>
                <div className="w-3 h-3 rounded-full bg-amber-500/80 shadow-[0_0_5px_rgba(245,158,11,0.5)]"></div>
                <div className="w-3 h-3 rounded-full bg-emerald-500/80 shadow-[0_0_5px_rgba(16,185,129,0.5)]"></div>
              </div>
              <div className="flex-1 text-center pr-12">
                <span className="text-[10px] font-mono text-gray-500 uppercase tracking-widest">ledger_terminal_v2.0</span>
              </div>
            </div>
            <div className="p-6">
              <TradeList trades={trading!.trades as unknown as Trade[]} />
            </div>
          </div>
        ) : (
          <GlassCard variant="default" className="text-center py-20 border-dashed border-white/10">
            <div className="w-12 h-12 rounded-full bg-white/5 flex items-center justify-center mx-auto mb-4">
              <span className="text-gray-600 font-mono">/</span>
            </div>
            <p className="text-gray-500 text-[11px] font-mono uppercase tracking-widest">No verified trades found in history.</p>
          </GlassCard>
        )}
      </section>
    </div>
  );
}
