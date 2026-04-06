import { Link } from 'react-router-dom';

interface AgentBadgeProps {
  name: string;
  id?: string;
  className?: string;
}

export function AgentBadge({ name, id, className = "" }: AgentBadgeProps) {
  const getAgentStyle = (name: string) => {
    const safeName = name || 'UNKNOWN_AGENT';
    let hash = 0;
    for (let i = 0; i < safeName.length; i++) {
      hash = safeName.charCodeAt(i) + ((hash << 5) - hash);
    }
    const hue = Math.abs(hash) % 360;
    
    // Compute the raw HSL strings for inline styles
    const textColor = `hsl(${hue}, 90%, 75%)`;
    const accentColor = `hsl(${hue}, 90%, 65%)`;
    const glowColor = `hsla(${hue}, 90%, 65%, 0.4)`;
    
    return { textColor, accentColor, glowColor };
  };

  const styleColors = getAgentStyle(name);
  const safeName = name || 'UNKNOWN_AGENT';

  const content = (
    <span 
      className={`group relative inline-flex items-center px-3 py-1 text-[10px] sm:text-xs font-mono font-bold uppercase tracking-widest bg-black/50 backdrop-blur-md border border-white/10 overflow-hidden transition-all duration-300 hover:bg-black/70 hover:border-white/30 truncate max-w-full ${className}`}
      style={{
        color: styleColors.textColor,
        borderLeft: `3px solid ${styleColors.accentColor}`,
        boxShadow: `inset 4px 0 15px -5px ${styleColors.glowColor}, 0 2px 8px rgba(0,0,0,0.5)`,
      }}
      title={safeName}
    >
      {/* Decorative corners - top right and bottom right */}
      <span className="absolute top-0 right-0 w-1.5 h-1.5 border-t border-r border-white/20 transition-all duration-300 group-hover:border-white/60 group-hover:w-2.5 group-hover:h-2.5"></span>
      <span className="absolute bottom-0 right-0 w-1.5 h-1.5 border-b border-r border-white/20 transition-all duration-300 group-hover:border-white/60 group-hover:w-2.5 group-hover:h-2.5"></span>
      
      {/* Left decorative tech dots */}
      <span className="absolute left-1 top-1 w-0.5 h-0.5 rounded-full bg-white/30 group-hover:bg-white/70 transition-colors"></span>
      <span className="absolute left-1 bottom-1 w-0.5 h-0.5 rounded-full bg-white/30 group-hover:bg-white/70 transition-colors"></span>

      {/* Brackets around text */}
      <span className="text-white/30 group-hover:text-white/80 transition-colors mr-2 select-none font-normal">[</span>
      
      <span className="truncate drop-shadow-[0_0_2px_currentColor] relative z-10">
        {safeName}
      </span>
      
      <span className="text-white/30 group-hover:text-white/80 transition-colors ml-2 select-none font-normal">]</span>
    </span>
  );

  if (id) {
    return (
      <Link to={`/agents/${id}`} className="inline-block max-w-full focus:outline-none rounded transition-transform hover:scale-[1.02]">
        {content}
      </Link>
    );
  }

  return content;
}