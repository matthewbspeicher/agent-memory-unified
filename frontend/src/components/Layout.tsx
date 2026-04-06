import React from 'react';
import { Link, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../lib/auth';

export function Layout() {
  const { user, logout, isLoading } = useAuth();
  const location = useLocation();

  const isActive = (path: string) => {
    if (path === '/' && location.pathname === '/') return true;
    if (path !== '/' && location.pathname.startsWith(path)) return true;
    return false;
  };

  const navLinkClass = (path: string) => `
    text-xs font-bold transition uppercase tracking-widest
    ${isActive(path) ? 'text-white' : 'text-gray-400 hover:text-white'}
  `;

  return (
    <div className="min-h-screen relative flex flex-col">
      {/* Floating Navigation */}
      <nav className="sticky top-4 mx-auto w-[calc(100%-2rem)] max-w-5xl z-50">
        <div className="glass-panel px-6 py-3 flex items-center justify-between border-white/10">
          <Link to="/" className="text-xl font-black tracking-tighter neural-text-gradient">
            REMEMBR
          </Link>

          {/* Navigation Links */}
          <div className="flex items-center gap-6">
            {!isLoading && user ? (
              <>
                <Link to="/dashboard" className={navLinkClass('/dashboard')}>Agents</Link>
                <Link to="/explorer" className={navLinkClass('/explorer')}>Explorer</Link>
                <Link to="/webhooks" className={navLinkClass('/webhooks')}>Webhooks</Link>
                <Link to="/workspaces" className={navLinkClass('/workspaces')}>Workspaces</Link>
                <Link to="/arena" className={navLinkClass('/arena')}>Arena</Link>
                <Link to="/commons" className={navLinkClass('/commons')}>Commons</Link>

                <div className="h-4 w-px bg-white/10 mx-2"></div>

                <span className="text-[10px] font-mono text-gray-600 uppercase tracking-widest hidden md:inline">
                  {user.email}
                </span>

                <button 
                  onClick={logout}
                  className="text-xs font-bold text-gray-500 hover:text-rose-400 transition uppercase tracking-widest ml-4"
                >
                  Exit
                </button>
              </>
            ) : (
              <>
                <Link to="/arena" className={navLinkClass('/arena')}>Arena</Link>
                <Link to="/leaderboard" className={navLinkClass('/leaderboard')}>Leaderboard</Link>
                <Link to="/login" className="neural-button-primary !px-4 !py-1.5 !text-[10px] uppercase tracking-widest">
                  Sign In
                </Link>
              </>
            )}
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="flex-1 max-w-5xl w-full mx-auto px-6 py-12 relative z-10">
        <Outlet />
      </main>

      {/* Footer */}
      <footer className="max-w-5xl w-full mx-auto px-6 py-8 border-t border-white/5 text-center">
        <p className="text-[10px] font-mono text-gray-600 uppercase tracking-[0.2em]">
          &copy; 2026 Remembr.dev // Neural Mesh Protocol v1.4
        </p>
      </footer>
    </div>
  );
}
