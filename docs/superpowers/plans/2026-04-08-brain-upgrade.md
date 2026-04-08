# "Brain" Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement two-phase index-guided strategy retrieval into the core trading loop so agents explicitly select strategy documents based on market regime context before scoring trades.

**Architecture:** 
1. `TradeReflector` gains a new `query_strategies` method which fetches the strategy index, queries the LLM for the most relevant strategy IDs, and then retrieves those full strategies via the memory client.
2. `OpportunityRouter` invokes this method during the annotation phase of `route()`, injecting the full strategy texts into `opportunity.data["strategies"]` so evaluating agents have explicit, compiled guidance.

**Tech Stack:** Python, FastAPI, LLMClient, AsyncRemembrClient

---

### Task 1: Add `query_strategies` to `TradeReflector`

**Files:**
- Modify: `trading/learning/trade_reflector.py`

- [x] **Step 1: Add the new two-phase retrieval method**
Inject this method into the `TradeReflector` class below the existing `query` method.

```python
    async def query_strategies(self, context_summary: str, max_strategies: int = 2) -> list[dict]:
        """Use LLM to select strategies from the index, then retrieve their full contents."""
        try:
            # 1. Get compressed index
            index = await self._client.get_index()
            if not index:
                return []

            # Format index for the prompt
            index_text = "\n".join(
                f"- ID: {item.get('id')}\n  Tags: {item.get('tags')}\n  Summary: {item.get('summary')}"
                for item in index
            )

            # 2. Ask LLM to select best strategy IDs
            prompt = (
                f"You are a trading strategy selector. Below is the current market context:\n"
                f"{context_summary}\n\n"
                f"Below is a catalog of available trading strategies:\n"
                f"{index_text}\n\n"
                f"Select up to {max_strategies} strategy IDs that are most relevant to the current market context. "
                "Return ONLY a comma-separated list of the raw IDs, with no other text, formatting, or explanation. "
                "If none are relevant, return the exact word: NONE."
            )
            
            result = await self._llm.complete(prompt, max_tokens=100)
            response_text = (result.text or "").strip()
            
            if not response_text or response_text.upper() == "NONE":
                return []
                
            # Parse CSV IDs, ignoring empty strings
            selected_ids = [s.strip() for s in response_text.split(",") if s.strip()]
            
            # 3. Retrieve full strategies
            if not selected_ids:
                return []
                
            full_strategies = await self._client.search_by_keys(selected_ids)
            return full_strategies
            
        except Exception as e:
            logger.warning("Strategy index query failed: %s", e)
            return []
```

### Task 2: Wire Index-Guided Retrieval into `OpportunityRouter`

**Files:**
- Modify: `trading/agents/router.py`

- [x] **Step 1: Inject strategies into the Opportunity context**
Find the `async def route` method in `OpportunityRouter` (around line 361) where the Deja Vu annotation happens. Add the strategy retrieval block right before or after it.

```python
            # --- Index-Guided Strategy Retrieval ---
            if self._trade_reflector:
                try:
                    regime_ctx = opportunity.data.get("regime")
                    regime_name = regime_ctx.name if regime_ctx else "unknown"
                    trend = regime_ctx.trend.value if regime_ctx and hasattr(regime_ctx, "trend") else "unknown"
                    
                    context_summary = (
                        f"Symbol: {opportunity.symbol.ticker}\n"
                        f"Signal Direction: {opportunity.signal}\n"
                        f"Market Regime: {regime_name}, Trend: {trend}"
                    )
                    
                    strategies = await self._trade_reflector.query_strategies(context_summary)
                    if strategies:
                        opportunity.data["strategies"] = [
                            s.get("value", "") for s in strategies
                        ]
                except Exception as _strat_exc:
                    logger.warning(
                        "Strategy retrieval failed for %s: %s", opportunity.id, _strat_exc
                    )
```

- [x] **Step 2: Commit the changes**

```bash
git add trading/learning/trade_reflector.py trading/agents/router.py
git commit -m "feat: implement two-phase index-guided strategy retrieval in core router"
```
