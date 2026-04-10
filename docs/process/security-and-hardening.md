# Security and Hardening

> Adapted from [addyosmani/agent-skills/skills/security-and-hardening](https://github.com/addyosmani/agent-skills/blob/main/skills/security-and-hardening/SKILL.md) (MIT). Examples and threat surfaces tailored to this repository — a Python/FastAPI trading engine + Bittensor validator + React frontend, with real broker credentials, real on-chain wallet keys, and real money at stake in live mode.

## Overview

Treat every external input as hostile, every secret as sacred, every authorization check as mandatory, and every irreversible action (broker order, on-chain weight set, wallet operation) as a kill-switch that must require deliberate human-confirmed intent.

This project's threat model is unusual:

- **Real money is one boolean away.** `STA_BROKER_MODE=paper` vs `live` is the difference between simulated trades and an IBKR account placing real orders. Code that silently flips this is the most dangerous bug we can ship.
- **The Bittensor wallet controls on-chain identity** for our validator on Subnet 8 (UID 144). A leaked hotkey lets an attacker impersonate the validator and set malicious weights.
- **Many third-party API keys** with monetary stakes: Alpaca, Tradier, BitGet, Polymarket, Kalshi. Most can place real orders.
- **The FastAPI trading engine has no user accounts** — auth is a single shared `STA_API_KEY` via `X-API-Key` header. Compromise of that key compromises everything.
- **The validator's `weight_setter.py` writes irreversible state to the Bittensor chain.** No undo. Already in CLAUDE.md "Working Boundaries → Ask first".

Security in this repo is not about CSRF tokens and password hashing — there are no user passwords. It's about **secret hygiene, broker-mode safety, wallet handling, on-chain irreversibility, and validating every signal that crosses an external boundary.**

## When to Use

- Building or modifying any FastAPI route under `trading/api/routes/`
- Touching anything that reads or transmits broker credentials (Alpaca, Tradier, IBKR, BitGet, Polymarket, Kalshi)
- Working in `trading/integrations/bittensor/` — especially `adapter.py`, `weight_setter.py`, or `taoshi_bridge.py`
- Editing `trading/docker-entrypoint.sh` or `scripts/reconstruct-wallet-wsl.sh` (wallet reconstruction)
- Modifying anything that handles `STA_API_KEY` validation or the WebSocket handshake at `/engine/v1/ws/public`
- Adding a new external integration (broker, exchange, data provider, LLM provider)
- Reviewing dependency updates that touch `cryptography`, `bittensor`, `httpx`, `psycopg2`, `pydantic`, or any broker SDK
- Before any commit that could plausibly contain a secret (always grep first — see Secret Hygiene below)
- When the user mentions paper-vs-live mode, flipping `STA_BROKER_MODE`, or "going live"

**When NOT to use:**

- Pure refactors of internal code paths that don't touch boundaries, secrets, brokers, or the wallet
- Frontend-only visual changes (Tailwind tweaks, layout)
- Test fixtures and tests of business logic that don't exercise auth paths

## The Three-Tier Boundary System

These reinforce CLAUDE.md "Working Boundaries". Where they overlap, CLAUDE.md is the canonical statement; this skill explains *why* and shows examples.

### Always Do (No Exceptions)

- **Validate all external input at the FastAPI route boundary** with a Pydantic v2 model. Never accept `dict[str, Any]` from a user-facing route.
- **Use parameterized SQL** via SQLAlchemy 2.x or psycopg with placeholders. Never f-string or `%`-format user input into SQL.
- **Use HTTPS for every external service call** — broker APIs, LLM providers, data feeds, Bittensor RPC. Never `http://` to a service that handles credentials or trades.
- **Validate `X-API-Key` on every protected route**. If a route doesn't have explicit authentication, it must be deliberately public (health, readiness) and documented as such.
- **Run `pip-audit` (or `uv pip audit`) before merging dependency changes** to `trading/pyproject.toml`. For frontend, `npm audit` before merging changes to `frontend/package.json`.
- **Default broker mode to paper.** Live mode requires `STA_BROKER_MODE=live` AND a non-empty `STA_API_KEY` AND deliberate human action. This invariant lives in `trading/config.py`.
- **Reconstruct the Bittensor wallet from env vars at container start, not from a baked-in file.** The pattern (`B64_COLDKEY_PUB` + `B64_HOTKEY` decoded by `docker-entrypoint.sh`) keeps the wallet out of the image and out of git. Preserve it.
- **Restore loggers immediately after `import bittensor`** (CLAUDE.md). Otherwise security-relevant log lines silently disappear.
- **`git add` files explicitly by name** (CLAUDE.md). Never `git add -A` or `git add .` — too many places a secret could slip in via test outputs, playwright artifacts, or stray notebooks.

### Ask First (Requires Human Approval)

- **Adding a new authentication mechanism** (JWT, OAuth, OIDC). Today the trading engine uses a single shared `X-API-Key`. Adding a second auth mechanism multiplies the attack surface and the misconfiguration surface.
- **Changing what `STA_BROKER_MODE=live` actually does** — removing safety checks, default-flipping, or auto-promoting from paper to live.
- **Touching `trading/integrations/bittensor/weight_setter.py`** or anything that calls `Subtensor.set_weights`. The action is irreversible and visible on chain.
- **Adding or removing items from the noisy-logger silence list** in `trading/utils/logging.py` — silencing the wrong logger could hide a security event.
- **Adding a new external integration** that requires a credential. Catalog it in `trading/.env.example`, document the rotation procedure in this doc, and confirm the gitignore will catch it.
- **Changing CORS configuration** on the FastAPI app or the Vite proxy.
- **Modifying rate limiting or throttling** on any FastAPI route.
- **Reading wallet files directly** instead of using the env-var reconstruction path.
- **Disabling `STA_DATABASE_SSL_VERIFY`** outside of the pooler context (`STA_DATABASE_SSL_VERIFY=false` is intentional for the Supabase transaction-mode pooler — see `trading/.env.example` — but is *not* a license to disable it elsewhere).

### Never Do

- **Never commit `.env`, `.env.wallet`, `*.env.wallet`, broker credential files, or wallet files** to git. The `.gitignore` already excludes `.env`, `.env.local`, and `*.env.wallet`. **Verify before every commit** with the secret-scanner snippet in this doc.
- **Never log API keys, broker credentials, JWT secrets, wallet bytes, or `STA_*_PRIVATE_KEY` env vars.** Not at INFO, not at DEBUG. The structured logging convention (ADR-0008) does not include a `credential` event type and never will.
- **Never trust a request's `client_id` or `account_id` field as authorization.** It's user input. Look up the resource and check ownership.
- **Never invoke the `eval` / `exec` family of Python builtins, or run `subprocess` calls in shell mode, on any user-derived string.** These are arbitrary-code-execution primitives.
- **Never bypass Pydantic validation** by accepting `Request` directly and parsing the body manually unless there's a documented reason and an explicit second validation step.
- **Never expose internal stack traces or DB error messages** in API responses. Wrap with a sanitized error envelope.
- **Never store wallet bytes, broker credentials, or `STA_API_KEY` in the database.** Env vars only. If a secret needs to be discovered at runtime, fetch it from a secrets manager — not the same Postgres instance the trading engine reads positions from.
- **Never replace the `STA_BROKER_MODE` default of `paper`** with `live`. Live must be opt-in per environment, never per code default.
- **Never paste real broker credentials, real wallet bytes, or real `STA_API_KEY` values into this conversation, into a commit message, into a log line, or into any file under `frontend/test-results/`, `frontend/playwright-report/`, or any directory git might pick up.**

## OWASP Top 10 — Adapted to This Project

### 1. Injection (SQL, NoSQL, OS Command, Prompt Injection)

```python
# BAD: SQL injection via f-string
cursor.execute(f"SELECT * FROM positions WHERE account_id = '{account_id}'")

# GOOD: Parameterized
cursor.execute("SELECT * FROM positions WHERE account_id = %s", (account_id,))

# GOOD: SQLAlchemy 2.x style
stmt = select(Position).where(Position.account_id == account_id)
positions = session.execute(stmt).scalars().all()
```

(`cursor.execute` and `session.execute` are the *parameterized* DB-API methods. The Python `eval` / `exec` builtins are a different family entirely — those should never appear in this codebase.)

**Prompt injection** is real for the LLM-backed strategies (`trading/strategies/llm_analyst.py`, `trading/llm/client.py`). Treat any text that flows into an LLM prompt — news headlines, social posts, miner-supplied metadata — as untrusted. Never let LLM output directly drive a broker order without a structured validator and a paper-mode rehearsal.

```python
# BAD: News headline → LLM → broker order, no validation
order_intent = llm.complete(f"Decide trade: {headline}")
broker.place_order(parse(order_intent))
# what if the LLM hallucinates a 10000-share buy?

# GOOD: LLM output goes through Pydantic validation, position-size limits,
# and paper mode by default
class OrderIntent(BaseModel):
    symbol: str = Field(pattern=r"^[A-Z]{1,5}$")
    side: Literal["buy", "sell"]
    quantity: int = Field(gt=0, le=100)  # hard cap
    confidence: float = Field(ge=0, le=1)

raw = llm.complete_structured(prompt, schema=OrderIntent)
if raw.confidence < 0.7 or config.broker_mode != "live":
    log_event(logger, INFO, "trade.decision", "skipped",
              {"reason": "low_conf_or_paper"})
    return
broker.place_order(raw)
```

### 2. Broken Authentication

We have a single shared `X-API-Key`. The attack surface is small but unforgiving:

```python
# trading/api/dependencies.py (or wherever your dep is)
from fastapi import Header, HTTPException, status
from trading.config import load_config

config = load_config()

async def require_api_key(x_api_key: str = Header(None)) -> None:
    if config.api_key is None:
        # In dev with no key set, allow everything but log loudly
        return
    if not x_api_key or not _constant_time_eq(x_api_key, config.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid api key",
        )

def _constant_time_eq(a: str, b: str) -> bool:
    import hmac
    return hmac.compare_digest(a.encode(), b.encode())
```

Two non-obvious points:
- **Constant-time comparison** matters even for an API key — a naive `==` leaks length and prefix via timing.
- **The dev fallback** (no key set → allow everything) is convenient but dangerous if `STA_API_KEY` is accidentally unset in production. Add a startup check that refuses to bind to a non-localhost interface without a key set.

The legacy `JWT_SECRET=CHANGE_ME_TO_256_BIT_SECRET` placeholder in `trading/.env.example` is a footgun left over from the Laravel era. If you add a real JWT auth path, **delete that placeholder** in the same commit so it can't be copied unchanged into a `.env`.

### 3. Cross-Site Scripting (XSS)

React 19 auto-escapes JSX text — by default, every `{value}` in JSX is rendered as text, never as markup. The footgun is React's raw-HTML escape hatch (the `dangerously*` family of props). Treat any use of that escape hatch as a security review trigger.

```typescript
// SAFE: React renders this as text, never as markup
<div>{agentResponse}</div>

// SAFE: if you must inject HTML, sanitize first with DOMPurify
import DOMPurify from 'dompurify';
const cleaned = DOMPurify.sanitize(agentResponse);
// ...then pass cleaned to the raw-HTML prop
```

The two rules are: (1) never reach for the raw-HTML escape hatch with content that came from a user, an LLM, or a third-party API without sanitizing it first with a real HTML sanitizer; (2) treat React's raw-HTML escape hatch, the `Function` constructor, the `eval` builtin, and any legacy direct-DOM-write APIs as a fixed grep list — anything matching them in `frontend/src/` deserves a second look during review. Periodic check: search `frontend/src/` for occurrences of those identifiers and treat each hit as a review item.

### 4. Broken Access Control

The trading engine doesn't have user accounts, but it has resources scoped to a broker account. Always verify the caller's claim:

```python
# BAD: trust the path parameter
@router.get("/portfolio/{account_id}")
async def get_portfolio(account_id: str):
    return broker.get_positions(account_id)

# GOOD: the api key holder is implicitly the operator;
# scope to the configured account, not arbitrary input
@router.get("/portfolio")
async def get_portfolio(_: None = Depends(require_api_key)):
    return broker.get_positions(config.broker_account_id)
```

If you ever introduce multi-tenant access, every protected route needs an ownership check, not just an auth check.

### 5. Security Misconfiguration

```python
# trading/api/app.py — CORS
from fastapi.middleware.cors import CORSMiddleware

allowed_origins = (config.cors_allowed_origins or "").split(",")
allowed_origins = [o.strip() for o in allowed_origins if o.strip()]
if not allowed_origins:
    # Default to localhost dev only — NEVER "*" in this app
    allowed_origins = ["http://localhost:3000", "http://localhost:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)
```

Wildcard `*` origin with `allow_credentials=True` is a footgun — most browsers will reject it, but the misconfiguration is a sign the security model is unclear. If you need broader access, list the origins.

### 6. Sensitive Data Exposure

Never return wallet bytes, broker credentials, raw API keys, or password hashes (we don't have any, but if you add them) in API responses. Strip on the way out:

```python
# Pydantic response models with explicit fields
class PortfolioResponse(BaseModel):
    account_id: str  # public
    cash: Decimal
    positions: list[PositionPublic]
    # NOTE: do NOT include broker_credentials, ib_session_token, etc.

class PositionPublic(BaseModel):
    symbol: str
    quantity: int
    avg_price: Decimal
    unrealized_pnl: Decimal
    # NOTE: do NOT include order_id internals or routing metadata
```

For LLM provider responses, watch for echoed prompts that may contain secrets you don't want round-tripped through a third party. Sanitize before sending.

### 7. Wallet and On-Chain Operations

The Bittensor wallet is the most sensitive secret in this repository:

- **Coldkey (`B64_COLDKEY_PUB`)** is base64-encoded in env vars and reconstructed at container start by `trading/docker-entrypoint.sh`. The private coldkey **is never on the host** — only the validator hotkey is reconstructed for signing.
- **Hotkey (`B64_HOTKEY`)** signs weight-setting transactions. A leaked hotkey lets an attacker set arbitrary weights as our validator (UID 144 on Subnet 8).
- **Wallet files at `~/.bittensor/wallets/sta_wallet/`** are reconstructed at runtime, not stored in the image or in git. Verify with `cat .gitignore | grep -i wallet` and `cat .dockerignore | grep -i wallet`.

When you touch wallet code:

```bash
# Before any wallet-touching commit:
git diff --cached -- 'trading/docker-entrypoint.sh' \
                     'scripts/reconstruct-wallet-wsl.sh' \
                     'trading/integrations/bittensor/'
git diff --cached | grep -iE 'B64_COLDKEY|B64_HOTKEY|coldkey|hotkey' | head -50
```

If any actual base64 wallet bytes appear in the diff — **stop, unstage, rotate the wallet**. Treat it as a leaked secret regardless of how briefly it was staged.

The `weight_setter.py` is the only path that calls `Subtensor.set_weights`. Changes to it require explicit user approval (CLAUDE.md "Ask first") because the action is irreversible on-chain.

### 8. Broker Mode Safety

`STA_BROKER_MODE` is the most consequential boolean in the project. Defenses:

```python
# trading/config.py — invariants enforced at config load
@dataclass
class TradingConfig:
    broker_mode: Literal["paper", "live"] = "paper"  # default is safe
    api_key: str | None = None
    # ...

    def __post_init__(self):
        if self.broker_mode == "live":
            if not self.api_key:
                raise ConfigError(
                    "STA_BROKER_MODE=live requires STA_API_KEY"
                )
            if self.api_host not in ("127.0.0.1", "localhost") and not self.tls_cert:
                raise ConfigError("live mode on non-localhost requires TLS")
            log_event(logger, WARNING, "config", "LIVE BROKER MODE ENABLED",
                      {"host": self.api_host, "broker": self.broker})
```

Never write code that flips `broker_mode` at runtime based on a request, an env var read mid-process, or an LLM decision. The mode is set once at startup.

## Input Validation Patterns

Validate at the FastAPI route boundary with Pydantic v2. Never accept `dict[str, Any]`:

```python
from pydantic import BaseModel, Field, field_validator
from typing import Literal

class CreateOrderRequest(BaseModel):
    symbol: str = Field(pattern=r"^[A-Z]{1,5}$", description="US equity ticker")
    side: Literal["buy", "sell"]
    quantity: int = Field(gt=0, le=10_000)  # hard cap to prevent fat-finger
    order_type: Literal["market", "limit"]
    limit_price: float | None = Field(default=None, gt=0, le=1_000_000)

    @field_validator("limit_price")
    @classmethod
    def limit_price_required_for_limit_orders(cls, v, info):
        if info.data.get("order_type") == "limit" and v is None:
            raise ValueError("limit_price required for limit orders")
        return v


@router.post("/orders", status_code=201)
async def create_order(
    req: CreateOrderRequest,
    _: None = Depends(require_api_key),
):
    # req is validated, typed, and bounded
    return await broker.place_order(req)
```

The `quantity` upper bound is a fat-finger guard — even if the API key holder is malicious, they cannot place a billion-share order in one request.

## Triaging Vulnerability Scanner Results

```
Scanner reports a vulnerability
├── Severity: critical or high
│   ├── In the trading engine path, broker integration, or wallet handling?
│   │   ├── YES → Fix immediately, halt the merge until patched
│   │   └── NO (dev-only dep, unused code path) → Fix soon, but not a blocker
│   └── Is a fix available?
│       ├── YES → Update to the patched version
│       └── NO → Check for workarounds, consider replacing the dependency,
│                 or document an exception with a review date
├── Severity: moderate
│   ├── Reachable in production? → Fix in the next release cycle
│   └── Dev-only? → Fix when convenient, track in backlog
└── Severity: low
    └── Track and fix during regular dependency updates
```

**Always-prioritize regardless of severity:** anything in `cryptography`, `bittensor`, `httpx`, `requests`, `urllib3`, `psycopg`/`psycopg2`, or any broker SDK. These touch credentials, network, or the chain.

## Secret Hygiene

### What's already protected

```bash
# .gitignore (current state, verified 2026-04-10)
.env
.env.local
*.env.wallet
```

### Pre-commit secret scan

Always run before committing changes that touch `trading/`, `frontend/`, or `scripts/`:

```bash
# Look for staged secrets — ANY hit is suspicious
git diff --cached | grep -iE 'STA_[A-Z_]*_KEY|STA_[A-Z_]*_SECRET|STA_[A-Z_]*_TOKEN|B64_COLDKEY|B64_HOTKEY|JWT_SECRET=[^C]|password\s*=|api[_-]?key\s*=' | head -50

# Look for .env files accidentally staged
git diff --cached --name-only | grep -E '^\.env|\.env\.wallet|wallet\.json|coldkey|hotkey'
```

If anything matches, **unstage and investigate** before continuing. Don't `git stash` your way out of a leak.

### Credential rotation cheatsheet

| Credential | If leaked, rotate via |
|---|---|
| `STA_API_KEY` | Regenerate, update `trading/.env`, restart trading container, update frontend `VITE_TRADING_API_KEY` |
| `STA_ANTHROPIC_API_KEY` | Anthropic console → revoke key → generate new |
| `STA_GROQ_API_KEY` | Groq console → revoke → generate new |
| `STA_ALPACA_*` | Alpaca dashboard → revoke → generate new pair |
| `STA_TRADIER_TOKEN` | Tradier dashboard → revoke → generate new |
| `STA_BITGET_*` | BitGet API key management → revoke triplet → generate new |
| `STA_KALSHI_*` | Kalshi key management → generate new keypair → upload private key |
| `STA_POLYMARKET_*` | Polymarket API → revoke → generate new |
| `STA_WHATSAPP_TOKEN` | Meta developer console → revoke → generate new |
| `STA_DATABASE_URL` | Supabase project → reset password → update connection string everywhere |
| `B64_COLDKEY_PUB` + `B64_HOTKEY` | Generate a new wallet via `btcli wallet new_coldkey` + `btcli wallet new_hotkey`, register the new hotkey on subnet 8, deregister the old, update env vars. **This is operationally expensive — preserving wallet secrecy is cheaper than rotating.** |
| `JWT_SECRET` | Currently unused (Laravel era). If reintroduced, generate via `openssl rand -base64 32` |

## Security Review Checklist

Before merging changes that touch security boundaries:

- [ ] No secrets in staged diff (run the grep above)
- [ ] No `.env*` files staged
- [ ] All new FastAPI routes have an `X-API-Key` dependency unless deliberately public (health, readiness)
- [ ] All new request bodies are typed Pydantic models with field validators and bounded numeric fields
- [ ] Any new SQL is parameterized
- [ ] Any new HTTP client uses `https://`
- [ ] Any new external integration is documented in `trading/.env.example` and the rotation cheatsheet above
- [ ] If touching `trading/integrations/bittensor/weight_setter.py` or `docker-entrypoint.sh`, the user explicitly approved the change
- [ ] If touching anything LLM-facing (`trading/strategies/llm_analyst.py`, `trading/llm/client.py`), the prompt-injection guards are in place
- [ ] `pip-audit` (or `uv pip audit`) clean for trading; `npm audit` clean for frontend
- [ ] No new uses of Python's `eval`/`exec` builtins, no shell-mode subprocess calls, no React raw-HTML escape hatches without DOMPurify

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "It's paper mode, security doesn't matter" | The same code runs in live mode. Habits formed in paper mode are the habits that ship to live. |
| "We'll add auth later" | The trading engine is *one* shared API key away from a broker account. "Later" has been "never" in every project that said it. |
| "No one would attack a small validator" | Bittensor validators sign on-chain weights for real TAO emissions. Attackers absolutely target them. |
| "The framework handles input validation" | FastAPI validates *if* you give it a Pydantic model. `dict[str, Any]` opts out of every protection. |
| "It's just a private key in env vars, not in code" | Env vars leak via crashes, log lines, error pages, child processes, container inspection, and hung debuggers. Every secret needs a rotation plan. |
| "I'll log the request body for debugging" | Request bodies contain credentials, order details, account ids. Log structured event types instead (ADR-0008). |
| "The wallet is reconstructed from env vars, that's safe" | The reconstruction is safe; the env var values are still secrets. Same threat model as a key file. |
| "The CLAUDE.md Boundaries already cover this" | CLAUDE.md is the rules; this skill is the *why* and the examples. Use both. |

## Red Flags

Stop and verify if you catch yourself doing any of these:

- Writing a route that takes `request: Request` and parses `await request.json()` manually
- Adding a broad `try` / `except Exception: pass` around a broker call
- Logging anything that contains `STA_`, `B64_`, `api_key`, `secret`, `token`, or `password`
- Building a shell command string from request data and handing it to `subprocess`
- Reaching for Python's `eval` or `exec` builtins anywhere in the trading engine
- Reading wallet files instead of going through the env-var reconstruction
- Hardcoding `STA_BROKER_MODE = "live"` anywhere in source
- Adding a route under `trading/api/routes/` without an `X-API-Key` dependency
- Editing `weight_setter.py` without a user-approved task
- Pasting a real key value into a test fixture, a docstring, or a sample config
- Disabling SSL verification on a database or broker connection
- `git add -A` or `git add .` (CLAUDE.md → Never)
- Returning a stack trace, SQL error, or internal exception in an HTTP response

## Verification

After implementing security-relevant code, confirm all of these:

- [ ] Pre-commit secret scan clean (grep above)
- [ ] No secrets in source or in the staged diff
- [ ] All user input validated with Pydantic v2 models
- [ ] `X-API-Key` dependency on every protected route
- [ ] All new HTTP client calls use HTTPS
- [ ] Errors return sanitized envelopes, not stack traces
- [ ] `pip-audit` / `npm audit` clean for changed dependency files
- [ ] If wallet/weight-setter touched, the user approved the change in the same conversation
- [ ] If broker mode logic touched, paper-mode default is preserved
- [ ] Structured logging used; no raw secrets in log lines
- [ ] CLAUDE.md "Working Boundaries" rules still hold

---

*Adapted from [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills/blob/main/skills/security-and-hardening/SKILL.md) under MIT license. Stack examples (FastAPI, Pydantic v2, SQLAlchemy 2.x), credential inventory (`STA_*` + `B64_*`), threat model (broker mode, on-chain weight setter, wallet env-var reconstruction), and rotation cheatsheet are specific to this repository.*
