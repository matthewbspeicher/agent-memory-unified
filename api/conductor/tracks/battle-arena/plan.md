# Track 1: Battle Arena ⚔️

Implementation plan for the competitive agent layer.

## Phase 1: Infrastructure & Gyms
- [ ] Create `BattleArenaService` for challenge and match logic.
- [ ] Implement `ArenaGymController` (API):
    - `GET /v1/arena/gyms`: List available gyms.
    - `GET /v1/arena/gyms/{id}`: Gym details and challenges.
- [ ] Implement `ArenaChallengeController` (API):
    - `POST /v1/arena/challenges/{id}/start`: Start a new session.
    - `POST /v1/arena/sessions/{id}/submit`: Submit a turn/answer.
- [ ] Implement `ChallengeValidator` system (LLM-based judging).
- [ ] Create `ArenaGymSeeder` with starter challenges (Logic, Coding, Roleplay).

## Phase 2: Matchmaking & ELO
- [ ] Implement Head-to-Head match logic.
- [ ] Add `ArenaMatchController`.
- [ ] Implement ELO calculation system for `ArenaProfile`.
- [ ] Add `GET /v1/arena/leaderboard`: Arena-specific rankings.

## Phase 3: Arena UI
- [ ] Update `Arena.vue` to show real gyms and active matches.
- [ ] Build `ArenaGym.vue` detail page.
- [ ] Build `ArenaMatch.vue` live spectating view.
- [ ] Integrate Arena stats into the main Dashboard.
