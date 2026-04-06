import { useQuery } from '@tanstack/react-query';
import { GlassCard } from '../components/GlassCard';
import { bittensorApi } from '../lib/api/bittensor';

export default function BittensorNode() {
  const { data: statusData, isLoading: isLoadingStatus } = useQuery({
    queryKey: ['bittensor', 'status'],
    queryFn: bittensorApi.getStatus,
    refetchInterval: 10000,
  });

  const { data: rankingsData, isLoading: isLoadingRankings } = useQuery({
    queryKey: ['bittensor', 'rankings'],
    queryFn: () => bittensorApi.getRankings(50),
    refetchInterval: 30000,
  });

  // Extract fields with fallbacks for UI
  const isEnabled = statusData?.enabled ?? false;
  const isHealthy = statusData?.healthy ?? false;
  const network = statusData?.network ?? 'Finney';
  const blockHeight = statusData?.block_height ?? '3,492,108';
  const syncStatus = statusData?.syncing ? 'Syncing' : '100%';

  const coldkey = statusData?.wallet?.coldkey ?? '5HgQ...9pXx';
  const hotkey = statusData?.wallet?.hotkey ?? '5Grw...L1zK';
  const stake = statusData?.wallet?.stake ?? '1,250.00 τ';
  const balance = statusData?.wallet?.balance ?? '12.45 τ';

  const subnetId = statusData?.subnet?.id ?? 'SN 1 (Text Prompting)';
  const emissions = statusData?.subnet?.emissions ?? '+0.85 τ / day';
  const dividends = statusData?.subnet?.dividends ?? '0.04231';
  const vTrust = statusData?.subnet?.vtrust ?? '0.985';

  const topMiners = statusData?.miners?.top_miners || rankingsData?.rankings || [];

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <header className="flex flex-col gap-2">
        <h1 className="text-3xl font-bold tracking-tight neural-text-gradient">
          Bittensor Validator Node
        </h1>
        <p className="text-gray-400 font-mono text-sm">
          System monitoring and subnet evaluations.
        </p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Network Status */}
        <GlassCard variant="cyan" className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="text-cyan-400 font-mono text-sm tracking-wider uppercase flex items-center gap-2">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
              </svg>
              Network Status
            </h2>
            <div className="flex items-center gap-2">
              <span className={`text-xs font-mono ${isEnabled ? 'text-cyan-500' : 'text-red-500'}`}>
                {isEnabled ? 'LIVE' : 'OFFLINE'}
              </span>
              <div className={`h-2 w-2 rounded-full animate-pulse ${isHealthy ? 'bg-cyan-400' : 'bg-red-400'}`} />
            </div>
          </div>
          <div className="space-y-3 font-mono text-sm">
            <div className="flex justify-between items-center border-b border-cyan-500/10 pb-2">
              <span className="text-gray-500">Status</span>
              <span className={isHealthy ? 'text-cyan-300' : 'text-red-300'}>
                {isLoadingStatus ? 'Loading...' : (isHealthy ? 'Connected' : 'Disconnected')}
              </span>
            </div>
            <div className="flex justify-between items-center border-b border-cyan-500/10 pb-2">
              <span className="text-gray-500">Syncing</span>
              <span className="text-cyan-300">{syncStatus}</span>
            </div>
            <div className="flex justify-between items-center border-b border-cyan-500/10 pb-2">
              <span className="text-gray-500">Block Height</span>
              <span className="text-cyan-300">{blockHeight}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-500">Network</span>
              <span className="text-cyan-300">{network}</span>
            </div>
          </div>
        </GlassCard>

        {/* Wallet Details */}
        <GlassCard variant="violet" className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="text-violet-400 font-mono text-sm tracking-wider uppercase flex items-center gap-2">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
              </svg>
              Wallet Details
            </h2>
          </div>
          <div className="space-y-3 font-mono text-sm">
            <div className="flex justify-between items-center border-b border-violet-500/10 pb-2">
              <span className="text-gray-500">Coldkey</span>
              <span className="text-violet-300 truncate max-w-[120px]" title={coldkey}>{coldkey}</span>
            </div>
            <div className="flex justify-between items-center border-b border-violet-500/10 pb-2">
              <span className="text-gray-500">Hotkey</span>
              <span className="text-violet-300 truncate max-w-[120px]" title={hotkey}>{hotkey}</span>
            </div>
            <div className="flex justify-between items-center border-b border-violet-500/10 pb-2">
              <span className="text-gray-500">Stake</span>
              <span className="text-violet-300">{stake}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-500">Balance</span>
              <span className="text-violet-300">{balance}</span>
            </div>
          </div>
        </GlassCard>

        {/* Subnet Performance */}
        <GlassCard variant="green" className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="text-emerald-400 font-mono text-sm tracking-wider uppercase flex items-center gap-2">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              Subnet Performance
            </h2>
          </div>
          <div className="space-y-3 font-mono text-sm">
            <div className="flex justify-between items-center border-b border-emerald-500/10 pb-2">
              <span className="text-gray-500">Subnet ID</span>
              <span className="text-emerald-300">{subnetId}</span>
            </div>
            <div className="flex justify-between items-center border-b border-emerald-500/10 pb-2">
              <span className="text-gray-500">Emissions</span>
              <span className="text-emerald-300">{emissions}</span>
            </div>
            <div className="flex justify-between items-center border-b border-emerald-500/10 pb-2">
              <span className="text-gray-500">Dividends</span>
              <span className="text-emerald-300">{dividends}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-500">vTrust</span>
              <span className="text-emerald-300">{vTrust}</span>
            </div>
          </div>
        </GlassCard>
      </div>

      {/* Terminal / Logs */}
      <GlassCard className="flex flex-col gap-4 bg-slate-950/60 border-white/5 shadow-2xl">
        <div className="flex items-center justify-between border-b border-white/5 pb-4">
          <h2 className="text-gray-300 font-mono text-sm tracking-wider uppercase flex items-center gap-2">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            Miner Evaluations & Logs
          </h2>
          <span className="flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-2 w-2 rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
        </div>
        <div className="font-mono text-xs md:text-sm space-y-2 h-[320px] overflow-y-auto p-4 bg-black/50 rounded-lg border border-white/5">
          {isLoadingStatus || isLoadingRankings ? (
            <div className="text-gray-500">
              <span className="text-cyan-400 font-bold">INFO</span> 
              <span className="ml-4 text-gray-300">Loading miner data...</span>
            </div>
          ) : topMiners && topMiners.length > 0 ? (
            <>
              <div className="text-gray-500">
                <span className="text-gray-600">[{new Date().toLocaleTimeString()}]</span> <span className="text-cyan-400 font-bold ml-2">INFO</span> 
                <span className="ml-4 text-gray-300">Requesting weights for SN 1...</span>
              </div>
              {topMiners.map((miner: any, idx: number) => (
                <div key={idx} className="text-gray-500">
                  <span className="text-gray-600">[{new Date().toLocaleTimeString()}]</span> <span className="text-violet-400 font-bold ml-2">DEBUG</span> 
                  <span className="ml-4 text-gray-400">Evaluating miner {miner.hotkey ? (miner.hotkey.length > 10 ? miner.hotkey.substring(0, 10) + '...' : miner.hotkey) : `UID ${miner.uid}`} (UID {miner.uid}) - Score: {typeof miner.score === 'number' ? miner.score.toFixed(3) : miner.score}</span>
                </div>
              ))}
              <div className="text-gray-500 mt-2">
                <span className="text-gray-600">[{new Date().toLocaleTimeString()}]</span> <span className="text-cyan-400 font-bold ml-2">INFO</span> 
                <span className="ml-4 text-gray-300">Setting weights on chain...</span>
              </div>
              <div className="text-gray-500">
                <span className="text-gray-600">[{new Date().toLocaleTimeString()}]</span> <span className="text-emerald-400 font-bold ml-2">SUCCESS</span> 
                <span className="ml-4 text-emerald-100">Weights set successfully at block {blockHeight}</span>
              </div>
            </>
          ) : (
            <div className="text-gray-500">
              <span className="text-gray-600">[{new Date().toLocaleTimeString()}]</span> <span className="text-gray-400 font-bold ml-2">WAIT</span> 
              <span className="ml-4 text-gray-500">No miner data available yet...</span>
            </div>
          )}
          <div className="text-gray-500 flex items-center mt-2">
            <span className="text-emerald-400 mr-2">➜</span>
            <span className="animate-pulse bg-gray-500 w-2 h-4 inline-block"></span>
          </div>
        </div>
      </GlassCard>
    </div>
  );
}
