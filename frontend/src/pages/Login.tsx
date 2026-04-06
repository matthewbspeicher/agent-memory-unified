import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

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
          || 'Something went wrong';
        setStatus({ type: 'error', message: msg });
        return;
      }

      setStatus({ type: 'success', message: 'Check your email for a magic link!' });
    } catch {
      setStatus({ type: 'error', message: 'Network error. Try again.' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-8 max-w-md mx-auto">
      {/* Mode tabs */}
      <div className="flex mb-6 border-b border-gray-700">
        <button
          onClick={() => { setMode('token'); setStatus(null); }}
          className={`flex-1 pb-3 text-sm font-medium transition ${
            mode === 'token'
              ? 'text-white border-b-2 border-blue-500'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          Agent Login
        </button>
        <button
          onClick={() => { setMode('invite'); setStatus(null); }}
          className={`flex-1 pb-3 text-sm font-medium transition ${
            mode === 'invite'
              ? 'text-white border-b-2 border-blue-500'
              : 'text-gray-400 hover:text-gray-300'
          }`}
        >
          Join with Invite
        </button>
      </div>

      {mode === 'token' ? (
        <>
          <h2 className="text-2xl font-bold text-white mb-6">Login</h2>
          <form onSubmit={handleTokenLogin}>
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-300 mb-2">
                API Token
              </label>
              <input
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="amc_..."
                className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <button
              type="submit"
              disabled={!token}
              className="w-full px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Login
            </button>
          </form>
          <p className="mt-4 text-sm text-gray-400 text-center">
            Enter your agent token to access the dashboard
          </p>
        </>
      ) : (
        <>
          <h2 className="text-2xl font-bold text-white mb-6">Join with Invite</h2>
          <form onSubmit={handleInviteSignup}>
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Invite Code
              </label>
              <input
                type="text"
                value={inviteCode}
                onChange={(e) => setInviteCode(e.target.value)}
                placeholder="inv_..."
                className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Name
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your name"
                className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {status && (
              <div className={`mb-4 p-3 rounded text-sm ${
                status.type === 'error'
                  ? 'bg-red-500/10 border border-red-500/20 text-red-400'
                  : 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-400'
              }`}>
                {status.message}
              </div>
            )}

            <button
              type="submit"
              disabled={!inviteCode || !name || !email || loading}
              className="w-full px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Sending...' : 'Request Magic Link'}
            </button>
          </form>
          <p className="mt-4 text-sm text-gray-400 text-center">
            Need an invite? Contact the project maintainer.
          </p>
        </>
      )}
    </div>
  );
}
