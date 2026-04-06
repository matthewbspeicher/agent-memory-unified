import React from 'react';

export const LeaderboardRankRow = ({ 
  rank = 1, 
  agent = { name: "Alpha-Zero", version: "4.2", model: "LLaMA-3" }, 
  elo = 2850,
  trend = ['W', 'W', 'L', 'W', 'D'] // Win, Loss, Draw
}) => {
  // Dynamic glow logic for top ranks
  let rankColor = "text-slate-500";
  let rankGlow = "";
  
  if (rank === 1) {
    rankColor = "text-yellow-400";
    rankGlow = "drop-shadow-[0_0_10px_rgba(250,204,21,0.8)]";
  } else if (rank === 2) {
    rankColor = "text-slate-300";
    rankGlow = "drop-shadow-[0_0_10px_rgba(203,213,225,0.6)]";
  } else if (rank === 3) {
    rankColor = "text-amber-600";
    rankGlow = "drop-shadow-[0_0_10px_rgba(217,119,6,0.8)]";
  }

  return (
    <div className="group relative flex items-center justify-between p-4 bg-slate-900/40 hover:bg-slate-800/60 border border-slate-800/60 hover:border-cyan-500/50 rounded-xl transition-all duration-300 backdrop-blur-md cursor-pointer overflow-hidden mb-3">
      {/* Interactive hover radar sweep effect */}
      <div className="absolute inset-0 w-full h-full bg-gradient-to-r from-transparent via-cyan-500/5 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-1000 ease-in-out pointer-events-none"></div>

      <div className="flex items-center gap-6 z-10">
        {/* Rank Number */}
        <div className={`w-8 text-center font-mono text-2xl font-bold ${rankColor} ${rankGlow}`}>
          {rank}
        </div>

        {/* Agent Info */}
        <div className="flex flex-col">
          <span className="text-slate-200 font-bold tracking-wide group-hover:text-cyan-300 transition-colors duration-300">
            {agent.name}
          </span>
          <span className="text-[11px] text-slate-500 font-mono tracking-wider mt-0.5">
            v{agent.version} // {agent.model}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-10 z-10">
        {/* Match History Barcode (Sparkline) */}
        <div className="hidden sm:flex items-end gap-1.5 h-6">
          {trend.map((res, i) => (
            <div 
              key={i} 
              className={`w-1.5 rounded-sm opacity-60 group-hover:opacity-100 transition-opacity duration-300 ${
                res === 'W' ? 'h-full bg-green-400 shadow-[0_0_8px_rgba(74,222,128,0.5)]' : 
                res === 'L' ? 'h-2 bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]' : 
                'h-4 bg-slate-400'
              }`}
              title={res === 'W' ? "Win" : res === 'L' ? "Loss" : "Draw"}
            ></div>
          ))}
        </div>

        {/* ELO Score */}
        <div className="text-right">
          <div className="font-mono text-xl text-cyan-400 font-semibold group-hover:text-cyan-300 group-hover:drop-shadow-[0_0_10px_rgba(6,182,212,0.8)] transition-all duration-300">
            {elo}
          </div>
          <div className="text-[9px] text-slate-500 font-mono uppercase tracking-widest mt-1">
            Rating
          </div>
        </div>
      </div>
    </div>
  );
};
