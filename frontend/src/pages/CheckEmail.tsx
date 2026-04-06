import { Link } from 'react-router-dom';
import { GlassCard } from '../components/GlassCard';

export default function CheckEmail() {
  return (
    <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center p-4 font-mono relative overflow-hidden">
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-violet-900/20 blur-[100px] rounded-full pointer-events-none" />

      <GlassCard variant="violet" className="w-full max-w-md !p-0 z-10 shadow-[0_0_30px_rgba(167,139,250,0.15)] text-center">
        <div className="bg-slate-950/80 px-4 py-3 border-b border-violet-900/50 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 bg-violet-400 rounded-full animate-pulse"></span>
            <span className="text-xs text-violet-500 tracking-widest font-bold">SECURE_COMM_CHANNEL</span>
          </div>
        </div>

        <div className="p-10">
          <div className="w-20 h-20 bg-violet-500/10 border border-violet-500/30 rounded-full flex items-center justify-center mx-auto mb-8 text-violet-400 shadow-[0_0_20px_rgba(167,139,250,0.3)]">
            <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
          </div>
          
          <h1 className="text-2xl font-black text-white uppercase tracking-widest mb-4 drop-shadow-[0_0_10px_rgba(167,139,250,0.8)]">Uplink Established</h1>
          <p className="text-slate-400 text-sm leading-relaxed mb-10">
            A magic link has been dispatched to your inbox. Await the transmission to authenticate your session and enter the Neural Mesh.
          </p>

          <Link to="/login" className="inline-block text-xs font-bold text-violet-500 hover:text-violet-400 hover:shadow-[0_0_10px_rgba(167,139,250,0.4)] uppercase tracking-[0.2em] transition-all px-6 py-2 border border-transparent hover:border-violet-500/30 rounded bg-transparent hover:bg-violet-500/5">
            &lt; Return_To_Terminal
          </Link>
        </div>
      </GlassCard>
    </div>
  );
}
