import { MissionControlStatus } from '../../../lib/api/missionControl';
import { GlassCard } from '../../../components/GlassCard';
import { Activity } from 'lucide-react';

interface Props {
  data: MissionControlStatus | undefined;
  onExpand: () => void;
}

export function AgentActivityPanel({ data, onExpand }: Props) {
  const events = data?.activity ?? [];

  return (
    <GlassCard
      variant="violet"
      className="p-4 cursor-pointer hover:ring-2 hover:ring-violet-500/50 transition"
    >
      <button onClick={onExpand} className="w-full text-left">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-violet-400" />
            <h3 className="font-mono uppercase tracking-widest text-sm text-violet-400">
              Agent Activity
            </h3>
          </div>
          <span className="text-xs text-slate-400">
            {data?.agents.running ?? 0} / {data?.agents.total ?? 0} running
          </span>
        </div>

        {events.length === 0 ? (
          <div className="text-sm text-slate-500 py-4 text-center">
            No recent activity
          </div>
        ) : (
          <ul className="space-y-2 max-h-48 overflow-hidden">
            {events.slice(0, 5).map((e) => (
              <li
                key={e.id}
                className="text-sm flex items-center justify-between gap-2"
              >
                <div className="min-w-0 flex-1">
                  <span className="text-cyan-300 font-mono text-xs">
                    {e.agent_name}
                  </span>
                  <span className="text-slate-400 mx-1">→</span>
                  <span className="text-white">{e.symbol}</span>
                  <span className="text-slate-500 ml-2 text-xs">
                    {e.signal}
                  </span>
                </div>
                <span className="text-xs text-slate-600 shrink-0">
                  {e.status}
                </span>
              </li>
            ))}
          </ul>
        )}

        {events.length > 5 && (
          <div className="mt-3 text-xs text-slate-500">
            +{events.length - 5} more — click to expand
          </div>
        )}
      </button>
    </GlassCard>
  );
}
