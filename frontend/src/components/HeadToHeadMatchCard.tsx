import React from 'react';

export const HeadToHeadMatchCard = ({ 
  agentA = { name: "Optimus-7", initials: "OP7", elo: 2450 }, 
  agentB = { name: "Nexus.Void", initials: "NXV", elo: 2410 }, 
  matchStatus = "LIVE", 
  winProbA = 62 
}) => {
  const probB = 100 - winProbA;
  
  return (
    <div className="relative w-full max-w-2xl mx-auto p-6 rounded-2xl bg-slate-950/70 backdrop-blur-xl border border-slate-800 shadow-[0_0_20px_rgba(0,0,0,0.8)] overflow-hidden">
      {/* Ambient Mesh Glows */}
      <div className="absolute -top-10 -left-10 w-40 h-40 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none"></div>
      <div className="absolute -bottom-10 -right-10 w-40 h-40 bg-violet-500/10 rounded-full blur-3xl pointer-events-none"></div>
      
      {/* Header / Live Status */}
      <div className="flex justify-between items-center mb-8 relative z-10">
        <div className="flex items-center gap-3">
          {matchStatus === 'LIVE' && (
            <span className="flex h-3 w-3 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.8)]"></span>
            </span>
          )}
          <span className="font-mono text-xs text-slate-300 tracking-widest">{matchStatus}</span>
        </div>
        <span className="font-mono text-[10px] text-slate-500 tracking-widest">SIM_ID: #89X-F2</span>
      </div>

      {/* Main VS Area */}
      <div className="flex justify-between items-center relative z-10">
        {/* Agent A (Cyan) */}
        <div className="flex flex-col items-center space-y-3 w-1/3">
          <div className="w-16 h-16 rounded-full border border-cyan-500/50 shadow-[0_0_15px_rgba(6,182,212,0.4)] flex items-center justify-center bg-slate-900">
            <span className="font-mono text-cyan-400 text-xl font-bold">{agentA.initials}</span>
          </div>
          <div className="text-center">
            <h3 className="text-slate-100 font-bold text-lg tracking-wide">{agentA.name}</h3>
            <p className="font-mono text-cyan-400 text-sm mt-1">ELO: {agentA.elo}</p>
          </div>
        </div>

        {/* VS Divider */}
        <div className="flex flex-col items-center justify-center w-1/3">
          <div className="px-4 py-1.5 rounded border border-slate-700 bg-slate-900/80 shadow-inner">
            <span className="font-mono text-slate-400 text-sm tracking-widest">VS</span>
          </div>
        </div>

        {/* Agent B (Violet) */}
        <div className="flex flex-col items-center space-y-3 w-1/3">
          <div className="w-16 h-16 rounded-full border border-violet-500/50 shadow-[0_0_15px_rgba(139,92,246,0.4)] flex items-center justify-center bg-slate-900">
            <span className="font-mono text-violet-400 text-xl font-bold">{agentB.initials}</span>
          </div>
          <div className="text-center">
            <h3 className="text-slate-100 font-bold text-lg tracking-wide">{agentB.name}</h3>
            <p className="font-mono text-violet-400 text-sm mt-1">ELO: {agentB.elo}</p>
          </div>
        </div>
      </div>

      {/* Win Probability Bar */}
      <div className="mt-10 relative z-10">
        <div className="flex justify-between text-xs font-mono mb-2 tracking-widest">
          <span className="text-cyan-400 drop-shadow-[0_0_5px_rgba(6,182,212,0.8)]">WIN_PROB: {winProbA}%</span>
          <span className="text-violet-400 drop-shadow-[0_0_5px_rgba(139,92,246,0.8)]">{probB}%</span>
        </div>
        <div className="h-1.5 w-full bg-slate-800/80 rounded-full overflow-hidden flex shadow-inner">
          <div className="h-full bg-cyan-400 shadow-[0_0_10px_rgba(6,182,212,1)] transition-all duration-1000 ease-out" style={{ width: `${winProbA}%` }}></div>
          <div className="h-full bg-violet-500 shadow-[0_0_10px_rgba(139,92,246,1)] transition-all duration-1000 ease-out" style={{ width: `${probB}%` }}></div>
        </div>
      </div>
    </div>
  );
};
