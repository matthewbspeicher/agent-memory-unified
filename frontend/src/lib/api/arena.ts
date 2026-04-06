import { api } from './client';

export interface ArenaProfile {
  agent_id: string;
  rating: number;
  rank?: number;
  matches_played: number;
  wins: number;
  losses: number;
  draws: number;
}

export interface ArenaGym {
  id: string;
  name: string;
  description: string;
  difficulty: 'easy' | 'medium' | 'hard' | 'expert';
  category: string;
  is_official: boolean;
  challenges_count?: number;
}

export interface ArenaChallenge {
  id: string;
  gym_id: string;
  title: string;
  prompt: string;
  difficulty_level: string;
  xp_reward: number;
  max_turns: number;
}

export interface ArenaSessionTurn {
  id: string;
  session_id: string;
  turn_number: number;
  input: string;
  output: string | null;
  validator_response: {
    score: number;
    feedback: string;
  } | null;
  score: number;
  feedback: string | null;
}

export interface ArenaSession {
  id: string;
  agent_id: string;
  challenge_id: string;
  match_id: string | null;
  status: 'in_progress' | 'completed' | 'abandoned';
  score: number | null;
  turns?: ArenaSessionTurn[];
}

import type { Agent } from '../../../../shared/types/generated/typescript/index';

export interface ArenaMatchDetail {
  id: string;
  status: 'pending' | 'in_progress' | 'completed';
  agent_1_id: string;
  agent_2_id: string;
  winner_id: string | null;
  score_1: number | null;
  score_2: number | null;
  judge_feedback: string | null;
  challenge: ArenaChallenge;
  agent1: Agent;
  agent2: Agent;
  winner: Agent | null;
  sessions?: ArenaSession[];
  created_at: string;
}

export interface ArenaMatchSummary {
  id: string;
  status: 'pending' | 'in_progress' | 'completed';
  opponent_id: string;
  winner_id?: string;
  created_at: string;
}

export interface ArenaGymDetail extends ArenaGym {
  challenges: ArenaChallenge[];
}

export const arenaApi = {
  getProfile: () => api.get<{ data: ArenaProfile }>('/v1/arena/profile'),
  listGyms: () => api.get<{ data: ArenaGym[] }>('/v1/arena/gyms'),
  getGym: (id: string) => api.get<{ data: ArenaGymDetail }>('/v1/arena/gyms/' + id),
  listMatches: () => api.get<{ data: ArenaMatchSummary[] }>('/v1/arena/matches'),
  getMatch: (id: string) => api.get<{ data: ArenaMatchDetail }>('/v1/arena/matches/' + id),
  requestMatch: () => api.post<{ data: ArenaMatchDetail }>('/v1/arena/matches/request'),
};
