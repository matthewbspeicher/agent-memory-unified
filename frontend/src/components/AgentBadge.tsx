import React from 'react';
import { Link } from 'react-router-dom';

interface AgentBadgeProps {
  name: string;
  id?: string;
  className?: string;
}

export function AgentBadge({ name, id, className = "" }: AgentBadgeProps) {
  const getAgentStyle = (name: string) => {
    const safeName = name || 'Anonymous';
    let hash = 0;
    for (let i = 0; i < safeName.length; i++) {
      hash = safeName.charCodeAt(i) + ((hash << 5) - hash);
    }
    const hue = Math.abs(hash) % 360;
    return {
      color: `hsl(${hue}, 80%, 75%)`,
      backgroundColor: `hsla(${hue}, 80%, 65%, 0.15)`,
      borderColor: `hsla(${hue}, 80%, 65%, 0.25)`
    };
  };

  const style = getAgentStyle(name);
  const content = (
    <span 
      className={`px-2.5 py-0.5 rounded text-xs font-bold uppercase tracking-wider border shadow-sm truncate max-w-full inline-block ${className}`}
      style={style}
      title={name}
    >
      @{name}
    </span>
  );

  if (id) {
    return (
      <Link to={`/agents/${id}`} className="hover:opacity-80 transition-opacity inline-block max-w-full">
        {content}
      </Link>
    );
  }

  return content;
}
