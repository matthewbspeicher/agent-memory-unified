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
}

export interface ArenaMatch {
  id: string;
  status: 'pending' | 'in_progress' | 'completed';
  opponent_id: string;
  winner_id?: string;
  created_at: string;
}

export const arenaApi = {
  getProfile: () => api.get<{ data: ArenaProfile }>('/v1/arena/profile'),
  listGyms: () => api.get<{ data: ArenaGym[] }>('/v1/arena/gyms'),
  listMatches: () => api.get<{ data: ArenaMatch[] }>('/v1/arena/matches'),
  requestMatch: () => api.post<{ data: ArenaMatch }>('/v1/arena/matches/request'),
};
