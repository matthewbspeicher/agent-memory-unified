import { useEffect } from 'react';
import { X } from 'lucide-react';

interface DrawerProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  widthClass?: string;
}

/**
 * Overlay drawer that slides in from the right edge.
 * Closes on backdrop click or Escape key.
 */
export function Drawer({
  isOpen,
  onClose,
  title,
  children,
  widthClass = 'w-full md:w-3/5 lg:w-1/2',
}: DrawerProps) {
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <div
        className="flex-1 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200"
        onClick={onClose}
        aria-label="Close drawer"
      />
      {/* Drawer panel */}
      <aside
        className={`${widthClass} bg-slate-950/95 backdrop-blur-xl border-l border-white/10 shadow-[0_0_60px_rgba(0,0,0,0.5)] flex flex-col animate-in slide-in-from-right duration-200`}
        role="dialog"
        aria-modal="true"
      >
        <header className="flex items-center justify-between px-6 py-4 border-b border-white/10">
          <h2 className="text-lg font-mono uppercase tracking-widest text-cyan-400">
            {title}
          </h2>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-slate-800/60 text-slate-400 hover:text-white transition"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto p-6">{children}</div>
      </aside>
    </div>
  );
}
