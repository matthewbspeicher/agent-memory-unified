import React from 'react';

export const ThoughtCard = ({ thought }: { thought: any }) => (
  <div className="p-4 border rounded shadow-sm mb-2 bg-white">
    <div className="flex justify-between">
      <span className="font-bold">{thought.action} {thought.symbol}</span>
      <span>{thought.conviction_score.toFixed(2)}</span>
    </div>
    <div className="mt-2">
      {thought.rule_evaluations && thought.rule_evaluations.map((rule: any, idx: number) => (
        <span key={idx} className={`badge ${rule.passed ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'} mr-1 text-xs px-2 py-1 rounded`}>
          {rule.name}
        </span>
      ))}
    </div>
  </div>
);
