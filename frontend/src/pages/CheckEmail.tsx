import React from 'react';
import { Link } from 'react-router-dom';

export default function CheckEmail() {
  return (
    <div className="min-h-screen bg-obsidian flex items-center justify-center p-6">
      <div className="neural-card-indigo max-w-md w-full p-10 text-center">
        <div className="w-20 h-20 bg-indigo-500/10 rounded-full flex items-center justify-center mx-auto mb-8 text-indigo-400">
          <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
        </div>
        
        <h1 className="text-3xl font-black text-white uppercase italic tracking-tight mb-4">Check your email</h1>
        <p className="text-gray-400 leading-relaxed mb-10">
          We've sent a magic link to your inbox. Use it to authenticate your session and enter the neural mesh.
        </p>

        <div className="space-y-4">
          <Link to="/login" className="block text-[10px] font-black text-gray-500 hover:text-white uppercase tracking-[0.3em] transition">
            &larr; Back to login
          </Link>
        </div>
      </div>
    </div>
  );
}
