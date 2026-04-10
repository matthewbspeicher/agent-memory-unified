import React, { useEffect, useRef } from 'react';
import { ArenaSession, ArenaTurn } from '../../lib/api/arena';

interface ArenaMatchStreamProps {
  session: ArenaSession;
}

export default function ArenaMatchStream({ session }: ArenaMatchStreamProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [session.turns]);

  return (
    <div className="bg-bg-base border border-border-subtle rounded-xl overflow-hidden font-mono flex flex-col h-[500px]">
      <div className="bg-bg-surface border-b border-border-subtle p-4 flex justify-between items-center">
        <div className="flex items-center gap-3">
          <div className="flex -space-x-2">
            <div className="w-6 h-6 rounded-full bg-accent-success border-2 border-black"></div>
            <div className="w-6 h-6 rounded-full bg-blue-500 border-2 border-black"></div>
          </div>
          <h3 className="text-[10px] uppercase tracking-[0.3em] text-gray-400 font-black">Neural Execution Stream</h3>
        </div>
        <div className="text-[9px] text-gray-600 bg-gray-900 px-2 py-1 rounded">
          SESSION_ID: {session.id.slice(0, 8)}
        </div>
      </div>

      <div 
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-6 space-y-6 scrollbar-hide"
      >
        {session.turns.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-center space-y-4">
            <div className="w-8 h-8 border-2 border-gray-800 border-t-accent-success rounded-full animate-spin"></div>
            <p className="text-[10px] text-gray-600 uppercase tracking-widest">Waiting for agent initialization...</p>
          </div>
        )}

        {session.turns.map((turn, index) => (
          <div key={turn.id} className="animate-in fade-in slide-in-from-bottom-2 duration-500">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-[10px] text-gray-700">[{turn.turn_number.toString().padStart(3, '0')}]</span>
              <span className="text-[10px] text-accent-success uppercase font-bold tracking-widest">{turn.tool_name}</span>
              <div className="h-[1px] flex-1 bg-border-subtle/50"></div>
              <span className={`text-[10px] ${turn.score_delta > 0 ? 'text-emerald-400' : 'text-accent-danger'}`}>
                {turn.score_delta > 0 ? '+' : ''}{turn.score_delta.toFixed(2)} XP
              </span>
            </div>
            
            <div className="pl-4 border-l-2 border-border-subtle/50 space-y-2">
              <div className="bg-bg-surface p-3 rounded text-[11px] text-gray-400 border border-border-subtle/50">
                <span className="text-gray-600 mr-2">$</span>
                {JSON.stringify(turn.tool_input)}
              </div>
              <div className="text-[11px] text-gray-500 leading-relaxed italic">
                {turn.tool_output}
              </div>
            </div>
          </div>
        ))}

        {session.status !== 'active' && (
          <div className="pt-8 border-t border-border-subtle text-center">
            <div className={`inline-block px-6 py-2 rounded-full text-xs font-black uppercase tracking-[0.2em] ${
              session.status === 'completed' ? 'bg-accent-success/10 text-accent-success border border-accent-success/20' : 'bg-rose-500/10 text-rose-500 border border-rose-500/20'
            }`}>
              Match {session.status}
            </div>
          </div>
        )}
      </div>

      <div className="bg-bg-surface border-t border-border-subtle p-3 flex justify-between items-center text-[9px] text-gray-600 uppercase tracking-widest">
        <div>Turns: {session.turn_count} / {session.score.toFixed(1)} Total XP</div>
        <div className="flex gap-4">
          <span className="flex items-center gap-1"><span className="w-1 h-1 bg-gray-600 rounded-full"></span> Latency: 142ms</span>
          <span className="flex items-center gap-1"><span className="w-1 h-1 bg-accent-success rounded-full"></span> Synchronized</span>
        </div>
      </div>
    </div>
  );
}