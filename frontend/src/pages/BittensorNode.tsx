import { useQuery } from '@tanstack/react-query';
import { GlassCard } from '../components/GlassCard';
import { bittensorApi } from '../lib/api/bittensor';

function StatCard({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className={`rounded-lg border p-4 font-mono text-center transition-all ${
      warn
        ? 'border-rose-500/40 bg-rose-500/5 shadow-[0_0_10px_rgba(244,63,94,0.15)]'
        : 'border-slate-800 bg-slate-950/40'
    }`}>
      <div className={`text-2xl font-bold ${warn ? 'text-rose-400' : 'text-slate-200'}`}>{value}</div>
      <div className="text-xs text-slate-500 uppercase tracking-widest mt-1">{label}</div>
    </div>
  );
}

function RunningBadge({ running }: { running?: boolean }) {
  if (running === undefined) return null;
  return running ? (
    <div className="flex items-center gap-2">
      <span className="text-xs text-cyan-500 font-mono">LIVE</span>
      <div className="h-2 w-2 rounded-full bg-cyan-400 animate-pulse" />
    </div>
  ) : (
    <div className="flex items-center gap-2">
      <span className="text-xs text-slate-500 font-mono">OFFLINE</span>
      <div className="h-2 w-2 rounded-full bg-slate-600" />
    </div>
  );
}

export default function BittensorNode() {
  const { data: status, isLoading: isLoadingStatus } = useQuery({
    queryKey: ['bittensor', 'status'],
    queryFn: bittensorApi.getStatus,
    refetchInterval: 30_000,
  });

  const { data: metrics } = useQuery({
    queryKey: ['bittensor', 'metrics'],
    queryFn: bittensorApi.getMetrics,
    refetchInterval: 30_000,
  });

  if (isLoadingStatus) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="text-slate-600 font-mono text-sm uppercase tracking-widest animate-pulse">
          Connecting to validator node...
        </div>
      </div>
    );
  }

  if (!status?.enabled) {
    return (
      <div className="space-y-6 animate-in fade-in duration-500">
        <header className="flex flex-col gap-2">
          <h1 className="text-3xl font-bold tracking-tight neural-text-gradient">
            Bittensor Validator Node
          </h1>
        </header>
        <GlassCard variant="default">
          <p className="text-slate-400 font-mono text-sm">
            Bittensor integration is not enabled. Set STA_BITTENSOR_ENABLED=true to activate.
          </p>
        </GlassCard>
      </div>
    );
  }

  const hashTotal = (metrics?.scheduler?.hash_verifications_passed ?? 0) + (metrics?.scheduler?.hash_verifications_failed ?? 0);
  const hashPassRate = hashTotal > 0
    ? ((metrics?.scheduler?.hash_verifications_passed ?? 0) / hashTotal) * 100
    : 0;
  const avgDuration = metrics?.scheduler?.avg_collection_duration_secs ?? 0;
  const responseRate = (metrics?.scheduler?.last_miner_response_rate ?? 0) * 100;
  const consecutiveFailures = metrics?.scheduler?.consecutive_failures ?? 0;

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <header className="flex flex-col gap-2">
        <h1 className="text-3xl font-bold tracking-tight neural-text-gradient">
          Bittensor Validator Node
        </h1>
        <p className="text-gray-400 font-mono text-sm">
          Subnet 8 (Taoshi PTN) — {status?.healthy ? 'All systems operational' : 'Degraded'}
        </p>
      </header>

      {/* Row 1: Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <GlassCard variant="cyan" className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="text-cyan-400 font-mono text-sm tracking-wider uppercase">Scheduler</h2>
            <RunningBadge running={status?.scheduler?.running} />
          </div>
          <div className="space-y-3 font-mono text-sm">
            <div className="flex justify-between border-b border-cyan-500/10 pb-2">
              <span className="text-gray-500">Windows Collected</span>
              <span className="text-cyan-300">{status?.scheduler?.windows_collected_total ?? 0}</span>
            </div>
            <div className="flex justify-between border-b border-cyan-500/10 pb-2">
              <span className="text-gray-500">Last Collection</span>
              <span className="text-cyan-300 text-xs">{status?.scheduler?.last_window_collected ?? 'Never'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Next Window</span>
              <span className="text-cyan-300 text-xs">{status?.scheduler?.next_window ?? '—'}</span>
            </div>
          </div>
        </GlassCard>

        <GlassCard variant="violet" className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="text-violet-400 font-mono text-sm tracking-wider uppercase">Evaluator</h2>
            <RunningBadge running={status?.evaluator?.running} />
          </div>
          <div className="space-y-3 font-mono text-sm">
            <div className="flex justify-between border-b border-violet-500/10 pb-2">
              <span className="text-gray-500">Windows Evaluated</span>
              <span className="text-violet-300">{status?.evaluator?.windows_evaluated_total ?? 0}</span>
            </div>
            <div className="flex justify-between border-b border-violet-500/10 pb-2">
              <span className="text-gray-500">Unevaluated</span>
              <span className="text-violet-300">{status?.evaluator?.unevaluated_windows ?? 0}</span>
            </div>
            <div className="flex justify-between border-b border-violet-500/10 pb-2">
              <span className="text-gray-500">Skipped</span>
              <span className="text-violet-300">{metrics?.evaluator?.windows_skipped ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Last Eval</span>
              <span className="text-violet-300 text-xs">{status?.evaluator?.last_evaluation ?? 'Never'}</span>
            </div>
          </div>
        </GlassCard>

        <GlassCard variant="green" className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="text-emerald-400 font-mono text-sm tracking-wider uppercase">Weight Setter</h2>
          </div>
          <div className="space-y-3 font-mono text-sm">
            <div className="flex justify-between border-b border-emerald-500/10 pb-2">
              <span className="text-gray-500">Sets Total</span>
              <span className="text-emerald-300">{metrics?.weight_setter?.weight_sets_total ?? 0}</span>
            </div>
            <div className="flex justify-between border-b border-emerald-500/10 pb-2">
              <span className="text-gray-500">Sets Failed</span>
              <span className={`${(metrics?.weight_setter?.weight_sets_failed ?? 0) > 0 ? 'text-rose-400' : 'text-emerald-300'}`}>
                {metrics?.weight_setter?.weight_sets_failed ?? 0}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Last Block</span>
              <span className="text-emerald-300">{metrics?.weight_setter?.last_weight_set_block ?? '—'}</span>
            </div>
          </div>
        </GlassCard>
      </div>

      {/* Row 2: Compact Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Hash Pass Rate"
          value={hashTotal > 0 ? `${hashPassRate.toFixed(1)}%` : '—'}
          warn={hashTotal > 0 && hashPassRate < 80}
        />
        <StatCard
          label="Avg Collection"
          value={avgDuration > 0 ? `${avgDuration.toFixed(1)}s` : '—'}
          warn={avgDuration > 120}
        />
        <StatCard
          label="Miner Response"
          value={responseRate > 0 ? `${responseRate.toFixed(1)}%` : '—'}
          warn={responseRate > 0 && responseRate < 50}
        />
        <StatCard
          label="Consecutive Fails"
          value={String(consecutiveFailures)}
          warn={consecutiveFailures > 0}
        />
      </div>

      {/* Row 3: Miner Rankings Table */}
      <GlassCard className="flex flex-col gap-4 bg-slate-950/60 border-white/5 shadow-2xl">
        <div className="flex items-center justify-between border-b border-white/5 pb-4">
          <h2 className="text-gray-300 font-mono text-sm tracking-wider uppercase flex items-center gap-2">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            Top Miners ({status?.miners?.total_in_metagraph ?? 0} in metagraph)
          </h2>
          <span className="text-xs font-mono text-slate-500">
            {status?.miners?.responded_last_window ?? 0} responded last window
          </span>
        </div>
        {(status?.miners?.top_miners?.length ?? 0) > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full font-mono text-sm">
              <thead>
                <tr className="text-slate-500 text-xs uppercase tracking-widest border-b border-white/5">
                  <th className="text-left py-2 pr-4">Hotkey</th>
                  <th className="text-right py-2 px-4">Hybrid Score</th>
                  <th className="text-right py-2 px-4">Direction Acc</th>
                  <th className="text-right py-2 pl-4">Windows</th>
                </tr>
              </thead>
              <tbody>
                {status!.miners!.top_miners.map((m: any) => (
                  <tr key={m.hotkey} className="border-b border-white/5 hover:bg-white/[0.02] transition">
                    <td className="py-2 pr-4 text-cyan-300" title={m.hotkey}>
                      {m.hotkey.slice(0, 8)}...{m.hotkey.slice(-4)}
                    </td>
                    <td className="py-2 px-4 text-right text-slate-300">{m.hybrid_score.toFixed(4)}</td>
                    <td className="py-2 px-4 text-right text-slate-300">{(m.direction_accuracy * 100).toFixed(1)}%</td>
                    <td className="py-2 pl-4 text-right text-slate-400">{m.windows_evaluated}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-slate-500 font-mono text-sm py-8 text-center">No miners ranked yet</p>
        )}
      </GlassCard>
    </div>
  );
}
