import React, { useState, useEffect } from 'react';
import { AgentPriceCard } from './AgentPriceCard';
import { PropBetUI } from './PropBetUI';
import { ArenaMatchStream } from './ArenaMatchStream';
import { ArenaBettingForm } from './ArenaBettingForm';

interface ArenaViewProps {
  session: any;
  className?: string;
}

// Mock WebSocket hook for development
function useArenaWebSocket() {
  const [prices, setPrices] = useState<Record<string, number>>({
    'Agent Alpha': 10.0, 
    'Agent Beta': 10.0
  });
  const [liarAgent, setLiarAgent] = useState<string | null>(null);
  
  useEffect(() => {
    const timer = setInterval(() => {
      setPrices(prev => {
        const next = { ...prev };
        for (const key of Object.keys(next)) {
          next[key] = Math.max(0.01, next[key] + (Math.random() - 0.5) * 0.5);
        }
        return next;
      });
      
      // Random liar detection
      if (Math.random() < 0.05) {
        setLiarAgent(Math.random() < 0.5 ? 'Agent Alpha' : 'Agent Beta');
        setTimeout(() => setLiarAgent(null), 5000);
      }
    }, 2000);
    return () => clearInterval(timer);
  }, []);

  return { prices, liarAgent };
}

export function ArenaView({ session, className }: ArenaViewProps) {
  const { prices, liarAgent } = useArenaWebSocket();

  return (
    <div className={`min-h-screen bg-bg-base p-8 grid grid-cols-12 gap-8 ${className || ''}`}>
      
      {/* Left Column: Live Stream & Betting */}
      <div className="col-span-8 flex flex-col gap-6">
        <ArenaMatchStream session={session} />
        <ArenaBettingForm 
          sessionId={session.id}
          playerAName="Agent Alpha"
          playerBName="Agent Beta"
        />
      </div>

      {/* Right Column: Economy & Prop Bets */}
      <div className="col-span-4 flex flex-col gap-6">
        <h2 className="text-2xl text-text-primary font-bold mb-2">Live Odds</h2>
        
        <div className="grid grid-cols-1 gap-4">
          <AgentPriceCard 
            agentName="Agent Alpha" 
            currentPrice={prices['Agent Alpha']} 
            previousPrice={10.0} 
            isLying={liarAgent === 'Agent Alpha'} 
          />
          <AgentPriceCard 
            agentName="Agent Beta" 
            currentPrice={prices['Agent Beta']} 
            previousPrice={10.0} 
            isLying={liarAgent === 'Agent Beta'} 
          />
        </div>

        <div className="mt-8">
          <PropBetUI 
            prompt="Will the Blue Team patch the server before the Red Team breaches it?" 
            secondsRemaining={60} 
            onVote={(choice) => console.log('Vote:', choice)} 
          />
        </div>
      </div>
      
    </div>
  );
}
