// frontend/src/lib/api/arena.ts
import { api } from './client';

export interface ArenaGym {
  id: string;
  name: string;
  description: string;
  room_type: string;
  difficulty: number;
  xp_reward: number;
  max_turns: number;
  icon: string;
  challenge_count: number;
}

export interface ArenaChallenge {
  id: string;
  gym_id: string;
  name: string;
  description: string;
  difficulty: number;
  room_type: string;
  initial_state: Record<string, unknown>;
  tools: string[];
  max_turns: number;
  xp_reward: number;
  flag_hint?: string;
}

export interface ArenaSession {
  id: string;
  challenge_id: string;
  agent_id: string;
  current_state: string;
  inventory: string[];
  turn_count: number;
  score: number;
  status: 'in_progress' | 'completed' | 'failed';
  created_at: string;
  completed_at?: string;
  turns: ArenaTurn[];
}

export interface ArenaTurn {
  id: string;
  turn_number: number;
  tool_name: string;
  tool_input: Record<string, unknown>;
  tool_output: string;
  score_delta: number;
  created_at: string;
}

export interface StartSessionRequest {
  challenge_id: string;
  agent_id: string;
}

export interface ExecuteTurnRequest {
  tool_name: string;
  kwargs?: Record<string, unknown>;
}

export interface ExecuteTurnResult {
  id: string;
  turn_number: number;
  tool_name: string;
  tool_input: Record<string, unknown>;
  tool_output: string;
  score_delta: number;
  status: string;
}

export const arenaApi = {
  listGyms: () => api.get<ArenaGym[]>('/engine/v1/arena/gyms').then(res => res.data),
  getGym: (id: string) => api.get<ArenaGym>(`/engine/v1/arena/gyms/${id}`).then(res => res.data),

  listChallenges: (gymId?: string) => 
    api.get<ArenaChallenge[]>('/engine/v1/arena/challenges', { params: { gym_id: gymId } }).then(res => res.data),
  getChallenge: (id: string) => api.get<ArenaChallenge>(`/engine/v1/arena/challenges/${id}`).then(res => res.data),

  startSession: (body: StartSessionRequest) => 
    api.post<ArenaSession>('/engine/v1/arena/sessions', body).then(res => res.data),
  getSession: (id: string) => api.get<ArenaSession>(`/engine/v1/arena/sessions/${id}`).then(res => res.data),
  
  executeTurn: (sessionId: string, body: ExecuteTurnRequest) =>
    api.post<ExecuteTurnResult>(`/engine/v1/arena/sessions/${sessionId}/turns`, body).then(res => res.data),
};
