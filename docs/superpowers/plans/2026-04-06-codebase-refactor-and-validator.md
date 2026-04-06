# Codebase Refactor & Bittensor Validator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up 50 identified issues across the Agent Memory Commons monorepo while simultaneously deploying a live Bittensor Subnet 8 validator on WSL2.

**Architecture:** Service-by-service refactoring (Shared/Infra → Trading → API → Frontend) with a parallel infrastructure track for the Bittensor validator. Each phase produces independently deployable results.

**Tech Stack:** PHP 8.3 / Laravel 12, Python 3.13 / FastAPI, React 19 / Vite / TanStack Query, PostgreSQL 16 + pgvector, Redis 7, Bittensor SDK 8+, Docker Compose, GitHub Actions CI

**Spec:** `docs/superpowers/specs/2026-04-06-codebase-review-and-validator-design.md`

---

## Track A: Bittensor Validator on WSL2

> This track is fully independent of Track B. It can be executed in parallel on the WSL2 machine.

### Task A1: Install Bittensor CLI & Dependencies on WSL2

**Files:**
- Create: `~/.bittensor/` (wallet storage, created by btcli)

- [ ] **Step 1: Install system dependencies**

```bash
sudo apt update && sudo apt install -y python3 python3-pip python3-venv build-essential git curl
```

- [ ] **Step 2: Install Bittensor CLI**

```bash
pip3 install bittensor
```

- [ ] **Step 3: Verify installation**

```bash
btcli --version
```

Expected: `btcli version X.Y.Z` (8.0.0+)

- [ ] **Step 4: Test chain connectivity**

```bash
btcli subnet list --netuid 8 --subtensor.network finney
```

Expected: Table showing Subnet 8 details (name, tempo, emission, etc.)

---

### Task A2: Create Wallet (Coldkey + Hotkey)

**Files:**
- Create: `~/.bittensor/wallets/sta_wallet/` (created by btcli)

- [ ] **Step 1: Create coldkey**

```bash
btcli wallet new_coldkey --wallet.name sta_wallet
```

**CRITICAL:** Write down the 12-word mnemonic on paper. This controls your TAO. Never store it digitally.

- [ ] **Step 2: Create hotkey**

```bash
btcli wallet new_hotkey --wallet.name sta_wallet --wallet.hotkey sta_hotkey
```

Write down this mnemonic too (less critical but still important).

- [ ] **Step 3: Display wallet addresses**

```bash
btcli wallet overview --wallet.name sta_wallet
```

Expected: Table showing coldkey SS58 address (starts with `5`) and hotkey SS58 address. Copy the **coldkey SS58 address** — you'll need it for the Kraken withdrawal.

---

### Task A3: Fund Wallet & Register on Subnet 8

- [ ] **Step 1: Withdraw TAO from Kraken**

On Kraken:
1. Go to Withdraw → TAO (Bittensor)
2. Paste your coldkey SS58 address as the destination
3. Submit withdrawal
4. Wait for confirmation (usually 5-15 minutes)

- [ ] **Step 2: Verify balance on-chain**

```bash
btcli wallet balance --wallet.name sta_wallet --subtensor.network finney
```

Expected: Shows your TAO balance on the coldkey.

- [ ] **Step 3: Register hotkey on Subnet 8**

```bash
btcli subnet register --netuid 8 --wallet.name sta_wallet --wallet.hotkey sta_hotkey --subtensor.network finney
```

This costs a registration fee (~0.1 TAO, varies). Confirm when prompted.

- [ ] **Step 4: Verify registration**

```bash
btcli wallet overview --wallet.name sta_wallet --subtensor.network finney
```

Expected: Shows your hotkey registered on netuid 8.

- [ ] **Step 5: Stake TAO to your hotkey**

```bash
btcli stake add --wallet.name sta_wallet --wallet.hotkey sta_hotkey --amount <AMOUNT> --subtensor.network finney
```

Stake as much as you're comfortable with. More stake = more validator weight = more rewards.

- [ ] **Step 6: Verify stake**

```bash
btcli wallet overview --wallet.name sta_wallet --subtensor.network finney
```

Expected: Shows staked amount next to your hotkey.

---

### Task A4: Implement Weight-Setting (CRITICAL — Missing from Codebase)

**Files:**
- Create: `trading/integrations/bittensor/weight_setter.py`
- Create: `trading/tests/unit/test_integrations/test_bittensor_weight_setter.py`
- Modify: `trading/api/startup/integrations.py:108-221`

- [ ] **Step 1: Write the failing test**

```python
# trading/tests/unit/test_integrations/test_bittensor_weight_setter.py
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from integrations.bittensor.weight_setter import WeightSetter
from integrations.bittensor.models import MinerRanking


def _make_ranking(hotkey: str, hybrid_score: float, uid: int) -> MinerRanking:
    return MinerRanking(
        miner_hotkey=hotkey,
        windows_evaluated=100,
        direction_accuracy=0.6,
        mean_magnitude_error=0.01,
        mean_path_correlation=0.5,
        internal_score=0.7,
        latest_incentive_score=0.1,
        hybrid_score=hybrid_score,
        alpha_used=0.5,
        updated_at=datetime.now(tz=timezone.utc),
    )


class TestWeightSetter:
    def test_normalize_scores_to_weights(self):
        """Hybrid scores should normalize to weights summing to 1.0."""
        setter = WeightSetter(
            adapter=MagicMock(),
            store=MagicMock(),
            netuid=8,
            interval_blocks=100,
        )
        rankings = [
            _make_ranking("hk_a", 0.8, 0),
            _make_ranking("hk_b", 0.6, 1),
            _make_ranking("hk_c", 0.2, 2),
        ]
        hotkey_to_uid = {"hk_a": 0, "hk_b": 1, "hk_c": 2}

        uids, weights = setter.compute_weight_vector(rankings, hotkey_to_uid)

        assert len(uids) == 3
        assert len(weights) == 3
        assert abs(sum(weights) - 1.0) < 1e-6
        # Highest hybrid_score should get highest weight
        assert weights[uids.index(0)] > weights[uids.index(1)]
        assert weights[uids.index(1)] > weights[uids.index(2)]

    def test_empty_rankings_returns_empty(self):
        setter = WeightSetter(
            adapter=MagicMock(),
            store=MagicMock(),
            netuid=8,
            interval_blocks=100,
        )
        uids, weights = setter.compute_weight_vector([], {})
        assert uids == []
        assert weights == []

    def test_single_miner_gets_full_weight(self):
        setter = WeightSetter(
            adapter=MagicMock(),
            store=MagicMock(),
            netuid=8,
            interval_blocks=100,
        )
        rankings = [_make_ranking("hk_a", 0.9, 0)]
        uids, weights = setter.compute_weight_vector(rankings, {"hk_a": 0})
        assert uids == [0]
        assert abs(weights[0] - 1.0) < 1e-6

    @pytest.mark.asyncio
    async def test_set_weights_calls_subtensor(self):
        mock_adapter = MagicMock()
        mock_subtensor = MagicMock()
        mock_wallet = MagicMock()
        mock_adapter._subtensor = mock_subtensor
        mock_adapter._wallet = mock_wallet

        mock_metagraph = MagicMock()
        mock_metagraph.hotkeys = ["hk_a", "hk_b"]
        mock_metagraph.uids = [0, 1]
        mock_adapter._metagraph = mock_metagraph

        mock_store = AsyncMock()
        mock_store.get_miner_rankings = AsyncMock(return_value=[
            _make_ranking("hk_a", 0.8, 0),
            _make_ranking("hk_b", 0.4, 1),
        ])

        mock_subtensor.set_weights = MagicMock(return_value=(True, "ok"))

        setter = WeightSetter(
            adapter=mock_adapter,
            store=mock_store,
            netuid=8,
            interval_blocks=100,
        )

        success = await setter.set_weights_once()

        assert success is True
        mock_subtensor.set_weights.assert_called_once()
        call_kwargs = mock_subtensor.set_weights.call_args
        assert call_kwargs is not None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd trading && python -m pytest tests/unit/test_integrations/test_bittensor_weight_setter.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'integrations.bittensor.weight_setter'`

- [ ] **Step 3: Implement WeightSetter**

```python
# trading/integrations/bittensor/weight_setter.py
from __future__ import annotations

import asyncio
import logging
from typing import Any

from integrations.bittensor.models import MinerRanking

logger = logging.getLogger(__name__)


class WeightSetter:
    """Periodically sets on-chain weights based on miner rankings.

    Validators must call subtensor.set_weights() to score miners.
    This determines miner incentive distribution and validator rewards.
    """

    def __init__(
        self,
        adapter: Any,
        store: Any,
        netuid: int = 8,
        interval_blocks: int = 100,
        min_rankings: int = 5,
    ) -> None:
        self._adapter = adapter
        self._store = store
        self._netuid = netuid
        self._interval_blocks = interval_blocks
        self._min_rankings = min_rankings
        self._running = False
        self.last_set_at_block: int | None = None
        self.total_weight_sets: int = 0

    def compute_weight_vector(
        self,
        rankings: list[MinerRanking],
        hotkey_to_uid: dict[str, int],
    ) -> tuple[list[int], list[float]]:
        """Convert miner rankings to normalized (uids, weights) vectors.

        Maps hybrid_score to weights that sum to 1.0.
        Only includes miners present in both rankings and metagraph.
        """
        if not rankings:
            return [], []

        # Filter to miners present in metagraph
        valid = [
            (hotkey_to_uid[r.miner_hotkey], r.hybrid_score)
            for r in rankings
            if r.miner_hotkey in hotkey_to_uid and r.hybrid_score > 0
        ]

        if not valid:
            return [], []

        uids = [uid for uid, _ in valid]
        scores = [score for _, score in valid]

        # Normalize to sum to 1.0
        total = sum(scores)
        if total <= 0:
            return [], []

        weights = [s / total for s in scores]
        return uids, weights

    async def set_weights_once(self) -> bool:
        """Compute and set weights on-chain once.

        Returns True if weights were successfully set.
        """
        metagraph = self._adapter.metagraph
        if metagraph is None:
            logger.warning("WeightSetter: metagraph not loaded, skipping")
            return False

        # Build hotkey→uid map from metagraph
        hotkey_to_uid: dict[str, int] = {
            hk: uid for uid, hk in zip(metagraph.uids, metagraph.hotkeys)
        }

        # Get current rankings from store
        rankings = await self._store.get_miner_rankings(limit=256)
        if len(rankings) < self._min_rankings:
            logger.info(
                "WeightSetter: only %d rankings (min %d), skipping",
                len(rankings), self._min_rankings,
            )
            return False

        uids, weights = self.compute_weight_vector(rankings, hotkey_to_uid)
        if not uids:
            logger.warning("WeightSetter: no valid weights to set")
            return False

        # Set weights on-chain
        subtensor = self._adapter._subtensor
        wallet = self._adapter._wallet
        if subtensor is None or wallet is None:
            logger.error("WeightSetter: subtensor or wallet not initialized")
            return False

        try:
            success, msg = subtensor.set_weights(
                netuid=self._netuid,
                wallet=wallet,
                uids=uids,
                weights=weights,
                wait_for_inclusion=True,
            )
            if success:
                block = getattr(metagraph, "block", None)
                self.last_set_at_block = block
                self.total_weight_sets += 1
                logger.info(
                    "WeightSetter: set weights for %d miners at block %s (total sets: %d)",
                    len(uids), block, self.total_weight_sets,
                )
            else:
                logger.warning("WeightSetter: set_weights returned failure: %s", msg)
            return success
        except Exception as exc:
            logger.exception("WeightSetter: set_weights failed: %s", exc)
            return False

    async def run(self) -> None:
        """Background loop: set weights every interval_blocks (~20 min at 12s/block)."""
        self._running = True
        interval_secs = self._interval_blocks * 12  # ~12 seconds per block
        logger.info(
            "WeightSetter started (interval=%d blocks / %d secs, netuid=%d)",
            self._interval_blocks, interval_secs, self._netuid,
        )
        try:
            while self._running:
                await self._adapter.refresh_metagraph()
                await self.set_weights_once()
                await asyncio.sleep(interval_secs)
        except asyncio.CancelledError:
            logger.info("WeightSetter cancelled")
        finally:
            self._running = False
            logger.info("WeightSetter stopped")

    def stop(self) -> None:
        self._running = False
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd trading && python -m pytest tests/unit/test_integrations/test_bittensor_weight_setter.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 5: Wire WeightSetter into Bittensor startup**

In `trading/api/startup/integrations.py`, add to the `setup_bittensor()` function, after the evaluator is created (around line 184):

```python
        from integrations.bittensor.weight_setter import WeightSetter

        _bt_weight_setter = WeightSetter(
            adapter=_bt_adapter,
            store=_bt_store,
            netuid=config.bittensor_subnet_uid,
            interval_blocks=100,
            min_rankings=config.bittensor_min_windows_for_ranking,
        )
```

Add `"weight_setter": _bt_weight_setter` to the returned components dict (around line 206).

- [ ] **Step 6: Start the WeightSetter as a background task**

In `trading/api/app.py`, find where `bittensor_scheduler` and `bittensor_evaluator` background tasks are started. Add alongside them:

```python
if bt_components.get("weight_setter"):
    weight_setter = bt_components["weight_setter"]
    app.state.bittensor_weight_setter = weight_setter
    asyncio.create_task(weight_setter.run())
```

- [ ] **Step 7: Commit**

```bash
git add trading/integrations/bittensor/weight_setter.py \
       trading/tests/unit/test_integrations/test_bittensor_weight_setter.py \
       trading/api/startup/integrations.py \
       trading/api/app.py
git commit -m "feat(bittensor): implement WeightSetter for on-chain weight setting

Validators must call set_weights() to score miners and earn rewards.
Maps hybrid_score from miner rankings to normalized weight vector."
```

---

### Task A5: Add Connection Retry Logic to Adapter

**Files:**
- Modify: `trading/integrations/bittensor/adapter.py:53-75`
- Create: `trading/tests/unit/test_integrations/test_bittensor_adapter_retry.py`

- [ ] **Step 1: Write the failing test**

```python
# trading/tests/unit/test_integrations/test_bittensor_adapter_retry.py
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from integrations.bittensor.adapter import TaoshiProtocolAdapter


class TestAdapterRetry:
    @pytest.mark.asyncio
    async def test_connect_retries_on_failure(self):
        """connect() should retry up to max_retries on failure."""
        adapter = TaoshiProtocolAdapter(
            network="finney",
            endpoint="wss://fake:443",
            wallet_name="test",
            hotkey_path="/tmp",
            hotkey="test_hotkey",
            subnet_uid=8,
        )

        call_count = 0

        def mock_subtensor(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("chain unreachable")
            return MagicMock()

        with patch("integrations.bittensor.adapter.bt") as mock_bt:
            mock_bt.subtensor = mock_subtensor
            mock_bt.wallet = MagicMock(return_value=MagicMock())
            mock_bt.dendrite = MagicMock(return_value=MagicMock())

            await adapter.connect(max_retries=3, retry_delay=0.01)

        assert call_count == 3
        assert adapter._subtensor is not None

    @pytest.mark.asyncio
    async def test_connect_raises_after_max_retries(self):
        adapter = TaoshiProtocolAdapter(
            network="finney",
            endpoint="wss://fake:443",
            wallet_name="test",
            hotkey_path="/tmp",
            hotkey="test_hotkey",
            subnet_uid=8,
        )

        with patch("integrations.bittensor.adapter.bt") as mock_bt:
            mock_bt.subtensor = MagicMock(side_effect=ConnectionError("down"))
            with pytest.raises(ConnectionError):
                await adapter.connect(max_retries=2, retry_delay=0.01)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd trading && python -m pytest tests/unit/test_integrations/test_bittensor_adapter_retry.py -v
```

Expected: FAIL — `connect()` doesn't accept `max_retries` parameter.

- [ ] **Step 3: Update adapter.connect() with retry logic**

Replace the `connect()` method in `trading/integrations/bittensor/adapter.py:53-75`:

```python
    async def connect(self, max_retries: int = 5, retry_delay: float = 5.0) -> None:
        """Initialize subtensor connection, wallet, and dendrite with retry."""
        try:
            import bittensor as bt
        except ImportError:
            raise ImportError(
                "bittensor SDK not installed. Run: pip install bittensor"
            )

        last_exc: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                self._subtensor = bt.subtensor(
                    network=self._network,
                    chain_endpoint=self._endpoint,
                )
                self._wallet = bt.wallet(
                    name=self._wallet_name,
                    path=self._hotkey_path,
                    hotkey=self._hotkey,
                )
                self._dendrite = bt.dendrite(wallet=self._wallet)
                logger.info(
                    "Bittensor adapter connected (network=%s, endpoint=%s, subnet=%d) on attempt %d",
                    self._network, self._endpoint, self._subnet_uid, attempt,
                )
                return
            except Exception as exc:
                last_exc = exc
                if attempt < max_retries:
                    delay = retry_delay * (2 ** (attempt - 1))  # exponential backoff
                    logger.warning(
                        "Bittensor connect attempt %d/%d failed: %s. Retrying in %.1fs",
                        attempt, max_retries, exc, delay,
                    )
                    await asyncio.sleep(delay)

        raise last_exc or ConnectionError("Failed to connect after retries")
```

Also add `import asyncio` at the top of `adapter.py` if not already present.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd trading && python -m pytest tests/unit/test_integrations/test_bittensor_adapter_retry.py -v
```

Expected: Both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add trading/integrations/bittensor/adapter.py \
       trading/tests/unit/test_integrations/test_bittensor_adapter_retry.py
git commit -m "feat(bittensor): add exponential backoff retry to adapter.connect()"
```

---

### Task A6: Deploy Trading Service on WSL2

**Files:**
- Create: `trading/.env` (on WSL2, not committed)
- Create: `/etc/systemd/system/bittensor-validator.service` (on WSL2)

- [ ] **Step 1: Clone repo and install dependencies on WSL2**

```bash
cd ~
git clone <your-repo-url> agent-memory-unified
cd agent-memory-unified/trading
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

- [ ] **Step 2: Create .env with production Bittensor config**

```bash
cat > ~/agent-memory-unified/trading/.env << 'EOF'
STA_BITTENSOR_ENABLED=true
STA_BITTENSOR_MOCK=false
STA_BITTENSOR_NETWORK=finney
STA_BITTENSOR_ENDPOINT=wss://entrypoint-finney.opentensor.ai:443
STA_BITTENSOR_WALLET_NAME=sta_wallet
STA_BITTENSOR_HOTKEY=sta_hotkey
STA_BITTENSOR_HOTKEY_PATH=~/.bittensor/wallets
STA_BITTENSOR_SUBNET_UID=8
STA_BITTENSOR_SELECTION_POLICY=all
STA_BITTENSOR_MIN_RESPONSES_FOR_CONSENSUS=3
STA_BITTENSOR_MIN_RESPONSES_FOR_OPPORTUNITY=3
STA_DATABASE_URL=postgresql://user:pass@host:5432/agent_memory
STA_DATABASE_SSL=true
STA_REDIS_URL=redis://host:6379/0
STA_API_KEY=your-api-key-here
STA_API_PORT=8080
STA_BROKER_MODE=paper
EOF
```

Update `DATABASE_URL` and `REDIS_URL` to point to your Railway instances (or local PostgreSQL/Redis).

- [ ] **Step 3: Test the service starts and connects**

```bash
cd ~/agent-memory-unified/trading
source .venv/bin/activate
python -m uvicorn api.app:create_app --host 0.0.0.0 --port 8080 --factory
```

Watch logs for:
- `Bittensor adapter connected (network=finney ...)`
- `Bittensor smoke test passed`
- `TaoshiScheduler started`
- `WeightSetter started`

Hit `Ctrl+C` to stop.

- [ ] **Step 4: Create systemd service for 24/7 uptime**

```bash
sudo tee /etc/systemd/system/bittensor-validator.service << 'EOF'
[Unit]
Description=Agent Memory Bittensor Validator
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=/home/$USER/agent-memory-unified/trading
Environment=PATH=/home/$USER/agent-memory-unified/trading/.venv/bin:/usr/local/bin:/usr/bin
ExecStart=/home/$USER/agent-memory-unified/trading/.venv/bin/python -m uvicorn api.app:create_app --host 0.0.0.0 --port 8080 --factory
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF
```

Replace `$USER` with your actual WSL2 username.

- [ ] **Step 5: Enable and start the service**

```bash
sudo systemctl daemon-reload
sudo systemctl enable bittensor-validator
sudo systemctl start bittensor-validator
sudo systemctl status bittensor-validator
```

Expected: `active (running)`.

- [ ] **Step 6: Verify validator is collecting predictions**

```bash
curl http://localhost:8080/api/bittensor/status -H "Authorization: Bearer your-api-key"
```

Expected: JSON with `enabled: true`, `healthy: true`, scheduler and evaluator running.

---

## Track B: Codebase Refactoring

### Phase 1: Shared/Infrastructure

---

### Task 1.1: Unify Type Generation Pipeline

**Files:**
- Modify: `scripts/sync-types.sh` (becomes the single source of truth)
- Delete: `shared/types/scripts/generate-types.sh`
- Modify: `.githooks/pre-commit`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Read both existing scripts**

```bash
cat scripts/sync-types.sh
cat shared/types/scripts/generate-types.sh
```

Understand what each does. `sync-types.sh` handles Python + TypeScript. `generate-types.sh` handles the same but with different tool paths. `scripts/generate-php-types.php` handles PHP separately.

- [ ] **Step 2: Update `scripts/sync-types.sh` to generate all three languages**

Add PHP generation to the end of `scripts/sync-types.sh`:

```bash
# After the existing Python and TypeScript generation blocks, add:

echo "→ PHP (DTOs)..."
php scripts/generate-php-types.php
if [ $? -ne 0 ]; then
    echo "❌ PHP type generation failed"
    exit 1
fi

echo "✅ All types generated (Python, TypeScript, PHP)"
```

- [ ] **Step 3: Delete the duplicate script**

```bash
rm shared/types/scripts/generate-types.sh
```

- [ ] **Step 4: Update pre-commit hook with error handling**

Replace `.githooks/pre-commit`:

```bash
#!/bin/bash
set -euo pipefail

echo "🔧 Regenerating types from JSON Schemas..."

# Check required tools
if ! command -v datamodel-codegen &>/dev/null; then
    echo "⚠️  datamodel-codegen not installed — skipping type generation"
    echo "   Install: pip install datamodel-code-generator"
    exit 0
fi

if ! command -v npx &>/dev/null; then
    echo "⚠️  npx not available — skipping type generation"
    exit 0
fi

# Run unified generator
./scripts/sync-types.sh || { echo "❌ Type generation failed"; exit 1; }

# Stage generated files
git add shared/types/generated/
git add shared/types-py/shared_types/

echo "✅ Types regenerated and staged"
```

- [ ] **Step 5: Commit**

```bash
git add scripts/sync-types.sh .githooks/pre-commit
git rm shared/types/scripts/generate-types.sh
git commit -m "refactor: unify type generation into single script

- scripts/sync-types.sh now generates Python, TypeScript, and PHP
- Deleted duplicate shared/types/scripts/generate-types.sh
- Pre-commit hook now checks for tool availability before running"
```

---

### Task 1.2: Add Test Execution to CI

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add API test job**

Append to `.github/workflows/ci.yml`:

```yaml
  api-test:
    name: API Tests
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_DB: agent_memory_test
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: secret
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
      redis:
        image: redis:7-alpine
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 6379:6379
    defaults:
      run:
        working-directory: api
    steps:
      - uses: actions/checkout@v4

      - name: Set up PHP
        uses: shivammathur/setup-php@v2
        with:
          php-version: '8.3'
          extensions: pdo_pgsql, redis, bcmath, zip
          tools: composer:v2

      - name: Install dependencies
        run: composer install --no-interaction --no-progress --prefer-dist

      - name: Prepare environment
        run: |
          cp .env.example .env
          php artisan key:generate
          php artisan config:clear

      - name: Run tests
        env:
          DB_CONNECTION: pgsql
          DB_HOST: 127.0.0.1
          DB_PORT: 5432
          DB_DATABASE: agent_memory_test
          DB_USERNAME: postgres
          DB_PASSWORD: secret
          REDIS_HOST: 127.0.0.1
        run: php artisan test --parallel

  trading-test:
    name: Trading Tests
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: trading
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-test.txt

      - name: Run unit tests
        run: python -m pytest tests/unit/ -x --timeout=60 -q
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add API and Trading test jobs to CI pipeline

- api-test: runs Pest with PostgreSQL + Redis service containers
- trading-test: runs pytest unit tests with timeout"
```

---

### Task 1.3: Docker Health Checks

**Files:**
- Modify: `docker-compose.yml`
- Modify: `staging.docker-compose.yml`

- [ ] **Step 1: Add health checks to docker-compose.yml**

Add to the `postgres` service:
```yaml
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5
```

Add to the `redis` service:
```yaml
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5
```

Add `condition: service_healthy` to api and trading service `depends_on`:
```yaml
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
```

- [ ] **Step 2: Apply the same to staging.docker-compose.yml**

Same health checks for postgres and redis. Same `condition: service_healthy` on api-service and trading-service.

- [ ] **Step 3: Fix staging Dockerfile references**

In `staging.docker-compose.yml`, update:
- `api-service.build.dockerfile` from `Dockerfile.api` to `api/Dockerfile`
- `trading-service.build.dockerfile` from `Dockerfile.trading` to `trading/Dockerfile`

Set the build context to repo root for both:
```yaml
  api-service:
    build:
      context: .
      dockerfile: api/Dockerfile
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml staging.docker-compose.yml
git commit -m "fix(docker): add health checks, fix staging Dockerfile paths

- postgres/redis health checks prevent race conditions
- Services wait for healthy databases before starting
- Fixed staging compose to reference actual Dockerfile paths"
```

---

### Task 1.4: Fix Schema Drift

**Files:**
- Create: `api/database/migrations/2026_04_06_000001_fix_arb_schema_drift.php`

- [ ] **Step 1: Create the migration**

```bash
cd api && php artisan make:migration fix_arb_schema_drift
```

- [ ] **Step 2: Implement the migration**

```php
<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (Schema::hasTable('arb_spread_observations')) {
            Schema::table('arb_spread_observations', function (Blueprint $table) {
                if (!Schema::hasColumn('arb_spread_observations', 'is_claimed')) {
                    $table->boolean('is_claimed')->default(false);
                }
                if (!Schema::hasColumn('arb_spread_observations', 'claimed_at')) {
                    $table->timestamp('claimed_at')->nullable();
                }
                if (!Schema::hasColumn('arb_spread_observations', 'claimed_by')) {
                    $table->string('claimed_by')->nullable();
                }
            });
        }

        if (Schema::hasTable('arb_trades')) {
            Schema::table('arb_trades', function (Blueprint $table) {
                if (!Schema::hasColumn('arb_trades', 'sequencing')) {
                    $table->string('sequencing')->nullable();
                }
            });
        }
    }

    public function down(): void
    {
        if (Schema::hasTable('arb_spread_observations')) {
            Schema::table('arb_spread_observations', function (Blueprint $table) {
                $table->dropColumn(['is_claimed', 'claimed_at', 'claimed_by']);
            });
        }

        if (Schema::hasTable('arb_trades')) {
            Schema::table('arb_trades', function (Blueprint $table) {
                $table->dropColumn('sequencing');
            });
        }
    }
};
```

- [ ] **Step 3: Commit**

```bash
git add api/database/migrations/
git commit -m "fix(schema): add missing arb columns from schema-drift-audit

Fixes: arb_spread_observations missing is_claimed, claimed_at, claimed_by
Fixes: arb_trades missing sequencing column"
```

---

### Task 1.5: Remove Stale Scripts

**Files:**
- Delete: `scripts/migrate_sqlite_to_postgres.py`
- Delete: `scripts/postgres-to-laravel.py`

- [ ] **Step 1: Delete stale migration scripts**

```bash
git rm scripts/migrate_sqlite_to_postgres.py scripts/postgres-to-laravel.py
git commit -m "chore: remove stale database migration scripts

Database consolidation (Phase 2) is complete. These can be
recovered from git history if ever needed again."
```

---

### Phase 2: Trading Service

---

### Task 2.1: Consolidate Duplicate Modules

**Files:**
- Delete: `trading/strategies/ensemble_optimizer.py`
- Delete: `trading/strategies/correlation_monitor.py`

- [ ] **Step 1: Verify the learning/ versions are the canonical ones**

```bash
diff trading/strategies/ensemble_optimizer.py trading/learning/ensemble_optimizer.py
diff trading/strategies/correlation_monitor.py trading/learning/correlation_monitor.py
```

Confirm they are near-identical (may have minor differences to reconcile).

- [ ] **Step 2: Find all imports of the strategies/ versions**

```bash
cd trading && grep -rn "from strategies.ensemble_optimizer\|from strategies.correlation_monitor" --include="*.py" .
```

- [ ] **Step 3: Update imports to use learning/ versions**

For each file found in step 2, change:
- `from strategies.ensemble_optimizer import ...` → `from learning.ensemble_optimizer import ...`
- `from strategies.correlation_monitor import ...` → `from learning.correlation_monitor import ...`

- [ ] **Step 4: Delete the duplicates**

```bash
rm trading/strategies/ensemble_optimizer.py trading/strategies/correlation_monitor.py
```

- [ ] **Step 5: Run tests to verify nothing broke**

```bash
cd trading && python -m pytest tests/unit/ -x --timeout=60 -q
```

- [ ] **Step 6: Commit**

```bash
git add -A trading/strategies/ trading/learning/
git commit -m "refactor: consolidate duplicate modules to learning/

Deleted strategies/ensemble_optimizer.py and strategies/correlation_monitor.py.
Canonical versions live in learning/. Updated all imports."
```

---

### Task 2.2: Split Config Dataclass

**Files:**
- Modify: `trading/config.py`
- Create: `trading/tests/unit/test_config_nested.py`

- [ ] **Step 1: Write the failing test**

```python
# trading/tests/unit/test_config_nested.py
from config import load_config, Config


class TestNestedConfig:
    def test_bittensor_config_nested(self):
        """Bittensor settings should be accessible via config.bittensor."""
        config = load_config(env_file="/dev/null")
        assert hasattr(config, 'bittensor')
        assert config.bittensor.enabled is False
        assert config.bittensor.network == "finney"
        assert config.bittensor.subnet_uid == 8

    def test_broker_config_nested(self):
        config = load_config(env_file="/dev/null")
        assert hasattr(config, 'broker')
        assert config.broker.ib_host == "127.0.0.1"
        assert config.broker.mode == "paper"

    def test_backward_compat_flat_access(self):
        """Flat attribute access should still work for migration period."""
        config = load_config(env_file="/dev/null")
        # These should work via __getattr__ delegation
        assert config.bittensor_enabled is False
        assert config.ib_host == "127.0.0.1"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd trading && python -m pytest tests/unit/test_config_nested.py -v
```

Expected: FAIL — `Config` has no `bittensor` attribute.

- [ ] **Step 3: Implement nested config dataclasses**

This is a large refactor of `trading/config.py`. Create nested dataclasses for the major groups:

```python
@dataclass
class BrokerConfig:
    ib_host: str = "127.0.0.1"
    ib_port: int | None = None
    ib_client_id: int = 1
    ib_readonly: bool = False
    mode: str = "paper"
    primary_broker: str | None = None
    routing: dict[str, str] = field(default_factory=dict)
    # ... alpaca, tradier fields

@dataclass
class BittensorConfig:
    enabled: bool = False
    network: str = "finney"
    endpoint: str = "ws://localhost:9944"
    wallet_name: str = "sta_wallet"
    hotkey_path: str = ""
    hotkey: str = "sta_hotkey"
    subnet_uid: int = 8
    selection_policy: str = "all"
    selection_metric: str = "incentive"
    top_miners: int = 10
    mock: bool = False
    # ... remaining bittensor fields

@dataclass
class LLMConfig:
    anthropic_api_key: str | None = None
    groq_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    bedrock_region: str | None = None
    # ... remaining LLM fields
    fallback_chain: list[str] = field(
        default_factory=lambda: ["anthropic", "bedrock", "groq", "ollama", "rule-based"]
    )
```

Add `__getattr__` to `Config` for backward compatibility:

```python
@dataclass
class Config:
    broker: BrokerConfig = field(default_factory=BrokerConfig)
    bittensor: BittensorConfig = field(default_factory=BittensorConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    # ... keep flat fields that don't fit a group

    def __getattr__(self, name: str):
        """Backward-compat: config.bittensor_enabled -> config.bittensor.enabled"""
        # Map old flat names to nested paths
        prefixes = {
            'bittensor_': ('bittensor', 'bittensor_'),
            'ib_': ('broker', 'ib_'),
        }
        for prefix, (group, strip) in prefixes.items():
            if name.startswith(prefix):
                nested_name = name[len(strip):]
                group_obj = object.__getattribute__(self, group)
                if hasattr(group_obj, nested_name):
                    return getattr(group_obj, nested_name)
                # Try with prefix kept (e.g., ib_host -> broker.ib_host)
                if hasattr(group_obj, name):
                    return getattr(group_obj, name)
        raise AttributeError(f"Config has no attribute '{name}'")
```

Update `load_config()` to populate nested structures.

**Note:** This is a significant change. The `__getattr__` bridge ensures existing code like `config.bittensor_enabled` keeps working during migration. Over time, callers should migrate to `config.bittensor.enabled`.

- [ ] **Step 4: Run tests**

```bash
cd trading && python -m pytest tests/unit/test_config_nested.py -v
cd trading && python -m pytest tests/unit/ -x --timeout=60 -q
```

Expected: All tests pass (new and existing).

- [ ] **Step 5: Commit**

```bash
git add trading/config.py trading/tests/unit/test_config_nested.py
git commit -m "refactor: split Config into nested dataclasses

BrokerConfig, BittensorConfig, LLMConfig extracted as nested groups.
__getattr__ bridge maintains backward compatibility for flat access."
```

---

### Task 2.3: Remove Unused Imports in Trading Service

**Files:**
- Modify: `trading/api/app.py`
- Modify: `trading/agents/router.py`
- Modify: `trading/llm/client.py`

- [ ] **Step 1: Run ruff to identify all unused imports**

```bash
cd trading && ruff check --select F401 .
```

- [ ] **Step 2: Auto-fix unused imports**

```bash
cd trading && ruff check --select F401 --fix .
```

- [ ] **Step 3: Run tests to verify nothing broke**

```bash
cd trading && python -m pytest tests/unit/ -x --timeout=60 -q
```

- [ ] **Step 4: Commit**

```bash
git add -A trading/
git commit -m "chore: remove unused imports across trading service

Automated fix via ruff --select F401 --fix"
```

---

### Phase 3: API Service (Laravel)

---

### Task 3.1: Extract ResolvesAgent Trait

**Files:**
- Create: `api/app/Traits/ResolvesAgent.php`
- Modify: `api/app/Http/Controllers/Api/MemoryController.php`
- Modify: `api/app/Http/Controllers/Api/TaskController.php`
- Modify: `api/app/Http/Controllers/Api/MentionController.php`
- Modify: `api/app/Http/Controllers/Api/PresenceController.php`
- Modify: `api/app/Http/Controllers/Api/SubscriptionController.php`
- Modify: `api/app/Http/Controllers/Api/SessionController.php`

- [ ] **Step 1: Create the trait**

```php
<?php
// api/app/Traits/ResolvesAgent.php

namespace App\Traits;

use App\Models\Agent;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

trait ResolvesAgent
{
    /**
     * Resolve the active agent for the request.
     * If the actor is an Agent token, use that agent.
     * If the actor is a Workspace token, require 'agent_id' in payload
     * and ensure it belongs to the workspace.
     */
    protected function resolveAgent(Request $request, ?array $validated = null): Agent|JsonResponse
    {
        $agent = $request->attributes->get('agent');
        $workspace = $request->attributes->get('workspace_token');

        if ($agent) {
            return $agent;
        }

        if ($workspace) {
            $agentId = $validated['agent_id'] ?? $request->input('agent_id');
            if (! $agentId) {
                return response()->json(['error' => 'agent_id is required when authenticating via Workspace token.'], 422);
            }

            $agent = Agent::find($agentId);
            if (! $agent) {
                return response()->json(['error' => 'Agent not found.'], 404);
            }

            if (! $workspace->agents()->where('agents.id', $agentId)->exists()) {
                return response()->json(['error' => 'Agent does not belong to this Workspace.'], 403);
            }

            return $agent;
        }

        return response()->json(['error' => 'No valid authentication context found.'], 401);
    }

    /**
     * Resolve agent and abort if resolution failed.
     * Returns Agent on success; sends error response and returns null on failure.
     */
    protected function resolveAgentOrFail(Request $request, ?array $validated = null): Agent|JsonResponse
    {
        return $this->resolveAgent($request, $validated);
    }
}
```

- [ ] **Step 2: Update MemoryController to use the trait**

In `api/app/Http/Controllers/Api/MemoryController.php`:

1. Add `use App\Traits\ResolvesAgent;` import
2. Add `use ResolvesAgent;` inside the class (alongside existing `use FormatsMemories;`)
3. Delete the private `resolveAgent()` method (lines 36-64)

- [ ] **Step 3: Repeat for the other 5 controllers**

For each of TaskController, MentionController, PresenceController, SubscriptionController, SessionController:

1. Add `use App\Traits\ResolvesAgent;` import
2. Add `use ResolvesAgent;` inside the class
3. Delete the private `resolveAgent()` method

- [ ] **Step 4: Run tests**

```bash
cd api && php artisan test
```

Expected: All tests pass. The trait has identical behavior to the inline methods.

- [ ] **Step 5: Commit**

```bash
git add api/app/Traits/ResolvesAgent.php \
       api/app/Http/Controllers/Api/MemoryController.php \
       api/app/Http/Controllers/Api/TaskController.php \
       api/app/Http/Controllers/Api/MentionController.php \
       api/app/Http/Controllers/Api/PresenceController.php \
       api/app/Http/Controllers/Api/SubscriptionController.php \
       api/app/Http/Controllers/Api/SessionController.php
git commit -m "refactor: extract ResolvesAgent trait from 6 controllers

Eliminates ~150 lines of duplicated agent resolution logic.
All 6 controllers now use the shared trait."
```

---

### Task 3.2: Create FormRequest Classes

**Files:**
- Create: `api/app/Http/Requests/StoreMemoryRequest.php`
- Create: `api/app/Http/Requests/CreateTaskRequest.php`
- Create: `api/app/Http/Requests/CreateWebhookRequest.php`
- Modify: `api/app/Http/Controllers/Api/MemoryController.php`
- Modify: `api/app/Http/Controllers/Api/TaskController.php`
- Modify: `api/app/Http/Controllers/Api/WebhookController.php`

- [ ] **Step 1: Create StoreMemoryRequest**

```bash
cd api && php artisan make:request StoreMemoryRequest
```

```php
<?php
// api/app/Http/Requests/StoreMemoryRequest.php

namespace App\Http\Requests;

use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Rule;

class StoreMemoryRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true; // Auth handled by middleware
    }

    public function rules(): array
    {
        return [
            'value' => ['required', 'string', 'min:1', 'max:100000'],
            'type' => ['sometimes', Rule::in(['note', 'lesson', 'preference', 'fact', 'procedure'])],
            'visibility' => ['sometimes', Rule::in(['private', 'public'])],
            'tags' => ['sometimes', 'array'],
            'tags.*' => ['string'],
            'metadata' => ['sometimes', 'array'],
            'ttl' => ['sometimes', 'string'],
            'workspace_id' => ['sometimes', 'uuid'],
            'agent_id' => ['sometimes', 'uuid'],
        ];
    }
}
```

- [ ] **Step 2: Create CreateTaskRequest**

```bash
cd api && php artisan make:request CreateTaskRequest
```

```php
<?php

namespace App\Http\Requests;

use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Rule;

class CreateTaskRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true;
    }

    public function rules(): array
    {
        return [
            'workspace_id' => ['required', 'uuid', 'exists:workspaces,id'],
            'title' => ['required', 'string', 'max:255'],
            'description' => ['sometimes', 'string', 'max:10000'],
            'assigned_to' => ['sometimes', 'uuid', 'exists:agents,id'],
            'priority' => ['sometimes', Rule::in(['low', 'medium', 'high', 'critical'])],
            'due_at' => ['sometimes', 'date'],
            'agent_id' => ['sometimes', 'uuid'],
        ];
    }
}
```

- [ ] **Step 3: Create CreateWebhookRequest**

```bash
cd api && php artisan make:request CreateWebhookRequest
```

```php
<?php

namespace App\Http\Requests;

use Illuminate\Foundation\Http\FormRequest;

class CreateWebhookRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true;
    }

    public function rules(): array
    {
        return [
            'url' => ['required', 'url', 'max:2048'],
            'events' => ['required', 'array', 'min:1'],
            'events.*' => ['string'],
            'secret' => ['sometimes', 'string', 'min:16'],
        ];
    }
}
```

- [ ] **Step 4: Update controllers to use FormRequests**

In each controller, replace `$request->validate([...])` calls with the typed FormRequest:

```php
// Before (MemoryController):
public function store(Request $request): JsonResponse
{
    $validated = $request->validate([...]);

// After:
public function store(StoreMemoryRequest $request): JsonResponse
{
    $validated = $request->validated();
```

- [ ] **Step 5: Run tests**

```bash
cd api && php artisan test
```

- [ ] **Step 6: Commit**

```bash
git add api/app/Http/Requests/ api/app/Http/Controllers/Api/
git commit -m "refactor: extract FormRequest classes for Memory, Task, Webhook

Moves inline validation rules to dedicated FormRequest classes.
Improves reusability and testability of validation logic."
```

---

### Phase 4: Frontend

---

### Task 4.1: Fix Authentication

**Files:**
- Modify: `frontend/src/lib/auth.ts`

- [ ] **Step 1: Read the current auth implementation**

```bash
cat frontend/src/lib/auth.ts
```

- [ ] **Step 2: Replace with real token verification**

```typescript
// frontend/src/lib/auth.ts
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from './api/client';

interface AuthUser {
  id: string;
  name: string;
  email?: string;
}

interface AuthState {
  user: AuthUser | null;
  token: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}

export function useAuth() {
  const [state, setState] = useState<AuthState>({
    user: null,
    token: localStorage.getItem('token'),
    isLoading: true,
    isAuthenticated: false,
  });

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      setState({ user: null, token: null, isLoading: false, isAuthenticated: false });
      return;
    }

    // Verify token by hitting the agents/me endpoint
    api.get('/v1/agents/me')
      .then((res) => {
        setState({
          user: res.data,
          token,
          isLoading: false,
          isAuthenticated: true,
        });
      })
      .catch(() => {
        // Token expired or invalid — clear it
        localStorage.removeItem('token');
        setState({ user: null, token: null, isLoading: false, isAuthenticated: false });
      });
  }, []);

  const login = useCallback((token: string) => {
    localStorage.setItem('token', token);
    setState((prev) => ({ ...prev, token, isLoading: true }));
    // Re-trigger verification
    api.get('/v1/agents/me')
      .then((res) => {
        setState({ user: res.data, token, isLoading: false, isAuthenticated: true });
      })
      .catch(() => {
        localStorage.removeItem('token');
        setState({ user: null, token: null, isLoading: false, isAuthenticated: false });
      });
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('token');
    setState({ user: null, token: null, isLoading: false, isAuthenticated: false });
  }, []);

  return { ...state, login, logout };
}
```

- [ ] **Step 3: Run the app to verify**

```bash
cd frontend && npm run dev
```

Open `http://localhost:3000` — should redirect to login if no valid token.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/auth.ts
git commit -m "fix(auth): replace placeholder with real token verification

- Verifies token on app load via GET /api/v1/agents/me
- Clears invalid/expired tokens automatically
- Removes hardcoded mock user data"
```

---

### Task 4.2: Add Error Boundaries

**Files:**
- Create: `frontend/src/components/ErrorBoundary.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create ErrorBoundary component**

```tsx
// frontend/src/components/ErrorBoundary.tsx
import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div className="min-h-screen flex items-center justify-center bg-obsidian">
          <div className="glass-panel p-8 max-w-md text-center">
            <h2 className="text-xl font-bold text-white mb-4">Something went wrong</h2>
            <p className="text-gray-400 mb-6">
              {this.state.error?.message || 'An unexpected error occurred.'}
            </p>
            <button
              onClick={() => this.setState({ hasError: false, error: null })}
              className="neural-button-primary px-6 py-2"
            >
              Try again
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
```

- [ ] **Step 2: Wrap App with ErrorBoundary**

In `frontend/src/App.tsx`, wrap the `QueryClientProvider` + `RouterProvider` in `<ErrorBoundary>`:

```tsx
import { ErrorBoundary } from './components/ErrorBoundary';

// In the return:
return (
  <ErrorBoundary>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </ErrorBoundary>
);
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ErrorBoundary.tsx frontend/src/App.tsx
git commit -m "feat(frontend): add ErrorBoundary for crash recovery

Catches unhandled errors and shows a friendly 'Try again' UI
instead of a white screen."
```

---

### Task 4.3: Extract QueryWrapper Component

**Files:**
- Create: `frontend/src/components/QueryWrapper.tsx`

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/QueryWrapper.tsx
import type { UseQueryResult } from '@tanstack/react-query';
import type { ReactNode } from 'react';

interface QueryWrapperProps<T> {
  query: UseQueryResult<T>;
  emptyMessage?: string;
  children: (data: T) => ReactNode;
}

export function QueryWrapper<T>({
  query,
  emptyMessage = 'No data found.',
  children,
}: QueryWrapperProps<T>) {
  if (query.isLoading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-pulse text-gray-500">Loading...</div>
      </div>
    );
  }

  if (query.error) {
    return (
      <div className="glass-panel p-6 text-center">
        <p className="text-red-400">Error: {query.error.message}</p>
        <button
          onClick={() => query.refetch()}
          className="mt-4 neural-button-secondary px-4 py-2"
        >
          Retry
        </button>
      </div>
    );
  }

  const data = query.data;
  if (data == null || (Array.isArray(data) && data.length === 0)) {
    return (
      <div className="glass-panel p-6 text-center">
        <p className="text-gray-500">{emptyMessage}</p>
      </div>
    );
  }

  return <>{children(data)}</>;
}
```

- [ ] **Step 2: Use it in one page as proof of concept**

In `frontend/src/pages/Leaderboard.tsx`, replace the manual loading/error/empty pattern:

```tsx
import { QueryWrapper } from '../components/QueryWrapper';

// Replace the manual checks with:
<QueryWrapper query={leaderboardQuery} emptyMessage="No agents ranked yet.">
  {(data) => (
    <div className="grid gap-4">
      {data.map((agent: any) => (
        // ... existing render logic
      ))}
    </div>
  )}
</QueryWrapper>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/QueryWrapper.tsx frontend/src/pages/Leaderboard.tsx
git commit -m "feat(frontend): add QueryWrapper for consistent loading/error/empty states

Eliminates repeated loading/error/empty pattern across pages.
Applied to Leaderboard as proof of concept."
```

---

### Task 4.4: Fix E2E Test Assertions

**Files:**
- Modify: `frontend/tests/e2e/auth.spec.ts`
- Modify: `frontend/tests/e2e/core.spec.ts`

- [ ] **Step 1: Read current test files and actual page text**

```bash
cat frontend/tests/e2e/auth.spec.ts
cat frontend/tests/e2e/core.spec.ts
grep -n "Welcome Back\|Login\|Trade Ledger\|Trade History" frontend/src/pages/*.tsx
```

- [ ] **Step 2: Fix auth.spec.ts assertions**

Update heading assertion from `"Welcome Back"` to match actual Login.tsx heading text.

- [ ] **Step 3: Fix core.spec.ts assertions**

Update `"Trade Ledger"` to `"Trade History"` to match actual TradeHistory.tsx.

- [ ] **Step 4: Run Playwright tests**

```bash
cd frontend && npx playwright test
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/tests/e2e/
git commit -m "fix(tests): update E2E assertions to match current UI text

- auth.spec.ts: fix heading text expectation
- core.spec.ts: 'Trade Ledger' -> 'Trade History'"
```

---

## Plan Summary

| Track/Phase | Tasks | Estimated Steps | Key Deliverable |
|---|---|---|---|
| **Track A: Validator** | A1-A6 | 26 | Live Bittensor validator on WSL2 |
| **Phase 1: Infra** | 1.1-1.5 | 14 | Unified CI, Docker health, schema fixes |
| **Phase 2: Trading** | 2.1-2.3 | 16 | No duplicates, nested config, clean imports |
| **Phase 3: API** | 3.1-3.2 | 10 | Traits, FormRequests |
| **Phase 4: Frontend** | 4.1-4.4 | 12 | Real auth, error boundaries, QueryWrapper |
| **Total** | **20 tasks** | **78 steps** | Net negative lines, production validator |

> **Note:** This plan covers the highest-priority items from the 50 identified in the spec. The remaining items (app.py decomposition, router.py decomposition, MemoryController split, etc.) are large refactors that should get their own dedicated plans once these foundations are in place.
