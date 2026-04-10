import { Link, useLocation } from 'react-router-dom';
import { Activity, BrainCircuit, Terminal, Search, Settings, LogOut, Compass, FolderOpen, Swords, Globe, Trophy, Server, Rocket, Users } from 'lucide-react';
import { cn } from '../lib/utils';
import { useAuth } from '../lib/auth';

function NavItem({ to, icon: Icon, label, isActive, accent = 'cyan' }: { to: string, icon: any, label: string, isActive?: boolean, accent?: 'cyan' | 'violet' | 'green' }) {
  const accentActive = {
    cyan: 'bg-cyan-950/40 text-cyan-400 border-cyan-400 shadow-[inset_2px_0_10px_rgba(34,211,238,0.15)]',
    violet: 'bg-violet-950/40 text-violet-400 border-violet-400 shadow-[inset_2px_0_10px_rgba(167,139,250,0.15)]',
    green: 'bg-emerald-950/40 text-emerald-400 border-emerald-400 shadow-[inset_2px_0_10px_rgba(52,211,153,0.15)]',
  };
  const accentHover = {
    cyan: 'hover:bg-cyan-950/20 hover:text-cyan-300',
    violet: 'hover:bg-violet-950/20 hover:text-violet-300',
    green: 'hover:bg-emerald-950/20 hover:text-emerald-300',
  };

  return (
    <Link
      to={to}
      className={cn(
        "w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-200 border border-transparent font-mono text-sm tracking-wide",
        isActive ? cn(accentActive[accent], "border-l-2 rounded-l-none") : cn("text-slate-400", accentHover[accent])
      )}
    >
      <Icon className={cn("w-5 h-5", isActive ? "animate-pulse" : "")} />
      <span>{label}</span>
    </Link>
  );
}

export function Sidebar() {
  const location = useLocation();
  const { user, logout, isLoading } = useAuth();

  const isActive = (path: string) => {
    if (path === '/' && location.pathname === '/') return true;
    if (path !== '/' && location.pathname.startsWith(path)) return true;
    return false;
  };

  return (
    <aside className="flex flex-col w-72 h-screen bg-slate-950/80 backdrop-blur-xl border-r border-white/5 shrink-0">
      {/* Brand / Logo */}
      <div className="p-6 flex items-center gap-3">
        <div className="w-8 h-8 rounded bg-gradient-to-br from-cyan-500 to-violet-600 flex items-center justify-center shadow-[0_0_15px_rgba(34,211,238,0.4)]">
          <BrainCircuit className="w-5 h-5 text-white" />
        </div>
        <Link to="/" className="font-bold text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-violet-400 tracking-widest font-mono">
          NEXUS_CORE
        </Link>
      </div>

      {/* Omnibar Placeholder */}
      <div className="px-4 mb-6">
        <div className="relative group">
          <div className="absolute inset-0 bg-cyan-500/20 rounded-lg blur opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
          <div className="relative flex items-center bg-slate-900/50 border border-white/10 rounded-lg px-3 py-2.5 focus-within:border-cyan-500/50 focus-within:ring-1 focus-within:ring-cyan-500/50 transition-all">
            <Search className="w-4 h-4 text-cyan-500/70 mr-2" />
            <input type="text" placeholder="Query memory matrix..." className="bg-transparent border-none outline-none text-sm text-cyan-50 font-mono w-full placeholder:text-slate-600" />
            <div className="flex items-center gap-1">
              <kbd className="hidden sm:inline-block bg-slate-950 border border-white/10 rounded px-1.5 py-0.5 text-[10px] font-mono text-slate-500">⌘</kbd>
              <kbd className="hidden sm:inline-block bg-slate-950 border border-white/10 rounded px-1.5 py-0.5 text-[10px] font-mono text-slate-500">K</kbd>
            </div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 space-y-6 overflow-y-auto">
        {!isLoading && user ? (
          <>
            <div>
              <h3 className="px-4 text-[10px] uppercase font-mono tracking-[0.2em] text-slate-500 mb-2">Ops</h3>
              <div className="space-y-1">
                <NavItem to="/mission-control" icon={Rocket} label="Mission Control" isActive={isActive('/mission-control')} accent="cyan" />
                <NavItem to="/dashboard" icon={Activity} label="Dashboard" isActive={isActive('/dashboard')} accent="cyan" />
                <NavItem to="/roster" icon={Users} label="Agent Roster" isActive={isActive('/roster')} accent="cyan" />
                <NavItem to="/bittensor" icon={Server} label="Bittensor Node" isActive={isActive('/bittensor')} accent="cyan" />
              </div>
            </div>
            <div>
              <h3 className="px-4 text-[10px] uppercase font-mono tracking-[0.2em] text-slate-500 mb-2">Community</h3>
              <div className="space-y-1">
                <NavItem to="/arena" icon={Swords} label="Arena" isActive={isActive('/arena')} accent="green" />
                <NavItem to="/commons" icon={Globe} label="Commons" isActive={isActive('/commons')} accent="green" />
                <NavItem to="/leaderboard" icon={Trophy} label="Leaderboard" isActive={isActive('/leaderboard')} accent="green" />
              </div>
            </div>
            <div>
              <h3 className="px-4 text-[10px] uppercase font-mono tracking-[0.2em] text-slate-500 mb-2">System</h3>
              <div className="space-y-1">
                <NavItem to="/explorer" icon={Compass} label="Explorer" isActive={isActive('/explorer')} accent="violet" />
                <NavItem to="/webhooks" icon={Terminal} label="Webhooks" isActive={isActive('/webhooks')} accent="violet" />
                <NavItem to="/workspaces" icon={FolderOpen} label="Workspaces" isActive={isActive('/workspaces')} accent="violet" />
              </div>
            </div>
          </>
        ) : (
          <>
            <div>
              <h3 className="px-4 text-[10px] uppercase font-mono tracking-[0.2em] text-slate-500 mb-2">Public</h3>
              <div className="space-y-1">
                <NavItem to="/arena" icon={Swords} label="Arena" isActive={isActive('/arena')} accent="green" />
                <NavItem to="/leaderboard" icon={Trophy} label="Leaderboard" isActive={isActive('/leaderboard')} accent="green" />
                <NavItem to="/login" icon={LogOut} label="Sign In" isActive={isActive('/login')} accent="cyan" />
              </div>
            </div>
          </>
        )}
      </nav>
      
      {/* Footer Settings */}
      <div className="p-4 border-t border-white/5 bg-slate-900/20">
        {!isLoading && user ? (
          <div className="flex flex-col gap-2">
            <span className="px-4 text-[10px] font-mono text-slate-500 uppercase tracking-widest truncate">
              {user.email}
            </span>
            <button onClick={logout} className="flex items-center gap-3 w-full px-4 py-2.5 rounded-lg hover:bg-slate-800/50 text-slate-400 hover:text-rose-400 transition-colors font-mono text-sm">
              <LogOut className="w-4 h-4" />
              <span>Exit System</span>
            </button>
          </div>
        ) : (
          <button className="flex items-center gap-3 w-full px-4 py-2.5 rounded-lg hover:bg-slate-800/50 text-slate-400 hover:text-cyan-400 transition-colors font-mono text-sm">
            <Settings className="w-4 h-4" />
            <span>System Config</span>
          </button>
        )}
      </div>
    </aside>
  );
}
