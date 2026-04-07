import { useQuery } from '@tanstack/react-query';
import { intelligenceApi } from '../lib/api/intelligence';
import { GlassCard } from './GlassCard';

export function IntelligencePanel() {
  const { data: status, isLoading } = useQuery({
    queryKey: ['intelligence-status'],
    queryFn: intelligenceApi.getStatus,
    refetchInterval: 5000,
  });

  if (isLoading) return <div className="animate-pulse h-48 bg-white/5 rounded-xl" />;

  return (
    <GlassCard variant="violet" className="h-full">
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-sm font-bold text-violet-400 uppercase tracking-widest flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-violet-500 animate-pulse" />
          Intelligence Layer
        </h3>
        <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${status?.enabled ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-500' : 'bg-red-500/10 border-red-500/20 text-red-500'}`}>
          {status?.enabled ? 'ACTIVE' : 'DISABLED'}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-6">
        <div className="bg-black/20 p-3 rounded-lg border border-white/5">
          <div className="text-[10px] text-gray-500 uppercase font-mono">Enrichments</div>
          <div className="text-xl font-bold text-white font-mono">{status?.enrichments_applied || 0}</div>
        </div>
        <div className="bg-black/20 p-3 rounded-lg border border-white/5">
          <div className="text-[10px] text-gray-500 uppercase font-mono">Vetos</div>
          <div className="text-xl font-bold text-red-400 font-mono">{status?.vetos_issued || 0}</div>
        </div>
      </div>

      <div className="space-y-3">
        {status?.providers && Object.entries(status.providers).map(([name, p]) => (
          <div key={name} className="flex items-center justify-between group">
            <span className="text-xs text-gray-400 capitalize">{name.replace('_', ' ')}</span>
            <div className="flex items-center gap-3">
              {p.failures > 0 && (
                <span className="text-[10px] text-red-500 font-mono">FAIL: {p.failures}</span>
              )}
              <span className={`w-1.5 h-1.5 rounded-full ${
                p.circuit === 'closed' ? 'bg-emerald-500' : 
                p.circuit === 'open' ? 'bg-red-500' : 'bg-yellow-500'
              }`} title={`Circuit: ${p.circuit}`} />
            </div>
          </div>
        ))}
      </div>
    </GlassCard>
  );
}
