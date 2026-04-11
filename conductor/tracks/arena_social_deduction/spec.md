# Specification: Arena & Social Deduction (AI Gamification & Monetization)

## 1. Objective
Transform the `ArenaGym` from a simple tool-calling framework into a highly-engaging, monetization-ready ecosystem. This track focuses on two core pillars:
1.  **Arena Betting UI:** A spectator-facing betting interface that enables users to wager "Agent XP" or tokens on the outcome of autonomous agent matches.
2.  **Social Deduction "Werewolf" Gym:** A specialized environment designed to test and progress an agent's "Theory of Mind," deception, and cooperative logic.

## 2. Architecture & Design

### A. Arena Betting System (Frontend & Backend)
- **Pool-based Odds:** Payouts are calculated based on the total pool vs. the individual wager (e.g., if 80% of the pool is on Player A, the payout for Player B is significantly higher).
- **Match View:** A real-time stream of agent "thoughts" (Neural Execution Stream) and "actions" (Tools called) to inform bettors.
- **Betting History:** Track user success/failure and leaderboard the "Top Bettors" for added social engagement.

### B. Social Deduction "Werewolf" Gym
- **Environment:** Multi-agent text-based game.
- **Roles:** Villager (Loyalist), Werewolf (Traitor), Seer (Inspector).
- **Phases:** 
    - `discussion`: Agents share (potentially untruthful) observations.
    - `vote`: Agents choose one player to eliminate.
    - `action`: Hidden roles (Seer/Werewolf) execute their specific powers.
- **Evaluation:** Success is measured by win-rate, bluffing accuracy, and "Theory of Mind" scores (did they accurately predict other agents' roles?).

## 3. Tech Stack
- **Backend:** Python 3.14 (FastAPI) for game engine logic and the `match_bets` table.
- **Frontend:** React 19 + TanStack Query for the betting interface.
- **Database:** PostgreSQL (with `pgvector` for agent memory tracking during social deduction).

## 4. Risks & Mitigations
- **Risk:** Agents colluding to "rig" betting outcomes.
- **Mitigation:** Implement strict "Proof of Non-Collusion" via separate agent instances and randomized environment seeds.
- **Risk:** "Stale" games that aren't engaging to watch.
- **Mitigation:** Use the "Neuro-Symbolic HUD" to highlight high-tension moments (e.g., "Agent X is lying with 85% confidence").
