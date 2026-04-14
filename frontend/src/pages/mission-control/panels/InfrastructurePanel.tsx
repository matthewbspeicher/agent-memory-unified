import { MissionControlStatus } from '../../../lib/api/missionControl';
import { GlassCard } from '../../../components/GlassCard';
import { Server } from 'lucide-react';

interface Props {
  data: MissionControlStatus | undefined;
  onExpand: () => void;
}

export function InfrastructurePanel({ data, onExpand }: Props) {
  const services = data?.infra.services ?? [];

  return (
    <GlassCard
      variant="cyan"
      className="p-4 cursor-pointer hover:ring-2 hover:ring-cyan-500/50 transition"
    >
      <button onClick={onExpand} className="w-full text-left">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Server className="w-4 h-4 text-cyan-400" />
            <h3 className="font-mono uppercase tracking-widest text-sm text-cyan-400">
              Infrastructure
            </h3>
          </div>
          <span className="text-xs text-slate-400">
            {services.length} {services.length === 1 ? 'service' : 'services'}
          </span>
        </div>

        <ul className="space-y-2">
          {services.slice(0, 4).map((s) => {
            const dot =
              s.status === 'healthy'
                ? 'bg-emerald-400'
                : s.status === 'unhealthy'
                ? 'bg-rose-500'
                : 'bg-slate-500';
            return (
              <li
                key={s.name}
                className="flex items-center justify-between text-sm"
              >
                <div className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${dot}`} />
                  <span className="text-slate-300">{s.name}</span>
                </div>
                <span className="text-xs text-slate-500 uppercase">
                  {s.status}
                </span>
              </li>
            );
          })}
        </ul>

        {services.length > 4 && (
          <div className="mt-3 text-xs text-slate-500">
            +{services.length - 4} more — click to expand
          </div>
        )}
      </button>
    </GlassCard>
  );
}
