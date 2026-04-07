# Specification: Infrastructure (Mission Control & CI/CD)

Complete the mission-critical infrastructure, including the frontend dashboard, alerting system, and automated pipeline.

## Problem Statement
The engine is intelligent, but visibility and operational safety are still limited. We need real-time monitoring via the dashboard, automated trade alerts via Discord, and a robust CI/CD pipeline to prevent regressions.

## Objectives
- **Mission Control Dashboard**: Implement high-fidelity panels for strategy health, miner rankings, and intelligence enrichment logs.
- **Discord Alerting**: Wire real-time trade events (Open/Close/Veto) to a Discord webhook.
- **CI/CD Pipeline**: Create a GitHub Actions workflow that runs tests, linting, and `mypy` type checks.

## Key Requirements

### 1. Dashboard Enhancements
- Build `IntelligencePanel.tsx` to show real-time enrichments and vetos.
- Build `MinerLeaderboard.tsx` using the `bittensor_miner_rankings` table.
- Integrate 3D visualization for the Vector Memory space (if feasible).

### 2. Alerting System
- Implement `DiscordNotifier` in `trading/notifications/`.
- Configure webhook URL via `STA_DISCORD_WEBHOOK_URL`.

### 3. CI/CD Pipeline
- Configure `.github/workflows/ci.yml`.
- Steps: Setup PHP/Python/Node, Run Pest (API), Run Pytest (Trading) + mypy, Run Vitest (Frontend).

## Success Criteria
- [ ] Discord receives a message when a trade is opened in paper mode.
- [ ] The dashboard shows active miner rankings and intelligence stats.
- [ ] CI pipeline passes on the next push.
