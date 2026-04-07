# Wire Signal Pipeline End-to-End Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the complete signal pipeline so miner positions from TaoshiBridge reach trading strategies via a new consensus aggregator.

**Architecture:** A `MinerConsensusAggregator` subscribes to raw `bittensor_miner_position` signals on the `SignalBus`, maintains a sliding window of positions per symbol, computes consensus (direction, confidence, expected return), and publishes `bittensor_consensus` signals. The aggregator is wired into the app lifecycle to ensure the existing `BittensorAlphaAgent` receives these signals.

**Tech Stack:** Python 3.12+, FastAPI, asyncio, pytest

---

### Task 1: Create MinerConsensusAggregator and Unit Tests

**Files:**
- Create: `trading/integrations/bittensor/consensus_aggregator.py`
- Create: `trading/tests/unit/test_consensus_aggregator.py`

- [ ] **Step 1: Write the failing unit tests for MinerConsensusAggregator**

Create `trading/tests/unit/test_consensus_aggregator.py`:

```python
import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from agents.models import AgentSignal
from data.signal_bus import SignalBus
from integrations.bittensor.consensus_aggregator import MinerConsensusAggregator

@pytest.mark.asyncio
async def test_consensus_aggregator_emits_consensus():
    signal_bus = SignalBus()
    aggregator = MinerConsensusAggregator(signal_bus, window_minutes=5)
    await aggregator.start()

    published_signals = []
    
    async def mock_publish(signal: AgentSignal):
        if signal.signal_type == "bittensor_consensus":
            published_signals.append(signal)

    signal_bus.publish = AsyncMock(side_effect=mock_publish)

    # Emit some miner positions
    now = datetime.now(timezone.utc)
    base_payload = {
        "symbol": "BTCUSD",
        "leverage": 1.0,
        "price": 65000.0,
        "open_ms": int(now.timestamp() * 1000)
    }

    # 3 bullish miners
    for i in range(3):
        payload = base_payload.copy()
        payload["miner_hotkey"] = f"hotkey{i}"
        payload["direction"] = "long"
        
        sig = AgentSignal(
            source_agent="taoshi_bridge",
            signal_type="bittensor_miner_position",
            payload=payload,
            expires_at=now + timedelta(minutes=30)
        )
        await aggregator._handle_miner_position(sig)

    # Wait for processing
    await asyncio.sleep(0.1)

    assert len(published_signals) > 0
    latest = published_signals[-1]
    assert latest.payload["symbol"] == "BTCUSD"
    assert latest.payload["direction"] == "bullish"
    assert latest.payload["confidence"] == 1.0
    assert latest.payload["miner_count"] == 3

    await aggregator.stop()

@pytest.mark.asyncio
async def test_stale_positions_are_ignored():
    signal_bus = SignalBus()
    aggregator = MinerConsensusAggregator(signal_bus, window_minutes=5)
    await aggregator.start()

    published_signals = []
    
    async def mock_publish(signal: AgentSignal):
        if signal.signal_type == "bittensor_consensus":
            published_signals.append(signal)

    signal_bus.publish = AsyncMock(side_effect=mock_publish)

    # Emit a stale miner position
    now = datetime.now(timezone.utc)
    payload = {
        "symbol": "ETHUSD",
        "miner_hotkey": "hotkey1",
        "direction": "long",
        "leverage": 1.0,
        "price": 3500.0,
        "open_ms": int((now - timedelta(minutes=10)).timestamp() * 1000) # 10 mins old
    }

    sig = AgentSignal(
        source_agent="taoshi_bridge",
        signal_type="bittensor_miner_position",
        payload=payload,
        expires_at=now + timedelta(minutes=30)
    )
    
    await aggregator._handle_miner_position(sig)
    await asyncio.sleep(0.1)

    # Should not emit consensus for purely stale data
    assert len(published_signals) == 0

    await aggregator.stop()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd trading && ./venv/bin/python -m pytest tests/unit/test_consensus_aggregator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'integrations.bittensor.consensus_aggregator'`

- [ ] **Step 3: Write minimal implementation**

Create `trading/integrations/bittensor/consensus_aggregator.py`:

```python
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from data.signal_bus import SignalBus
from agents.models import AgentSignal
from integrations.bittensor.signals import BittensorSignalPayload, create_bittensor_agent_signal

logger = logging.getLogger(__name__)

class MinerConsensusAggregator:
    """Aggregates individual bittensor_miner_position signals into bittensor_consensus signals."""

    def __init__(self, signal_bus: SignalBus, window_minutes: int = 5):
        self.signal_bus = signal_bus
        self.window_minutes = window_minutes
        # Store as: symbol -> hotkey -> (timestamp, payload)
        self.positions: dict[str, dict[str, tuple[datetime, dict]]] = defaultdict(dict)
        self._running = False
        self._lock = asyncio.Lock()

    async def start(self):
        self._running = True
        self.signal_bus.subscribe("bittensor_miner_position", self._handle_miner_position)
        logger.info(f"MinerConsensusAggregator started (window: {self.window_minutes}m)")

    async def stop(self):
        self._running = False

    async def _handle_miner_position(self, signal: AgentSignal):
        payload = signal.payload
        symbol = payload.get("symbol")
        hotkey = payload.get("miner_hotkey")
        open_ms = payload.get("open_ms", 0)

        if not symbol or not hotkey:
            return

        open_time = datetime.fromtimestamp(open_ms / 1000.0, tz=timezone.utc)

        async with self._lock:
            self.positions[symbol][hotkey] = (open_time, payload)
            await self._evaluate_consensus(symbol)

    async def _evaluate_consensus(self, symbol: str):
        now = datetime.now(timezone.utc)
        cutoff_time = now - timedelta(minutes=self.window_minutes)

        symbol_positions = self.positions[symbol]
        active_positions = {}

        for hotkey, (pos_time, payload) in list(symbol_positions.items()):
            if pos_time >= cutoff_time:
                active_positions[hotkey] = payload
            else:
                del symbol_positions[hotkey]

        if not active_positions:
            return

        direction_counts = {"long": 0, "short": 0, "flat": 0}
        total_leverage = 0.0

        for payload in active_positions.values():
            direction = payload.get("direction", "flat")
            if direction in direction_counts:
                direction_counts[direction] += 1
            total_leverage += payload.get("leverage", 0.0)

        total_miners = len(active_positions)
        if total_miners == 0:
            return

        # Determine majority
        majority_dir = max(direction_counts.items(), key=lambda x: x[1])
        dir_name, count = majority_dir

        if count == 0:
            return

        confidence = count / total_miners
        avg_leverage = total_leverage / total_miners

        # Map to expected consensus directions
        mapped_direction = "flat"
        if dir_name == "long":
            mapped_direction = "bullish"
        elif dir_name == "short":
            mapped_direction = "bearish"

        window_id = now.strftime("%Y%m%d-%H%M")

        consensus_payload = BittensorSignalPayload(
            symbol=symbol,
            timeframe="5m",
            direction=mapped_direction,
            confidence=confidence,
            expected_return=avg_leverage,  # using average leverage as a proxy
            window_id=window_id,
            miner_count=total_miners
        )

        consensus_signal = create_bittensor_agent_signal(
            payload=consensus_payload,
            source_agent="miner_consensus_aggregator",
            ttl_minutes=30
        )

        await self.signal_bus.publish(consensus_signal)

    def get_status(self) -> dict:
        """Returns the current aggregation state for monitoring."""
        status = {}
        now = datetime.now(timezone.utc)
        cutoff_time = now - timedelta(minutes=self.window_minutes)

        for symbol, hotkeys in self.positions.items():
            active_count = sum(1 for pos_time, _ in hotkeys.values() if pos_time >= cutoff_time)
            if active_count > 0:
                status[symbol] = {"active_miners": active_count}
                
        return status
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd trading && ./venv/bin/python -m pytest tests/unit/test_consensus_aggregator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add trading/integrations/bittensor/consensus_aggregator.py trading/tests/unit/test_consensus_aggregator.py
git commit -m "feat(bittensor): add MinerConsensusAggregator and unit tests"
```

---

### Task 2: Wire Aggregator into Application Lifespan

**Files:**
- Modify: `trading/api/app.py`
- Modify: `trading/api/routes/bittensor.py`

- [ ] **Step 1: Modify `trading/api/app.py`**

In `trading/api/app.py`, locate `_setup_bittensor_integration` and instantiate the aggregator:

```python
    # Find this section inside _setup_bittensor_integration
    if taoshi_root:
        from integrations.bittensor.taoshi_bridge import TaoshiBridge
        from integrations.bittensor.consensus_aggregator import MinerConsensusAggregator # ADD THIS

        bridge = TaoshiBridge(
            taoshi_root=taoshi_root,
            store=app.state.bittensor_store if hasattr(app.state, 'bittensor_store') else None,
            signal_bus=signal_bus,
            event_bus=event_bus,
            poll_interval=30.0,
        )
        app.state.taoshi_bridge = bridge
        task_mgr.create_task(bridge.run(), name="taoshi_bridge")
        logger.info("TaoshiBridge started (root=%s)", taoshi_root)
        
        # ADD THIS BLOCK
        aggregator = MinerConsensusAggregator(signal_bus=signal_bus, window_minutes=5)
        app.state.consensus_aggregator = aggregator
        task_mgr.create_task(aggregator.start(), name="consensus_aggregator")
        logger.info("MinerConsensusAggregator started")
```

- [ ] **Step 2: Modify `trading/api/routes/bittensor.py`**

Expose the aggregator status in the `/api/bittensor/status` endpoint. Ensure you are editing `trading/api/routes/bittensor.py`.

```python
# Look for the status endpoint:
@router.get("/status")
async def get_bittensor_status(request: Request):
    """Get the status of the Bittensor integration."""
    enabled = getattr(request.app.state, "bittensor_enabled_runtime", False)
    # ...
    bridge = getattr(request.app.state, "taoshi_bridge", None)
    if bridge:
        res["taoshi_bridge"] = {
            "root": str(bridge._root),
            "miners_tracked": bridge.miners_tracked,
            "open_positions": bridge.open_positions,
            "last_scan_at": bridge._last_scan_at.isoformat() if bridge._last_scan_at else None,
        }

    # ADD THIS BLOCK
    aggregator = getattr(request.app.state, "consensus_aggregator", None)
    if aggregator:
        res["consensus_aggregator"] = aggregator.get_status()

    return res
```

- [ ] **Step 3: Run the API health check / startup tests**

Run: `cd trading && ./venv/bin/python -m pytest tests/unit/test_api/ -v` (if applicable, or just start it briefly to see it doesn't crash). Alternatively, since there are no direct tests for the startup beyond E2E, we'll verify it in the next task via the E2E test.

- [ ] **Step 4: Commit**

```bash
git add trading/api/app.py trading/api/routes/bittensor.py
git commit -m "feat(bittensor): wire MinerConsensusAggregator into app lifecycle and status endpoint"
```

---

### Task 3: Update E2E Integration Test

**Files:**
- Modify: `trading/tests/integration/test_bittensor_e2e.py`

- [ ] **Step 1: Modify `trading/tests/integration/test_bittensor_e2e.py`**

Update the test to simulate signals coming from the bridge format and verify they go through the aggregator to the agent.

```python
import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta, timezone

from data.signal_bus import SignalBus
from integrations.bittensor.consensus_aggregator import MinerConsensusAggregator
from strategies.bittensor_consensus import BittensorAlphaAgent
from agents.models import AgentConfig, ActionLevel, AgentSignal
from agents.runner import AgentRunner

@pytest.mark.asyncio
async def test_bittensor_mock_e2e_loop():
    """
    E2E test:
    1. Spin up SignalBus
    2. Start MinerConsensusAggregator
    3. Register BittensorAlphaAgent
    4. Inject mock 'bittensor_miner_position' signals
    5. Wait for them to propagate into an Opportunity via the agent
    """
    signal_bus = SignalBus()

    # Configure agent with loose thresholds so it fires on mock signals
    agent_config = AgentConfig(
        name="bt_agent",
        strategy="bittensor_consensus",
        schedule="continuous",
        interval=1,
        action_level=ActionLevel.SUGGEST_TRADE,
        universe=["BTCUSD", "ETHUSD"],
        parameters={"min_agreement": 0.1, "min_return": 0.001},
    )
    agent = BittensorAlphaAgent(agent_config)
    agent.signal_bus = signal_bus
    await agent.setup()

    router = AsyncMock()
    runner = AgentRunner(data_bus=AsyncMock(), router=router)
    runner.register(agent)

    # Start Aggregator
    aggregator = MinerConsensusAggregator(signal_bus, window_minutes=5)
    await aggregator.start()

    # Simulate Bridge Emitting Miner Positions
    now = datetime.now(timezone.utc)
    base_payload = {
        "symbol": "BTCUSD",
        "leverage": 1.0,
        "price": 65000.0,
        "open_ms": int(now.timestamp() * 1000),
        "direction": "long",
        "miner_hotkey": "test_miner"
    }

    sig = AgentSignal(
        source_agent="taoshi_bridge",
        signal_type="bittensor_miner_position",
        payload=base_payload,
        expires_at=now + timedelta(minutes=30)
    )

    # Publish the raw position to the bus
    await signal_bus.publish(sig)

    # Give time for the aggregator to process and emit consensus, and agent to consume
    await asyncio.sleep(0.5)

    emitted_opps = await agent.scan(AsyncMock())

    await aggregator.stop()

    assert len(emitted_opps) > 0, "Agent did not emit any opportunities from aggregated signals"
    opp = emitted_opps[0]
    assert opp.agent_name == "bt_agent"
    assert opp.symbol.ticker == "BTC/USD"
    assert opp.signal in ["BULLISH", "BEARISH"]
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd trading && ./venv/bin/python -m pytest tests/integration/test_bittensor_e2e.py -v`
Expected: PASS

- [ ] **Step 3: Run Full Test Suite**

Run: `cd trading && ./venv/bin/python -m pytest tests/ -v`
Ensure all tests pass.

- [ ] **Step 4: Commit**

```bash
git add trading/tests/integration/test_bittensor_e2e.py
git commit -m "test(bittensor): update E2E test to use MinerConsensusAggregator"
```
