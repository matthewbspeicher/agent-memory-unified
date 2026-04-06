import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { GlassCard } from '../components/GlassCard';

export default function Login() {
  const [token, setToken] = useState('');
  const [inviteCode, setInviteCode] = useState('');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [mode, setMode] = useState<'token' | 'invite'>('token');
  const [status, setStatus] = useState<{ type: 'error' | 'success'; message: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleTokenLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (token) {
      localStorage.setItem('auth_token', token);
      navigate('/');
    }
  };

  const handleInviteSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatus(null);
    setLoading(true);

    try {
      const res = await fetch('/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ name, email, invite_code: inviteCode }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        const msg = data.errors?.invite_code?.[0]
          || data.errors?.email?.[0]
          || data.message
          || 'SYSTEM_ERROR: INVALID_PARAMETERS';
        setStatus({ type: 'error', message: msg });
        return;
      }

      setStatus({ type: 'success', message: 'UPLINK_ESTABLISHED: CHECK_EMAIL_FOR_MAGIC_LINK' });
    } catch {
      setStatus({ type: 'error', message: 'NETWORK_ERROR: UPLINK_FAILED' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center p-4 font-mono relative overflow-hidden">
      {/* Background decoration */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-cyan-900/20 blur-[120px] rounded-full pointer-events-none" />

      <GlassCard variant="cyan" className="w-full max-w-md !p-0 z-10 shadow-[0_0_30px_rgba(34,211,238,0.15)]">
        {/* Terminal Header */}
        <div className="bg-slate-950/80 px-4 py-3 border-b border-cyan-900/50 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 bg-cyan-400 rounded-full animate-pulse"></span>
            <span className="text-xs text-cyan-500 tracking-widest font-bold">AUTH_TERMINAL_V1.0</span>
          </div>
        </div>

        <div className="p-8">
          {/* Mode tabs */}
          <div className="flex mb-8 border-b border-slate-800">
            <button
              onClick={() => { setMode('token'); setStatus(null); }}
              className={`flex-1 pb-3 text-sm font-bold tracking-widest uppercase transition-all ${
                mode === 'token'
                  ? 'text-cyan-400 border-b-2 border-cyan-400 shadow-[0_4px_10px_-2px_rgba(34,211,238,0.3)]'
                  : 'text-slate-500 hover:text-slate-400'
              }`}
            >
              Agent_Login
            </button>
            <button
              onClick={() => { setMode('invite'); setStatus(null); }}
              className={`flex-1 pb-3 text-sm font-bold tracking-widest uppercase transition-all ${
                mode === 'invite'
                  ? 'text-cyan-400 border-b-2 border-cyan-400 shadow-[0_4px_10px_-2px_rgba(34,211,238,0.3)]'
                  : 'text-slate-500 hover:text-slate-400'
              }`}
            >
              Request_Access
            </button>
          </div>

          {mode === 'token' ? (
            <form onSubmit={handleTokenLogin}>
              <div className="mb-6">
                <label className="block text-xs font-bold text-cyan-500 mb-2 uppercase tracking-widest">
                  &gt; API_TOKEN_INPUT
                </label>
                <input
                  type="password"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="amc_..."
                  className="w-full px-4 py-3 bg-slate-950 border border-cyan-900 rounded text-cyan-300 placeholder-slate-700 focus:outline-none focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400 transition-all font-mono"
                  autoComplete="off"
                  spellCheck="false"
                />
              </div>
              <button
                type="submit"
                disabled={!token}
                className="w-full px-4 py-3 bg-cyan-500/10 border border-cyan-500/50 text-cyan-400 font-bold rounded hover:bg-cyan-500/20 hover:shadow-[0_0_15px_rgba(34,211,238,0.4)] disabled:opacity-50 disabled:cursor-not-allowed transition-all uppercase tracking-widest"
              >
                Execute_Login
              </button>
            </form>
          ) : (
            <form onSubmit={handleInviteSignup}>
              <div className="mb-4">
                <label className="block text-xs font-bold text-cyan-500 mb-2 uppercase tracking-widest">
                  &gt; INVITE_CODE
                </label>
                <input
                  type="text"
                  value={inviteCode}
                  onChange={(e) => setInviteCode(e.target.value)}
                  placeholder="inv_..."
                  className="w-full px-4 py-3 bg-slate-950 border border-cyan-900 rounded text-cyan-300 placeholder-slate-700 focus:outline-none focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400 transition-all font-mono"
                  autoComplete="off"
                  spellCheck="false"
                />
              </div>
              <div className="mb-4">
                <label className="block text-xs font-bold text-cyan-500 mb-2 uppercase tracking-widest">
                  &gt; IDENTIFIER
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Operative Name"
                  className="w-full px-4 py-3 bg-slate-950 border border-cyan-900 rounded text-cyan-300 placeholder-slate-700 focus:outline-none focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400 transition-all font-mono"
                  autoComplete="off"
                  spellCheck="false"
                />
              </div>
              <div className="mb-6">
                <label className="block text-xs font-bold text-cyan-500 mb-2 uppercase tracking-widest">
                  &gt; COMM_LINK (EMAIL)
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@grid.net"
                  className="w-full px-4 py-3 bg-slate-950 border border-cyan-900 rounded text-cyan-300 placeholder-slate-700 focus:outline-none focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400 transition-all font-mono"
                  autoComplete="off"
                  spellCheck="false"
                />
              </div>

              {status && (
                <div className={`mb-6 p-4 rounded text-xs font-bold uppercase tracking-wider border ${
                  status.type === 'error'
                    ? 'bg-rose-500/10 border-rose-500/50 text-rose-400 shadow-[0_0_10px_rgba(244,63,94,0.2)]'
                    : 'bg-emerald-500/10 border-emerald-500/50 text-emerald-400 shadow-[0_0_10px_rgba(16,185,129,0.2)]'
                }`}>
                  [ {status.message} ]
                </div>
              )}

              <button
                type="submit"
                disabled={!inviteCode || !name || !email || loading}
                className="w-full px-4 py-3 bg-cyan-500/10 border border-cyan-500/50 text-cyan-400 font-bold rounded hover:bg-cyan-500/20 hover:shadow-[0_0_15px_rgba(34,211,238,0.4)] disabled:opacity-50 disabled:cursor-not-allowed transition-all uppercase tracking-widest"
              >
                {loading ? 'Transmitting...' : 'Initialize_Uplink'}
              </button>
            </form>
          )}
        </div>
      </GlassCard>
    </div>
  );
}
