import React from 'react';
import { cn } from '../lib/utils';

// Re-export cn for any existing consumers importing from GlassCard
export { cn };

export interface GlassCardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'cyan' | 'violet' | 'green' | 'red';
  hoverEffect?: boolean;
}

export function GlassCard({ 
  children, 
  className, 
  variant = 'default', 
  hoverEffect = true,
  ...props 
}: GlassCardProps) {
  // Mapping variants to their respective subtle borders and soft shadows
  const variantStyles = {
    default: 'border-white/10 shadow-black/20',
    cyan: 'border-cyan-500/30 shadow-cyan-500/10',
    violet: 'border-violet-500/30 shadow-violet-500/10',
    green: 'border-emerald-500/30 shadow-emerald-500/10',
    red: 'border-rose-500/30 shadow-rose-500/10',
  };

  // Hover states creating the "neon glow" lift effect
  const hoverStyles = {
    default: 'hover:border-white/20 hover:shadow-white/5',
    cyan: 'hover:border-cyan-400/50 hover:shadow-[0_0_15px_rgba(34,211,238,0.2)]',
    violet: 'hover:border-violet-400/50 hover:shadow-[0_0_15px_rgba(167,139,250,0.2)]',
    green: 'hover:border-emerald-400/50 hover:shadow-[0_0_15px_rgba(52,211,153,0.2)]',
    red: 'hover:border-rose-400/50 hover:shadow-[0_0_15px_rgba(251,113,133,0.2)]',
  };

  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-xl",
        "bg-slate-950/40 backdrop-blur-md", // Base Glassmorphism
        "border transition-all duration-300", 
        hoverEffect && "hover:-translate-y-1", // Lift effect
        variantStyles[variant],
        hoverEffect && hoverStyles[variant],
        className
      )}
      {...props}
    >
      {/* Subtle lighting overlay for a slight 3D mesh effect */}
      <div className="absolute inset-0 bg-gradient-to-br from-white/[0.03] to-transparent pointer-events-none" />
      
      <div className="relative z-10 p-6">
        {children}
      </div>
    </div>
  );
}
