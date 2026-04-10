import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { arenaApi, ArenaChallenge, ArenaSession, ArenaTurn } from '../lib/api/arena';
import { GlassCard } from '../components/GlassCard';

type ToolSelectorProps = {
  tools: string[];
  onExecute: (toolName: string, kwargs: Record<string, unknown>) => void;
  isExecuting: boolean;
};

function ToolSelector({ tools, onExecute, isExecuting }: ToolSelectorProps) {
  const [selectedTool, setSelectedTool] = useState<string>('');
  const [kwargsInput, setKwargsInput] = useState('{}');

  const handleExecute = () => {
    if (!selectedTool) return;
    try {
      const kwargs = JSON.parse(kwargsInput || '{}');
      onExecute(selectedTool, kwargs);
    } catch {
      alert('Invalid JSON in arguments');
    }
  };

  const toolDescriptions: Record<string, { icon: string; desc: string; placeholder: string }> = {
    fs_read: { icon: '📄', desc: 'Read a file', placeholder: '{"path": "/home/user/flag.txt"}' },
    fs_list: { icon: '📁', desc: 'List directory', placeholder: '{"path": "/home/user"}' },
    exec_python: { icon: '🐍', desc: 'Run Python code', placeholder: '{"code": "print(1+1)"}' },
    submit_flag: { icon: '🏁', desc: 'Submit flag', placeholder: '{"flag": "FLAG{...}"}' },
    exec_bash: { icon: '💻', desc: 'Run bash command', placeholder: '{"command": "ls -la"}' },
    read_sql: { icon: '🗃️', desc: 'Query database', placeholder: '{"query": "SELECT * FROM users"}' },
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="text-[9px] text-gray-600 uppercase tracking-widest font-black block mb-2">
          Select Tool
        </label>
        <div className="flex flex-wrap gap-2">
          {tools.map((tool) => {
            const info = toolDescriptions[tool] || { icon: '🔧', desc: tool, placeholder: '{}' };
            return (
              <button
                key={tool}
                onClick={() => {
                  setSelectedTool(tool);
                  setKwargsInput(info.placeholder);
                }}
                className={`px-3 py-2 rounded-lg border text-sm font-mono transition-all ${
                  selectedTool === tool
                    ? 'bg-indigo-500/20 border-indigo-500/50 text-indigo-300'
                    : 'bg-gray-800/50 border-gray-700/50 text-gray-400 hover:border-gray-600'
                }`}
              >
                <span className="mr-2">{info.icon}</span>
                {tool}
              </button>
            );
          })}
        </div>
      </div>

      {selectedTool && (
        <>
          <div>
            <label className="text-[9px] text-gray-600 uppercase tracking-widest font-black block mb-2">
              Arguments (JSON)
            </label>
            <textarea
              value={kwargsInput}
              onChange={(e) => setKwargsInput(e.target.value)}
              className="w-full bg-gray-900/50 border border-gray-700/50 rounded-lg p-3 font-mono text-sm text-gray-300 focus:border-indigo-500/50 focus:outline-none"
              rows={3}
              placeholder='{"key": "value"}'
            />
          </div>
          <button
            onClick={handleExecute}
            disabled={isExecuting}
            className="neural-button-primary w-full disabled:opacity-50"
          >
            {isExecuting ? 'Executing...' : `Execute ${selectedTool}`}
          </button>
        </>
      )}
    </div>
  );
}

type TurnLogProps = {
  turns: ArenaTurn[];
};

function TurnLog({ turns }: TurnLogProps) {
  if (turns.length === 0) {
    return (
      <div className="text-gray-600 text-sm italic text-center py-8">
        No turns yet. Use a tool to begin.
      </div>
    );
  }

  return (
    <div className="space-y-3 max-h-[400px] overflow-y-auto">
      {turns.map((turn) => (
        <div
          key={turn.id}
          className={`p-3 rounded-lg border text-sm font-mono ${
            turn.score_delta > 0
              ? 'bg-emerald-500/10 border-emerald-500/20'
              : turn.score_delta < 0
              ? 'bg-rose-500/10 border-rose-500/20'
              : 'bg-gray-800/50 border-gray-700/50'
          }`}
        >
          <div className="flex justify-between items-center mb-2">
            <span className="text-gray-400">Turn {turn.turn_number}</span>
            <span className={turn.score_delta > 0 ? 'text-emerald-400' : turn.score_delta < 0 ? 'text-rose-400' : 'text-gray-500'}>
              {turn.score_delta > 0 ? '+' : ''}{turn.score_delta.toFixed(1)}
            </span>
          </div>
          <div className="text-indigo-400 mb-1">{turn.tool_name}</div>
          <pre className="text-gray-500 text-xs whitespace-pre-wrap break-all">
            {JSON.stringify(turn.tool_input)}
          </pre>
          <div className="mt-2 pt-2 border-t border-gray-700/50 text-gray-300 whitespace-pre-wrap">
            {turn.tool_output.length > 500 ? turn.tool_output.slice(0, 500) + '...' : turn.tool_output}
          </div>
        </div>
      ))}
    </div>
  );
}

type SessionViewProps = {
  session: ArenaSession;
  challenge: ArenaChallenge;
  onExecuteTurn: (toolName: string, kwargs: Record<string, unknown>) => void;
  isExecuting: boolean;
};

function SessionView({ session, challenge, onExecuteTurn, isExecuting }: SessionViewProps) {
  const isComplete = session.status === 'completed' || session.status === 'failed';
  const turnsRemaining = challenge.max_turns - session.turn_count;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 space-y-6">
        <GlassCard variant="cyan">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-sm font-black text-cyan-400 uppercase tracking-widest">Current State</h3>
            <div className="flex items-center gap-4">
              <span className={`text-xs font-mono px-2 py-1 rounded ${
                session.status === 'completed' ? 'bg-emerald-500/20 text-emerald-400' :
                session.status === 'failed' ? 'bg-rose-500/20 text-rose-400' :
                'bg-indigo-500/20 text-indigo-400'
              }`}>
                {session.status}
              </span>
              <span className="text-sm font-mono text-gray-400">
                Score: <span className="text-white font-bold">{session.score.toFixed(1)}</span>
              </span>
            </div>
          </div>
          <pre className="bg-gray-900/50 rounded-lg p-4 text-sm text-gray-300 whitespace-pre-wrap font-mono overflow-x-auto">
            {session.current_state}
          </pre>
        </GlassCard>

        <GlassCard variant="violet">
          <h3 className="text-sm font-black text-violet-400 uppercase tracking-widest mb-4">Turn History</h3>
          <TurnLog turns={session.turns || []} />
        </GlassCard>
      </div>

      <div className="space-y-6">
        <GlassCard variant="green">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-sm font-black text-emerald-400 uppercase tracking-widest">Session Stats</h3>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-[9px] text-gray-600 uppercase tracking-widest">Turns</div>
              <div className="text-2xl font-black font-mono text-white">
                {session.turn_count}<span className="text-gray-600 text-sm">/{challenge.max_turns}</span>
              </div>
            </div>
            <div>
              <div className="text-[9px] text-gray-600 uppercase tracking-widest">Remaining</div>
              <div className={`text-2xl font-black font-mono ${turnsRemaining <= 3 ? 'text-rose-400' : 'text-white'}`}>
                {turnsRemaining}
              </div>
            </div>
            <div>
              <div className="text-[9px] text-gray-600 uppercase tracking-widest">XP Reward</div>
              <div className="text-amber-400 font-mono font-black text-lg">{challenge.xp_reward}</div>
            </div>
            <div>
              <div className="text-[9px] text-gray-600 uppercase tracking-widest">Inventory</div>
              <div className="text-white font-mono text-lg">{session.inventory.length}</div>
            </div>
          </div>
        </GlassCard>

        {!isComplete && (
          <GlassCard variant="default">
            <h3 className="text-sm font-black text-gray-400 uppercase tracking-widest mb-4">Execute Tool</h3>
            <ToolSelector
              tools={challenge.tools}
              onExecute={onExecuteTurn}
              isExecuting={isExecuting}
            />
          </GlassCard>
        )}

        {isComplete && (
          <GlassCard variant={session.status === 'completed' ? 'green' : 'red'}>
            <div className="text-center py-4">
              <div className="text-4xl mb-4">
                {session.status === 'completed' ? '🎉' : '💀'}
              </div>
              <h3 className="text-xl font-black text-white mb-2">
                {session.status === 'completed' ? 'Challenge Complete!' : 'Challenge Failed'}
              </h3>
              <p className="text-gray-400 text-sm">
                Final Score: <span className="text-white font-bold">{session.score.toFixed(1)}</span>
              </p>
            </div>
          </GlassCard>
        )}
      </div>
    </div>
  );
}

type ChallengeSelectionProps = {
  challenges: ArenaChallenge[];
  onSelect: (challenge: ArenaChallenge) => void;
};

function ChallengeSelection({ challenges, onSelect }: ChallengeSelectionProps) {
  const getDifficultyColor = (diff: number) => {
    if (diff <= 1) return 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20';
    if (diff <= 2) return 'text-amber-400 bg-amber-500/10 border-amber-500/20';
    if (diff <= 3) return 'text-orange-400 bg-orange-500/10 border-orange-500/20';
    return 'text-rose-400 bg-rose-500/10 border-rose-500/20';
  };

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-black text-gray-500 uppercase tracking-[0.4em]">Select Challenge</h2>
      <div className="grid gap-4">
        {challenges.map((challenge) => (
          <div
            key={challenge.id}
            className="neural-card-indigo group !p-6 cursor-pointer"
            onClick={() => onSelect(challenge)}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <h3 className="text-lg font-black text-white">{challenge.name}</h3>
                  <span className={`text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded border ${getDifficultyColor(challenge.difficulty)}`}>
                    {'⭐'.repeat(challenge.difficulty)}
                  </span>
                </div>
                <p className="text-gray-400 text-sm italic">"{challenge.description}"</p>
              </div>
              <div className="shrink-0 text-right">
                <div className="text-amber-400 font-mono font-black">{challenge.xp_reward} XP</div>
                <div className="text-[9px] text-gray-600 uppercase tracking-widest">{challenge.max_turns} turns</div>
              </div>
            </div>
            <div className="flex gap-2 mt-3">
              {challenge.tools.map((tool) => (
                <span key={tool} className="text-[9px] font-mono px-2 py-0.5 rounded bg-gray-800 text-gray-500">
                  {tool}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ArenaEscapeRoom() {
  const { id: gymId } = useParams<{ id: string }>();
  const queryClient = useQueryClient();

  const [selectedChallenge, setSelectedChallenge] = useState<ArenaChallenge | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);

  const { data: challenges, isLoading: challengesLoading } = useQuery({
    queryKey: ['arena-challenges', gymId],
    queryFn: () => arenaApi.listChallenges(gymId),
    enabled: !!gymId,
  });

  const { data: session, isLoading: sessionLoading } = useQuery({
    queryKey: ['arena-session', sessionId],
    queryFn: () => arenaApi.getSession(sessionId!),
    enabled: !!sessionId,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data || data.status === 'in_progress') return 2000;
      return false;
    },
  });

  const startSessionMutation = useMutation({
    mutationFn: (challengeId: string) => 
      arenaApi.startSession({ challenge_id: challengeId, agent_id: 'user' }),
    onSuccess: (data) => {
      setSessionId(data.id);
      queryClient.invalidateQueries({ queryKey: ['arena-session', data.id] });
    },
  });

  const executeTurnMutation = useMutation({
    mutationFn: ({ toolName, kwargs }: { toolName: string; kwargs: Record<string, unknown> }) =>
      arenaApi.executeTurn(sessionId!, { tool_name: toolName, kwargs }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['arena-session', sessionId] });
    },
  });

  const handleStartChallenge = (challenge: ArenaChallenge) => {
    setSelectedChallenge(challenge);
    startSessionMutation.mutate(challenge.id);
  };

  const handleExecuteTurn = (toolName: string, kwargs: Record<string, unknown>) => {
    executeTurnMutation.mutate({ toolName, kwargs });
  };

  if (challengesLoading) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center text-gray-500 font-mono">
        Loading challenges...
      </div>
    );
  }

  return (
    <div>
      <Link
        to="/arena"
        className="text-sm text-gray-500 hover:text-gray-300 transition flex items-center gap-2 mb-8 uppercase tracking-widest font-bold"
      >
        &larr; Back to Arena
      </Link>

      {!sessionId && (
        <ChallengeSelection
          challenges={challenges || []}
          onSelect={handleStartChallenge}
        />
      )}

      {sessionId && session && selectedChallenge && (
        <>
          <div className="mb-6">
            <button
              onClick={() => {
                setSessionId(null);
                setSelectedChallenge(null);
              }}
              className="text-sm text-gray-500 hover:text-gray-300 transition mb-4"
            >
              &larr; Back to Challenges
            </button>
            <h1 className="text-2xl font-black text-white">{selectedChallenge.name}</h1>
            <p className="text-gray-400 italic">"{selectedChallenge.description}"</p>
          </div>

          {sessionLoading ? (
            <div className="text-gray-500 font-mono text-center py-12">Loading session...</div>
          ) : (
            <SessionView
              session={session}
              challenge={selectedChallenge}
              onExecuteTurn={handleExecuteTurn}
              isExecuting={executeTurnMutation.isPending}
            />
          )}
        </>
      )}

      {startSessionMutation.isError && (
        <div className="mt-4 p-4 bg-rose-500/10 border border-rose-500/20 rounded-lg text-rose-400 text-sm">
          Failed to start session: {(startSessionMutation.error as Error).message}
        </div>
      )}
    </div>
  );
}
