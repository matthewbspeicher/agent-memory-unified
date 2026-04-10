# ADR-0007: Two-Process Bittensor Validator Architecture

**Status**: accepted

**Date**: 2026-04-10
**Deciders**: Backfilled from existing implementation (originally established 2026-04-06 to 2026-04-09)

---

## Context

We run a Bittensor Subnet 8 (Taoshi PTN) validator. The validator needs to:

1. **Receive miner trade signals** via the Bittensor axon protocol on a fixed port
2. **Track positions** per miner hotkey and apply Taoshi-specific scoring, elimination, and plagiarism detection
3. **Feed those signals into our trading engine** so they can drive our own strategies and risk system
4. **Set on-chain weights** based on miner performance

The hard constraint we hit early on: the **official Taoshi validator codebase requires `bittensor==9.12.1`**. Our trading engine had already adopted `bittensor>=10.0.0` for its custom dendrite/scheduler/evaluator code, and v10 is not API-compatible with v9 (`bt.Subtensor` vs `bt.subtensor`, `network=` vs `chain_endpoint=`, plus a logger-level kill at import time on v10 that the trading engine has to defensively reset). Pinning the trading engine back to v9 would forfeit features we depend on; forking the Taoshi validator to v10 would break our ability to pull upstream updates.

We needed both to coexist on the same host without breaking either.

## Decision

Run the Bittensor validator as **two cooperating processes**, each in its own Python virtual environment, communicating via the **filesystem rather than IPC or network**:

```
Miners → Taoshi Validator (axon :8091) → validation/miners/{hotkey}/ files
                                              ↓
Trading Engine ← TaoshiBridge (polls files every 30s) → SignalBus → Trading Strategies
```

### Process 1: Official Taoshi Validator (`taoshi-vanta/`)

- Lives in its own directory mounted **read-only** into the trading container
- Runs in a separate venv with `bittensor==9.12.1`
- Receives miner signals via axon on port 8091
- Writes positions and scoring state to `validation/miners/{hotkey}/` flat files
- Owned by upstream Taoshi — we do not patch this code; updates are pulled from upstream

### Process 2: Trading Engine (`trading/`)

- Python 3.13, `bittensor>=10.0.0`, FastAPI on port 8080
- Runs the **`TaoshiBridge`** (`trading/integrations/bittensor/taoshi_bridge.py`) which polls Taoshi's position files every 30s, dedupes against last-seen state, and pushes new signals into the in-memory `SignalBus`
- Also runs our **own** scheduler (`scheduler.py`), evaluator (`evaluator.py`), and weight setter (`weight_setter.py`) for direct dendrite queries against the chain — these use the v10 API
- Defensive logger restoration after `import bittensor` because v10 silently sets all existing loggers to `CRITICAL`
- Wallet is reconstructed at container start by `docker-entrypoint.sh` from `B64_COLDKEY_PUB` and `B64_HOTKEY` env vars in `trading/.env`

### Coupling

- **Filesystem-only.** The trading engine reads `taoshi-vanta/validation/miners/` via the read-only mount. No HTTP, no socket, no shared memory.
- **30s poll interval.** Taoshi's position files are append-mostly; the bridge dedupes by signal id.
- **One-way.** Trading engine never writes to Taoshi's state; Taoshi knows nothing about the trading engine.

## Consequences

### Positive

- **Both bittensor versions coexist** without forking either codebase. Upstream Taoshi updates pull cleanly; trading-engine-side v10 features are unimpaired.
- **Isolation of failure modes.** Taoshi crash does not take down the trading engine API; trading engine restart does not interrupt miner signal ingest.
- **Clear ownership boundary.** Taoshi-vanta is read-only; bug reports go upstream. Our patches go in `trading/integrations/bittensor/taoshi_bridge.py` and never touch their code.
- **Filesystem coupling is debuggable.** A human can `cat validation/miners/{hotkey}/*.json` to see exactly what the bridge will see next. No protocol tracing required.
- **30s latency is acceptable.** Taoshi positions update on a slower cadence than that anyway (hash windows at :00 and :30).

### Negative

- **30-second polling latency** for signals to traverse Taoshi → Bridge → SignalBus. Not suitable if we ever need sub-second reaction to miner signals.
- **Two venvs to maintain.** Dependency drift between them (especially around `pydantic`, `numpy`, `torch`) has bitten us.
- **Two processes to monitor.** Health checks must cover both; the `/api/bittensor/status` endpoint reports bridge state but cannot directly observe Taoshi process health beyond "files are being updated."
- **Read-only mount means** no recovery actions from the trading engine when Taoshi misbehaves — only a human-initiated restart fixes a stuck Taoshi.
- **The defensive logger reset after `import bittensor`** is non-obvious and a frequent foot-gun (see CLAUDE.md "Working Boundaries").

### Neutral

- Wallet (coldkey `5D2bwSZYA6Lxhi76VaT52av6VDYU1fYYSFjzsPmPmM8J7Aqe`, hotkey `5DkVM4wyv4ZXGvb9ZmYafPiySbmWS4s2i5W37CNHuh4ggAha`, UID 144) is shared between both processes via the same wallet path
- Both processes target Subnet 8 on Finney
- Trading engine's own scheduler/evaluator/weight-setter and the file-poll bridge are **complementary** sources of miner data, not redundant — the scheduler queries the chain directly, the bridge reads what Taoshi has already filtered and scored

---

## Alternatives Considered

| Alternative | Pros | Cons |
|-------------|------|------|
| **Single process, pin to bittensor 9.12.1** | One venv, no bridge | Lose v10 features in trading engine; can't use new dendrite/scheduler APIs |
| **Single process, pin to bittensor >=10.0.0; fork Taoshi to v10** | One venv, latest API everywhere | Fork burden — must rebase every Taoshi upstream change; high risk of subtle scoring/elimination divergence |
| **Two processes, communicate via Redis pub/sub** | Lower latency than file polling | More moving parts, requires both processes to be Redis-aware, harder to debug; gains are marginal because Taoshi's update cadence is already slow |
| **Two processes, communicate via HTTP** | Standard pattern | Requires Taoshi to expose an HTTP server (it doesn't), or a sidecar shim; introduces a second axon-like surface area |
| **Two processes + filesystem polling (chosen)** | Zero invasive changes to upstream Taoshi; trivially debuggable; failure-isolated | 30s latency floor; polling overhead; no recovery loop when Taoshi is stuck |

---

## Notes

- Bridge implementation: `trading/integrations/bittensor/taoshi_bridge.py`
- Custom v10 dendrite path: `trading/integrations/bittensor/{adapter,scheduler,evaluator,weight_setter}.py`
- Configuration: `STA_BITTENSOR_*` env vars in `trading/.env` (see CLAUDE.md "Bittensor Config")
- Operational gotchas: `feedback_bittensor_v10_logging.md` and `feedback_bittensor_v10_api.md` in user memory; CLAUDE.md "Working Boundaries"
- Status endpoint: `GET /engine/v1/bittensor/status` (note: `/engine/v1/`, not `/api/`)
- This ADR formalizes a decision that was already in production; written 2026-04-10 to backfill the rationale before further changes.
