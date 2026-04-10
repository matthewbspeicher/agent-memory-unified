import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { agentApi } from '../lib/api/agent';
import { competitionApi } from '../lib/api/competition';
import { AgentCard } from '../components/competition/AgentCard';
import { GlassCard } from '../components/GlassCard';

function RosterCard({ agentName }: { agentName: string }) {
  const navigate = useNavigate();
  const { data: card, isLoading } = useQuery({
    queryKey: ['agent-card', agentName],
    queryFn: () => competitionApi.getAgentCard(agentName),
  });

  if (isLoading) {
    return (
      <div className="w-72 h-80 rounded-xl border-2 border-gray-800 bg-gray-900/30 animate-pulse flex items-center justify-center">
        <span className="text-gray-600 text-sm">Loading {agentName}...</span>
      </div>
    );
  }

  if (!card) {
    return null;
  }

  return (
    <AgentCard 
      card={card} 
      onClick={() => navigate(`/arena/competitors/${agentName}`)} 
    />
  );
}

export default function Roster() {
  const { data: agents, isLoading } = useQuery({
    queryKey: ['agents'],
    queryFn: () => agentApi.listAgents(),
  });

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Agent Roster</h1>
          <p className="text-gray-400 mt-2">
            Manage your fleet of autonomous trading agents. Equip traits and monitor achievements.
          </p>
        </div>
      </div>

      <GlassCard className="p-6">
        {isLoading ? (
          <div className="text-center py-12 text-gray-500">Loading fleet...</div>
        ) : !agents || agents.length === 0 ? (
          <div className="text-center py-12 text-gray-500">No agents registered in the fleet.</div>
        ) : (
          <div className="flex flex-wrap gap-6 justify-center sm:justify-start">
            {agents.map((agent) => (
              <RosterCard key={agent.name} agentName={agent.name} />
            ))}
          </div>
        )}
      </GlassCard>
    </div>
  );
}
