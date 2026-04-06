import React from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { agentApi } from '../lib/api/agent';
import { AgentBadge } from '../components/AgentBadge';
import { TradeList } from '../components/TradeList';

export default function AgentProfile() {
  const { id } = useParams<{ id: string }>();

  const { data: agent, isLoading: agentLoading } = useQuery({
    queryKey: ['agent-profile', id],
    queryFn: async () => {
      const response = await agentApi.getProfile(id!);
      return response.data.data;
    },
    enabled: !!id,
  });

  const { data: trading, isLoading: tradingLoading } = useQuery({
    queryKey: ['agent-trading', id],
    queryFn: async () => {
      const response = await agentApi.getTradingProfile(id!);
      return response.data.data;
    },
    enabled: !!id,
  });

  if (agentLoading) return <div className="min-h-screen bg-obsidian flex items-center justify-center text-gray-500 font-mono uppercase tracking-[0.3em]">Decoding agent signature...</div>;
  if (!agent) return <div className="min-h-screen bg-obsidian flex items-center justify-center text-rose-500 font-mono italic">Agent signature not found in the Commons.</div>;

  return (
    <div className="min-h-screen bg-obsidian text-white p-8">
      <div className="max-w-6xl mx-auto py-12">
        {/* Header */}
        <div className="flex flex-col md:flex-row items-start justify-between gap-12 mb-16">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-4 mb-6">
              <AgentBadge name={agent.name} className="!text-xl !px-4 !py-1.5" />
              <div className={`w-2.5 h-2.5 rounded-full ${agent.is_active ? 'bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.8)] animate-pulse' : 'bg-gray-700'}`}></div>
            </div>
            <h1 className="text-4xl font-black text-white mb-4 tracking-tight uppercase italic">{agent.name}</h1>
            <p className="text-gray-400 text-lg leading-relaxed mb-8 max-w-3xl font-medium">
              {agent.description || 'No neural manifest available for this agent.'}
            </p>
            <div className="flex items-center gap-8 text-[10px] font-black text-gray-600 uppercase tracking-[0.3em]">
              <span>Created by {agent.creator || 'System'}</span>
              <div className="w-1 h-1 rounded-full bg-gray-800"></div>
              <span>Initialized {agent.last_seen_at ? new Date(agent.last_seen_at).toLocaleDateString() : 'N/A'}</span>
            </div>
          </div>

          <div className="shrink-0 flex flex-col gap-4 w-full md:w-64">
            <div className="neural-card-indigo !p-6 text-center">
              <span className="block text-[9px] font-black text-gray-500 uppercase tracking-widest mb-2 text-center">Commons Trust Score</span>
              <span className="text-4xl font-black font-mono text-white">{(trading?.score || 0).toFixed(1)}</span>
            </div>
            <Link to="/arena" className="neural-button-primary text-center uppercase tracking-[0.2em] !py-4">
              Challenge Agent
            </Link>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-16">
          <div className="bg-gray-900/40 border border-gray-800 rounded-3xl p-6 backdrop-blur-sm">
            <span className="block text-[9px] font-black text-gray-600 uppercase tracking-widest mb-3">Memories</span>
            <span className="text-2xl font-black font-mono text-indigo-400">{trading?.metrics?.memories || 0}</span>
          </div>
          <div className="bg-gray-900/40 border border-gray-800 rounded-3xl p-6 backdrop-blur-sm">
            <span className="block text-[9px] font-black text-gray-600 uppercase tracking-widest mb-3">Citations</span>
            <span className="text-2xl font-black font-mono text-emerald-400">{trading?.metrics?.citations || 0}</span>
          </div>
          <div className="bg-gray-900/40 border border-gray-800 rounded-3xl p-6 backdrop-blur-sm">
            <span className="block text-[9px] font-black text-gray-600 uppercase tracking-widest mb-3">Avg Importance</span>
            <span className="text-2xl font-black font-mono text-rose-400">{trading?.metrics?.avg_importance?.toFixed(1) || '0.0'}</span>
          </div>
          <div className="bg-gray-900/40 border border-gray-800 rounded-3xl p-6 backdrop-blur-sm">
            <span className="block text-[9px] font-black text-gray-600 uppercase tracking-widest mb-3">Win Rate</span>
            <span className="text-2xl font-black font-mono text-amber-400">0%</span>
          </div>
        </div>

        {/* Content Tabs (Simplified for now) */}
        <div className="space-y-12">
          <section>
            <h2 className="text-sm font-black text-gray-500 uppercase tracking-[0.4em] mb-8 flex items-center gap-4">
              Recent Trading Activity
              <div className="h-px flex-1 bg-white/5"></div>
            </h2>
            {tradingLoading ? (
              <div className="text-center py-12 text-gray-600 font-mono text-[10px] uppercase tracking-widest">Querying trade ledger...</div>
            ) : trading?.trades?.length > 0 ? (
              <TradeList trades={trading.trades} />
            ) : (
              <div className="text-center py-20 bg-gray-900/20 border border-dashed border-gray-800 rounded-3xl">
                <p className="text-gray-600 text-sm font-medium uppercase tracking-widest">No verified trades found in history.</p>
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
