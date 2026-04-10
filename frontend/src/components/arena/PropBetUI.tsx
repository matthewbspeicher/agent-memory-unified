import { useState, useEffect, useCallback } from 'react';

export interface PropBetUIProps {
  prompt: string;
  secondsRemaining: number;
  onVote: (choice: boolean) => void;
  disabled?: boolean;
  className?: string;
}

export function PropBetUI({ 
  prompt, 
  secondsRemaining, 
  onVote,
  disabled = false,
  className 
}: PropBetUIProps) {
  const [timeLeft, setTimeLeft] = useState(secondsRemaining);

  // Reset timer if prop changes
  useEffect(() => {
    setTimeLeft(secondsRemaining);
  }, [secondsRemaining]);

  useEffect(() => {
    if (timeLeft <= 0) return;
    const timer = setInterval(() => setTimeLeft(t => t - 1), 1000);
    return () => clearInterval(timer);
  }, [timeLeft]);

  const isExpired = timeLeft <= 0 || disabled;

  const handleVote = useCallback((choice: boolean) => {
    if (!isExpired) onVote(choice);
  }, [isExpired, onVote]);

  return (
    <div className={`neural-card border-accent-warning/30 shadow-glow-warning flex flex-col gap-4 ${className || ''}`}>
      <div className="flex justify-between items-center border-b border-border-subtle/10 pb-2">
        <h4 className="text-accent-warning font-bold uppercase tracking-wider text-sm">
          Live Prop Bet
        </h4>
        <span className="font-mono text-text-secondary">{timeLeft}s</span>
      </div>
      
      <p className="text-text-primary text-lg">{prompt}</p>
      
      <div className="flex gap-4 mt-2">
        <button 
          onClick={() => handleVote(true)}
          disabled={isExpired}
          className="flex-1 neural-button bg-accent-success/20 text-accent-success border border-accent-success/30 hover:bg-accent-success/30 disabled:opacity-50"
        >
          YES
        </button>
        <button 
          onClick={() => handleVote(false)}
          disabled={isExpired}
          className="flex-1 neural-button bg-accent-danger/20 text-accent-danger border border-accent-danger/30 hover:bg-accent-danger/30 disabled:opacity-50"
        >
          NO
        </button>
      </div>
    </div>
  );
}
