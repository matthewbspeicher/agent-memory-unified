# Implementation Plan: Arena & Social Deduction (AI Gamification & Monetization)

This plan outlines the steps for creating the Arena Betting system and the Social Deduction "Werewolf" Gym.

---

## Phase 1: Arena Betting Infrastructure & UI [ ]

The goal of this phase is to finalize the betting backend and create a high-fidelity frontend for users to place wagers.

- [x] **Task 1: Complete Backend Betting Logic** [ ]
    - Refine `match_bets` table and integrate into `competition/store.py`.
    - Implement payout calculation logic for pool-based betting.
    - Add `GET /sessions/bets/leaderboard` for top bettors.
- [x] **Task 2: Arena Betting Component (React)** [ ]
    - Create `ArenaBettingForm.tsx` with real-time odds calculation.
    - Implement `ArenaMatchStream.tsx` to visualize agent "neural thoughts" and actions.
    - Integrate with TanStack Query for live pool updates.
- [~] **Task 3: Match Result & Payout Distribution** [ ]
    - Implement automatic distribution of XP/tokens to winning bettors upon match completion.
    - Add visual feedback for "Win/Loss" in the user's betting history.

---

## Phase 2: Social Deduction "Werewolf" Gym [ ]

The goal of this phase is to implement a multi-agent environment that tests Theory of Mind and deception.

- [ ] **Task 4: Social Deduction Engine Core** [ ]
    - Create `competition/escape_rooms/werewolf.py` (inheriting from `EscapeRoomEnvironment`).
    - Define roles (Villager, Werewolf, Seer) and their specific toolsets (e.g., `vote`, `inspect`, `whisper`).
    - Implement turn-based phase management (`discussion`, `vote`, `night_action`).
- [ ] **Task 5: Deception & Theory of Mind (ToM) Evaluation** [ ]
    - Implement a "Lying Probability" estimator based on agent outputs vs. hidden state.
    - Add "ToM Score" calculation (how accurately an agent identifies other agents' hidden roles).
- [ ] **Task 6: Werewolf Challenge & Seeding** [ ]
    - Seed `arena_challenges` with the "AI Werewolf: The Traitor's Gambit" challenge.
    - Implement randomized role assignment and environment generation.

---

## Phase 3: Integration & Final Polish [ ]

Final verification and "spectator" experience tuning.

- [ ] **Task 7: Full Arena Flow Verification (E2E)** [ ]
    - Playwright tests for the betting -> match -> payout flow.
    - Verify "Theoretical vs. Actual" performance of the Werewolf agents.
- [ ] **Task 8: Production Readiness & Handoff** [ ]
    - Final security audit of the betting transactions.
    - Document the track in `conductor/index.md`.
    - Create final checkpoint.

---

## Quality Gates (Phase Completion)

Before marking any phase complete, the following criteria MUST be met:
- [ ] All unit tests pass with >80% coverage.
- [ ] Manual verification plan (MVP) confirmed by the user.
- [ ] UI is high-fidelity and matches the project's design tokens.
- [ ] Documentation updated in `tracks.md` and `plan.md` with commit SHAs.
