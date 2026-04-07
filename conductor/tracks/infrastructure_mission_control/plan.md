# Implementation Plan: Infrastructure (Mission Control & CI/CD)

## Phase 1: Alerting & Monitoring
- [x] Task: Implement `DiscordNotifier`
    - [x] Created `trading/notifications/discord.py`.
    - [x] Wired into `CompositeNotifier` in `trading/api/app.py`.
- [x] Task: Intelligence Status API
    - [x] Exposed `IntelligenceLayer.get_status()` via `/v1/intelligence/status`.

## Phase 2: Frontend Mission Control
- [x] Task: Intelligence Dashboard Panel
    - [x] Created `IntelligencePanel.tsx` component.
    - [x] Integrated into `Dashboard.tsx`.
- [x] Task: Miner Ranking View
    - [x] Created `MinerLeaderboard.tsx` component.
    - [x] Integrated into `Dashboard.tsx`.

## Phase 3: CI/CD Pipeline
- [x] Task: Unified GitHub Action
    - [x] Created `.github/workflows/ci.yml`.
    - [x] Included `mypy` check for the `trading/` directory.
