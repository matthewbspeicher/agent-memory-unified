import React from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export interface AgentPriceCardProps {
  agentName: string;
  currentPrice: number;
  previousPrice: number;
  isLying: boolean;
  className?: string;
}

export function AgentPriceCard({ 
  agentName, 
  currentPrice, 
  previousPrice, 
  isLying,
  className 
}: AgentPriceCardProps) {
  const priceDiff = currentPrice - previousPrice;
  const isUp = priceDiff >= 0;
  
  return (
    <div className={twMerge(
      "glass-panel p-4 flex flex-col justify-between transition-all duration-500",
      isLying 
        ? "shadow-glow-danger border-accent-danger/50" 
        : "hover:border-border-subtle/20",
      className
    )}>
      <div className="flex justify-between items-center">
        <h3 className="text-text-primary font-bold font-sans">{agentName}</h3>
        {isLying && (
          <span className="text-xs text-accent-danger font-mono font-bold animate-pulse">
            LIAR DETECTED
          </span>
        )}
      </div>
      <div className="mt-4 flex items-end gap-2">
        <span className="text-2xl text-text-primary font-mono">
          ${currentPrice.toFixed(2)}
        </span>
        <span className={clsx(
          "text-sm font-mono mb-1",
          isUp ? "text-accent-success" : "text-accent-danger"
        )}>
          {isUp ? '+' : ''}{priceDiff.toFixed(2)}
        </span>
      </div>
    </div>
  );
}
