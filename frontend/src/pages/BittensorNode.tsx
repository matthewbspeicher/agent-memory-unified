import { GlassCard } from '../components/GlassCard';

export default function BittensorNode() {
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
              <span className="text-xs text-cyan-500 font-mono">LIVE</span>
              <div className="h-2 w-2 rounded-full bg-cyan-400 animate-pulse" />
            </div>
          </div>
          <div className="space-y-3 font-mono text-sm">
            <div className="flex justify-between items-center border-b border-cyan-500/10 pb-2">
              <span className="text-gray-500">Status</span>
              <span className="text-cyan-300">Connected</span>
            </div>
            <div className="flex justify-between items-center border-b border-cyan-500/10 pb-2">
              <span className="text-gray-500">Syncing</span>
              <span className="text-cyan-300">100%</span>
            </div>
            <div className="flex justify-between items-center border-b border-cyan-500/10 pb-2">
              <span className="text-gray-500">Block Height</span>
              <span className="text-cyan-300">3,492,108</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-500">Network</span>
              <span className="text-cyan-300">Finney</span>
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
              <span className="text-violet-300 truncate max-w-[120px]" title="5HgQwE...9pXx">5HgQ...9pXx</span>
            </div>
            <div className="flex justify-between items-center border-b border-violet-500/10 pb-2">
              <span className="text-gray-500">Hotkey</span>
              <span className="text-violet-300 truncate max-w-[120px]" title="5GrwVn...L1zK">5Grw...L1zK</span>
            </div>
            <div className="flex justify-between items-center border-b border-violet-500/10 pb-2">
              <span className="text-gray-500">Stake</span>
              <span className="text-violet-300">1,250.00 τ</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-500">Balance</span>
              <span className="text-violet-300">12.45 τ</span>
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
              <span className="text-emerald-300">SN 1 (Text Prompting)</span>
            </div>
            <div className="flex justify-between items-center border-b border-emerald-500/10 pb-2">
              <span className="text-gray-500">Emissions</span>
              <span className="text-emerald-300">+0.85 τ / day</span>
            </div>
            <div className="flex justify-between items-center border-b border-emerald-500/10 pb-2">
              <span className="text-gray-500">Dividends</span>
              <span className="text-emerald-300">0.04231</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-500">vTrust</span>
              <span className="text-emerald-300">0.985</span>
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
          <div className="text-gray-500">
            <span className="text-gray-600">[14:32:01]</span> <span className="text-cyan-400 font-bold ml-2">INFO</span> 
            <span className="ml-4 text-gray-300">Requesting weights for SN 1...</span>
          </div>
          <div className="text-gray-500">
            <span className="text-gray-600">[14:32:02]</span> <span className="text-violet-400 font-bold ml-2">DEBUG</span> 
            <span className="ml-4 text-gray-400">Evaluating miner 5HgQ...9pXx (UID 245) - Score: 0.892</span>
          </div>
          <div className="text-gray-500">
            <span className="text-gray-600">[14:32:02]</span> <span className="text-violet-400 font-bold ml-2">DEBUG</span> 
            <span className="ml-4 text-gray-400">Evaluating miner 5Grw...L1zK (UID 12) - Score: 0.104</span>
          </div>
          <div className="text-gray-500">
            <span className="text-gray-600">[14:32:03]</span> <span className="text-violet-400 font-bold ml-2">DEBUG</span> 
            <span className="ml-4 text-gray-400">Evaluating miner 5Jui...Qw2T (UID 88) - Score: 0.941</span>
          </div>
          <div className="text-gray-500">
            <span className="text-gray-600">[14:32:04]</span> <span className="text-cyan-400 font-bold ml-2">INFO</span> 
            <span className="ml-4 text-gray-300">Calculating gradients and normalizing weights...</span>
          </div>
          <div className="text-gray-500">
            <span className="text-gray-600">[14:32:04]</span> <span className="text-cyan-400 font-bold ml-2">INFO</span> 
            <span className="ml-4 text-gray-300">Setting weights on chain...</span>
          </div>
          <div className="text-gray-500">
            <span className="text-gray-600">[14:32:05]</span> <span className="text-emerald-400 font-bold ml-2">SUCCESS</span> 
            <span className="ml-4 text-emerald-100">Weights set successfully at block 3,492,108</span>
          </div>
          <div className="text-gray-500 pt-2">
            <span className="text-gray-600">[14:32:10]</span> <span className="text-gray-400 font-bold ml-2">WAIT</span> 
            <span className="ml-4 text-gray-500">Awaiting next epoch... (approx 360 blocks)</span>
          </div>
          <div className="text-gray-500 pt-4">
            <span className="text-gray-600">[14:35:00]</span> <span className="text-cyan-400 font-bold ml-2">INFO</span> 
            <span className="ml-4 text-gray-300">New block detected: 3,492,109</span>
          </div>
          <div className="text-gray-500">
            <span className="text-gray-600">[14:35:01]</span> <span className="text-violet-400 font-bold ml-2">DEBUG</span> 
            <span className="ml-4 text-gray-400">Synchronizing metagraph...</span>
          </div>
          <div className="text-gray-500">
            <span className="text-gray-600">[14:35:02]</span> <span className="text-emerald-400 font-bold ml-2">SUCCESS</span> 
            <span className="ml-4 text-emerald-100">Metagraph synced. 1024 neurons active.</span>
          </div>
          <div className="text-gray-500 flex items-center mt-2">
            <span className="text-emerald-400 mr-2">➜</span>
            <span className="animate-pulse bg-gray-500 w-2 h-4 inline-block"></span>
          </div>
        </div>
      </GlassCard>
    </div>
  );
}
