# API Routes Registration

This file documents all routes registered in `trading/api/app.py`.

## Route Registration Location

All routes are registered in the `create_app()` function at the end of `app.py` (lines ~2036-2095).

## Routes Registry

| Order | Router | Source | Path Prefix |
|-------|--------|--------|-------------|
| 1 | `health.router` | `api.routes.health` | `/health` |
| 2 | `accounts.router` | `api.routes.accounts` | - |
| 3 | `market_data.router` | `api.routes.market_data` | - |
| 4 | `orders.router` | `api.routes.orders` | - |
| 5 | `trades.router` | `api.routes.trades` | - |
| 6 | `agents.router` | `api.routes.agents` | - |
| 7 | `opportunities.router` | `api.routes.opportunities` | - |
| 8 | `risk.router` | `api.routes.risk` | - |
| 9 | `ws.router` | `api.routes.ws` | `/ws` |
| 10 | `analytics.router` | `api.routes.analytics` | - |
| 11 | `tuning.router` | `api.routes.tuning` | - |
| 12 | `strategy_analytics.router` | `api.routes.strategy_analytics` | - |
| 13 | `execution_analytics.router` | `api.routes.execution_analytics` | - |
| 14 | `experiments.router` | `api.routes.experiments` | - |
| 15 | `leaderboard_route.router` | `api.routes.leaderboard` | - |
| 16 | `journal_route.router` | `api.routes.journal` | - |
| 17 | `markets_browser.router` | `api.routes.markets_browser` | - |
| 18 | `portfolio_route.router` | `api.routes.portfolio` | - |
| 19 | `bittensor_route.router` | `api.routes.bittensor` | `/bittensor` |
| 20 | `competition_route.router` | `api.routes.competition` | - |
| 21 | `memory_router` | `api.routes.memory` | `/memory` |
| 22 | `confidence_analytics_route.router` | `api.routes.confidence_analytics` | - |
| 23 | `strategy_health_router` | `api.routes.strategy_health` | - |
| 24 | `signal_features_router` | `api.routes.signal_features` | - |
| 25 | `shadow_route.router` | `api.routes.shadow` | - |
| 26 | `intelligence_route.router` | `api.routes.intelligence` | `/intelligence` |
| 27 | `achievements_route.router` | `api.routes.achievements` | `/achievements` |
| 28 | `drafts.router` | `api.routes.drafts` | `/api/v1/drafts` |

## How to Add a New Route

1. Create your route file in `trading/api/routes/` (e.g., `myfeature.py`)
2. Define a router: `router = APIRouter()`
3. Add endpoints to the router
4. Import and register in `app.py`:

```python
# Add import at top of file
from api.routes import myfeature

# Add at end of create_app(), in order
app.include_router(myfeature.router)
```

## All Route Files

Full list in `trading/api/routes/`:
- achievements.py
- agents.py
- analytics.py
- arbitrage.py
- backtest.py
- bittensor.py
- bittensor_schemas.py
- brief.py
- competition.py
- competition_schemas.py
- confidence_analytics.py
- execution.py
- execution_analytics.py
- experiments.py
- health.py
- intelligence.py
- journal.py
- learning.py
- leaderboard.py
- market_data.py
- markets_browser.py
- memory.py
- opportunities.py
- orders.py
- portfolio.py
- regime.py
- risk.py
- shadow.py
- signal_features.py
- sizing.py
- strategy_analytics.py
- strategy_health.py
- test.py
- trades.py
- tuning.py
- warroom.py
- ws.py