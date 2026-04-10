// frontend/src/lib/api/competition.ts
import { createApiClient } from './factory';
import { useQuery } from '@tanstack/react-query';

/**
 * Trading API client for Competition endpoints.
 * Uses /engine/v1 prefix for FastAPI trading engine.
 */
const getBaseUrl = () => {
  if (import.meta.env.DEV) {
    return '/engine/v1';
  }
  return import.meta.env.VITE_TRADING_API_URL 
    ? `${import.meta.env.VITE_TRADING_API_URL}/engine/v1`
    : 'http://localhost:8080/engine/v1';
};

const tradingApi = createApiClient(getBaseUrl());

// ── Types ──

export type CompetitorType = 'agent' | 'miner' | 'provider';
export type Tier = 'diamond' | 'gold' | 'silver' | 'bronze';
export type XpSource =
  | 'match_win_baseline'
  | 'match_win_pairwise'
  | 'streak_milestone'
  | 'achievement_common'
  | 'achievement_rare'
  | 'achievement_legendary'
  | 'tier_promotion'
  | 'sharpe_master'
  | 'diamond_maintenance';

export type AgentTrait =
  | 'genesis'
  | 'risk_manager'
  | 'tail_hedged'
  | 'trend_follower'
  | 'momentum'
  | 'breakout'
  | 'mean_reversion'
  | 'range_bound'
  | 'statistical'
  | 'cointegration'
  | 'kalman_filter';

export interface TraitInfo {
  trait: AgentTrait;
  icon: string;
  name: string;
  effect: string;
  required_level: number;
  parent: AgentTrait | null;
  unlocked: boolean;
}

export interface TraitsResponse {
  competitor_id: string;
  unlocked_traits: AgentTrait[];
  trait_tree: TraitInfo[];
}

export interface TraitLoadout {
  competitor_id: string;
  asset: string;
  primary: AgentTrait | null;
  secondary: AgentTrait | null;
  tertiary: AgentTrait | null;
}

export interface EquipTraitResponse {
  loadout: TraitLoadout;
  equipped: boolean;
  message: string | null;
}

// ── Agent Card Types ──

export type CardRarity = 'common' | 'uncommon' | 'rare' | 'epic' | 'legendary';

export interface CardStats {
  matches: number;
  wins: number;
  losses: number;
  win_rate: number;
  current_streak: number;
  best_streak: number;
  total_xp: number;
  achievement_count: number;
  traits_unlocked: number;
  calibration_score: number;
}

export interface AgentCard {
  competitor_id: string;
  name: string;
  level: number;
  tier: Tier;
  elo: number;
  rarity: CardRarity;
  stats: CardStats;
  trait_icons: string[];
  achievement_badges: { type: string; name: string; tier: string }[];
  card_version: string;
}

export interface FleetStats {
  total_agents: number;
  avg_level: number;
  total_xp: number;
  total_matches: number;
  avg_elo: number;
  legendary_count: number;
  mission_claimable: number;
}

export interface FleetResponse {
  stats: FleetStats;
  cards: AgentCard[];
}

export type MissionType = 'daily' | 'weekly';

export type MissionId =
  | 'warm_up'
  | 'streak_starter'
  | 'sharpe_hunter'
  | 'weekly_grind'
  | 'streak_master'
  | 'achievement_hunter';

export interface Mission {
  id: string;
  mission_id: MissionId;
  name: string;
  description: string;
  icon: string;
  mission_type: MissionType;
  progress: number;
  target: number;
  progress_pct: number;
  completed: boolean;
  claimed: boolean;
  xp_reward: number;
  is_claimable: boolean;
  period_end: string;
}

export interface MissionsResponse {
  missions: Mission[];
}

export interface ClaimMissionResponse {
  success: boolean;
  xp_awarded: number;
  message: string;
}

export interface Competitor {
  id: string;
  type: CompetitorType;
  name: string;
  ref_id: string;
  status: string;
  elo: number;
  tier: Tier;
  matches_count: number;
  streak: number;
  best_streak: number;
  xp: number;
  level: number;
}

export interface LeaderboardResponse {
  leaderboard: Competitor[];
  competitor_count: number;
}

export interface DashboardSummary {
  leaderboard: Competitor[];
  competitor_count: number;
}

export interface EloHistoryPoint {
  elo: number;
  tier: string;
  elo_delta: number;
  recorded_at: string;
}

export interface CompetitorDetail {
  id: string;
  type: CompetitorType;
  name: string;
  ref_id: string;
  status: string;
  metadata: Record<string, unknown>;
  ratings: Record<string, { elo: number; xp?: number; level?: number }>;
  calibration_score: number;
}

export interface HeadToHeadResponse {
  competitor_a: Record<string, unknown>;
  competitor_b: Record<string, unknown>;
  wins_a: number;
  wins_b: number;
  draws: number;
  total_matches: number;
}

export interface XpHistoryPoint {
  id: string;
  source: XpSource;
  amount: number;
  created_at: string;
}

export interface XpResponse {
  competitor_id: string;
  asset: string;
  xp: number;
  level: number;
  xp_to_next_level: number;
}

export interface XpHistoryResponse {
  competitor_id: string;
  asset: string;
  history: XpHistoryPoint[];
}

// ── API Functions ──

export const competitionApi = {
  getDashboardSummary: (asset = 'BTC') =>
    tradingApi.get<DashboardSummary>('/dashboard/summary', { params: { asset } })
      .then(res => res.data),

  getLeaderboard: (params: { asset?: string; type?: string; limit?: number; offset?: number } = {}) =>
    tradingApi.get<LeaderboardResponse>('/leaderboard', { params })
      .then(res => res.data),

  getCompetitor: (id: string) =>
    tradingApi.get<CompetitorDetail>(`/competitors/${id}`)
      .then(res => res.data),

  getEloHistory: (id: string, asset = 'BTC', days = 30) =>
    tradingApi.get<{ competitor_id: string; asset: string; history: EloHistoryPoint[] }>(
      `/competitors/${id}/elo-history`,
      { params: { asset, days } },
    ).then(res => res.data),

  getHeadToHead: (a: string, b: string, asset = 'BTC') =>
    tradingApi.get<HeadToHeadResponse>(`/head-to-head/${a}/${b}`, { params: { asset } })
      .then(res => res.data),

  getXp: (id: string, asset = 'BTC') =>
    tradingApi.get<XpResponse>(`/competitors/${id}/xp`, { params: { asset } })
      .then(res => res.data),

  getXpHistory: (id: string, asset = 'BTC', limit = 50) =>
    tradingApi.get<XpHistoryResponse>(`/competitors/${id}/xp/history`, { params: { asset, limit } })
      .then(res => res.data),

  getTraits: (id: string, asset = 'BTC') =>
    tradingApi.get<TraitsResponse>(`/competitors/${id}/traits`, { params: { asset } })
      .then(res => res.data),

  getLoadout: (id: string, asset = 'BTC') =>
    tradingApi.get<TraitLoadout>(`/competitors/${id}/loadout`, { params: { asset } })
      .then(res => res.data),

  equipTrait: (id: string, trait: AgentTrait, asset = 'BTC') =>
    tradingApi.post<EquipTraitResponse>(`/competitors/${id}/loadout/equip`, { trait }, { params: { asset } })
      .then(res => res.data),

  unequipTrait: (id: string, trait: AgentTrait, asset = 'BTC') =>
    tradingApi.post<EquipTraitResponse>(`/competitors/${id}/loadout/unequip`, { trait }, { params: { asset } })
      .then(res => res.data),

  getAgentCard: (id: string, asset = 'BTC') =>
    tradingApi.get<AgentCard>(`/competitors/${id}/card`, { params: { asset } })
      .then(res => res.data),

  getFleet: (asset = 'BTC') =>
    tradingApi.get<FleetResponse>('/fleet', { params: { asset } })
      .then(res => res.data),

  getMissions: (id: string, missionType?: MissionType, asset = 'BTC') =>
    tradingApi.get<MissionsResponse>(`/competitors/${id}/missions`, {
      params: { asset, mission_type: missionType },
    }).then(res => res.data),

  claimMission: (id: string, missionId: MissionId, asset = 'BTC') =>
    tradingApi.post<ClaimMissionResponse>(`/competitors/${id}/missions/${missionId}/claim`, {}, {
      params: { asset },
    }).then(res => res.data),

  getSeasons: () =>
    tradingApi.get<SeasonsResponse>('/seasons').then(res => res.data),

  getSeasonLeaderboard: (seasonId: string, limit = 50) =>
    tradingApi.get<SeasonLeaderboard>(`/seasons/${seasonId}/leaderboard`, { params: { limit } })
      .then(res => res.data),
};

// ── TanStack Query Hooks ──

export function useLeaderboard(asset = 'BTC', type?: string) {
  return useQuery({
    queryKey: ['competition', 'leaderboard', asset, type],
    queryFn: () => competitionApi.getLeaderboard({ asset, type }),
    refetchInterval: 30_000,
  });
}

export function useDashboardSummary(asset = 'BTC') {
  return useQuery({
    queryKey: ['competition', 'dashboard', asset],
    queryFn: () => competitionApi.getDashboardSummary(asset),
    refetchInterval: 30_000,
  });
}

export function useCompetitor(id: string) {
  return useQuery({
    queryKey: ['competition', 'competitor', id],
    queryFn: () => competitionApi.getCompetitor(id),
    enabled: !!id,
  });
}

export function useEloHistory(id: string, asset = 'BTC', days = 30) {
  return useQuery({
    queryKey: ['competition', 'elo-history', id, asset, days],
    queryFn: () => competitionApi.getEloHistory(id, asset, days),
    enabled: !!id,
  });
}

export function useHeadToHead(a: string, b: string, asset = 'BTC') {
  return useQuery({
    queryKey: ['competition', 'h2h', a, b, asset],
    queryFn: () => competitionApi.getHeadToHead(a, b, asset),
    enabled: !!a && !!b,
  });
}

export function useMetaLearnerStatus() {
  return useQuery({
    queryKey: ['competition', 'meta-learner'],
    queryFn: () => tradingApi.get('/meta-learner/status').then(res => res.data),
    refetchInterval: 60_000,
  });
}

export function useXp(id: string, asset = 'BTC') {
  return useQuery({
    queryKey: ['competition', 'xp', id, asset],
    queryFn: () => competitionApi.getXp(id, asset),
    enabled: !!id,
  });
}

export function useXpHistory(id: string, asset = 'BTC', limit = 50) {
  return useQuery({
    queryKey: ['competition', 'xp-history', id, asset, limit],
    queryFn: () => competitionApi.getXpHistory(id, asset, limit),
    enabled: !!id,
  });
}

export function useTraits(id: string, asset = 'BTC') {
  return useQuery({
    queryKey: ['competition', 'traits', id, asset],
    queryFn: () => competitionApi.getTraits(id, asset),
    enabled: !!id,
  });
}

export function useLoadout(id: string, asset = 'BTC') {
  return useQuery({
    queryKey: ['competition', 'loadout', id, asset],
    queryFn: () => competitionApi.getLoadout(id, asset),
    enabled: !!id,
  });
}

export function useAgentCard(id: string, asset = 'BTC') {
  return useQuery({
    queryKey: ['competition', 'card', id, asset],
    queryFn: () => competitionApi.getAgentCard(id, asset),
    enabled: !!id,
  });
}

export function useFleet(asset = 'BTC') {
  return useQuery({
    queryKey: ['competition', 'fleet', asset],
    queryFn: () => competitionApi.getFleet(asset),
    refetchInterval: 30_000,
  });
}

export function useMissions(id: string, missionType?: MissionType, asset = 'BTC') {
  return useQuery({
    queryKey: ['competition', 'missions', id, missionType, asset],
    queryFn: () => competitionApi.getMissions(id, missionType, asset),
    enabled: !!id,
  });
}

// ── Season Types ──

export type SeasonStatus = 'active' | 'ended' | 'upcoming';

export interface Season {
  id: string;
  number: number;
  name: string;
  status: SeasonStatus;
  started_at: string;
  ends_at: string;
  days_remaining: number;
  total_participants: number;
  your_rank: number | null;
  your_rating: number;
}

export interface SeasonLeaderboard {
  season_id: string;
  leaderboard: {
    rank: number;
    competitor_id: string;
    name: string;
    elo: number;
    tier: string;
    matches: number;
  }[];
}

export interface SeasonsResponse {
  current: Season | null;
  seasons: Season[];
}

// ── Season Hooks ──

export function useSeasons() {
  return useQuery({
    queryKey: ['competition', 'seasons'],
    queryFn: () => competitionApi.getSeasons(),
    refetchInterval: 60_000,
  });
}

export function useSeasonLeaderboard(seasonId: string, limit = 50) {
  return useQuery({
    queryKey: ['competition', 'season-leaderboard', seasonId, limit],
    queryFn: () => competitionApi.getSeasonLeaderboard(seasonId, limit),
    enabled: !!seasonId,
  });
}

// ── Betting Types ──

export type BetStatus = 'open' | 'locked' | 'settled' | 'cancelled';

export interface BetPlacement {
  predicted_winner: string;
  amount: number;
}

export interface Bet {
  id: string;
  match_id: string;
  predicted_winner: string;
  amount: number;
  potential_payout: number;
  status: BetStatus;
  created_at: string;
  payout?: number;
}

export interface BettingPool {
  match_id: string;
  total_pool: number;
  competitor_a_pool: number;
  competitor_b_pool: number;
  competitor_a_bettors: number;
  competitor_b_bettors: number;
  competitor_a_odds: number;
  competitor_b_odds: number;
  status: BetStatus;
}

export interface BetResult {
  match_id: string;
  winner: string;
  total_pool: number;
  house_cut: number;
  distributed: number;
  settled_bets: number;
}

// ── Betting API ──

export const bettingApi = {
  getPool: (matchId: string) =>
    tradingApi.get<BettingPool>(`/matches/${matchId}/pool`).then(res => res.data),

  placeBet: (matchId: string, bet: BetPlacement) =>
    tradingApi.post<Bet>(`/matches/${matchId}/bet`, bet).then(res => res.data),

  getBets: (matchId: string) =>
    tradingApi.get<Bet[]>(`/matches/${matchId}/bets`).then(res => res.data),

  settleMatch: (matchId: string, winnerId: string) =>
    tradingApi.post<BetResult>(`/matches/${matchId}/settle`, null, {
      params: { winner_id: winnerId },
    }).then(res => res.data),
};

export function useBettingPool(matchId: string) {
  return useQuery({
    queryKey: ['competition', 'pool', matchId],
    queryFn: () => bettingApi.getPool(matchId),
    enabled: !!matchId,
    refetchInterval: 10_000,
  });
}

export function useMatchBets(matchId: string) {
  return useQuery({
    queryKey: ['competition', 'bets', matchId],
    queryFn: () => bettingApi.getBets(matchId),
    enabled: !!matchId,
  });
}

// ── Evolution Types ──

export type MutationRarity = 'common' | 'uncommon' | 'rare' | 'legendary';

export interface Mutation {
  id: string;
  trait: AgentTrait;
  rarity: MutationRarity;
  bonus_multiplier: number;
  level_obtained: number;
}

export interface Lineage {
  agent_id: string;
  parent_a_id: string | null;
  parent_b_id: string | null;
  generation: number;
  breeding_count: number;
  can_breed: boolean;
  mutations: Mutation[];
}

export interface BreedRequest {
  parent_a_id: string;
  parent_b_id: string;
  child_name: string;
}

export interface BreedResult {
  child_id: string;
  child_name: string;
  inherited_traits: AgentTrait[];
  mutated_trait: AgentTrait | null;
  mutation_rarity: MutationRarity | null;
  generation: number;
}

// ── Evolution API ──

export const evolutionApi = {
  getMutations: (agentId: string) =>
    tradingApi.get<Mutation[]>(`/competitors/${agentId}/mutations`).then(res => res.data),

  getLineage: (agentId: string) =>
    tradingApi.get<Lineage>(`/competitors/${agentId}/lineage`).then(res => res.data),

  breed: (request: BreedRequest) =>
    tradingApi.post<BreedResult>('/breed', request).then(res => res.data),
};

export function useMutations(agentId: string) {
  return useQuery({
    queryKey: ['competition', 'mutations', agentId],
    queryFn: () => evolutionApi.getMutations(agentId),
    enabled: !!agentId,
  });
}

export function useLineage(agentId: string) {
  return useQuery({
    queryKey: ['competition', 'lineage', agentId],
    queryFn: () => evolutionApi.getLineage(agentId),
    enabled: !!agentId,
  });
}
