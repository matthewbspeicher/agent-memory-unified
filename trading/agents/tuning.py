"""
AdaptiveTuner — evaluates agent performance and adjusts parameters.

Uses a fallback-chain LLM client (Anthropic → Groq → Ollama → rule-based)
for generating recommendations and parameter variants.
"""

import json
import logging
from typing import TYPE_CHECKING, Any

from llm.client import LLMClient

if TYPE_CHECKING:
    from agents.runner import AgentRunner
    from storage.trades import TradeStore
    from storage.opportunities import OpportunityStore

logger = logging.getLogger(__name__)

MIN_SAMPLE_SIZE = 20


class AdaptiveTuner:
    """
    Periodically evaluates agent performance and
    adjusts runtime parameters (execution-rate-based threshold adjustment).
    """

    def __init__(
        self,
        runner: "AgentRunner",
        opp_store: "OpportunityStore",
        trade_store: "TradeStore",
        trade_reflector_factory: Any | None = None,
        anthropic_key: str | None = None,
        groq_key: str | None = None,
        ollama_url: str = "http://localhost:11434",
    ) -> None:
        self._runner = runner
        self._opp_store = opp_store
        self._trade_store = trade_store
        self._reflector_factory = trade_reflector_factory

        # Unified LLM client with fallback chain
        self._llm = LLMClient(
            anthropic_key=anthropic_key,
            groq_key=groq_key,
            ollama_url=ollama_url,
        )

    async def get_agent_execution_rate(self, agent_name: str) -> tuple[float, int]:
        """
        Calculate the ratio of executed vs rejected opportunities.
        Note: this measures filter pass-through rate, NOT trade profitability.
        Returns (rate, sample_count).
        """
        opps = await self._opp_store.list(agent_name=agent_name, limit=100)
        if not opps:
            return 0.5, 0

        executed = sum(1 for o in opps if o["status"] == "executed")
        rejected = sum(1 for o in opps if o["status"] == "rejected")
        total = executed + rejected
        if total == 0:
            return 0.5, 0

        return executed / total, total

    async def tune_agent(self, agent_name: str) -> None:
        execution_rate, sample_count = await self.get_agent_execution_rate(agent_name)

        if sample_count < MIN_SAMPLE_SIZE:
            logger.debug(
                "Skipping tuning for %s: only %d samples (need %d)",
                agent_name,
                sample_count,
                MIN_SAMPLE_SIZE,
            )
            return

        agent_info = self._runner.get_agent_info(agent_name)
        if not agent_info:
            return

        config = agent_info.config
        confidence_threshold = config.parameters.get("confidence_threshold", 0.7)
        current_threshold = config.runtime_overrides.get(
            "confidence_threshold", confidence_threshold
        )

        overrides = config.runtime_overrides.copy()

        if execution_rate >= 0.6:
            new_threshold = max(0.1, current_threshold - 0.05)
            overrides["confidence_threshold"] = round(new_threshold, 2)
            logger.info(
                "Tuning %s: exec_rate=%.2f. Lowering threshold to %.2f",
                agent_name,
                execution_rate,
                new_threshold,
            )
        elif execution_rate <= 0.4:
            new_threshold = min(0.95, current_threshold + 0.05)
            overrides["confidence_threshold"] = round(new_threshold, 2)
            logger.info(
                "Tuning %s: exec_rate=%.2f. Raising threshold to %.2f",
                agent_name,
                execution_rate,
                new_threshold,
            )

        config.runtime_overrides = overrides

    async def generate_recommendations(
        self,
        agent_name: str,
        perf_snapshot: dict,
    ) -> str:
        execution_rate = perf_snapshot.get(
            "execution_rate", perf_snapshot.get("win_rate", 0.5)
        )

        # --- Qualitative Memory Retrieval ---
        reflections: list[str] = []
        if self._reflector_factory:
            try:
                reflector = self._reflector_factory(agent_name)
                memories = await reflector.query(
                    symbol="",
                    context="deep_reflection lessons",
                    agent_name=agent_name,
                    top_k=10,
                )
                reflections = [
                    m.get("value", "")
                    for m in memories
                    if "Key lesson" in m.get("value", "")
                ]
            except Exception as e:
                logger.warning(
                    "Failed to fetch reflections for tuning %s: %s", agent_name, e
                )

        metrics_summary = ", ".join(f"{k}={v}" for k, v in perf_snapshot.items())

        memory_context = ""
        if reflections:
            memory_context = "\n\nPast Qualitative Lessons Learned:\n- " + "\n- ".join(
                reflections[:5]
            )

        prompt = (
            f"Agent '{agent_name}' has the following performance metrics: {metrics_summary}."
            f"{memory_context}\n\n"
            "Based on both the quantitative metrics and the qualitative lessons from past trades, "
            "please provide 2-3 concise, actionable recommendations for improving this agent's "
            "strategy parameters (e.g., confidence_threshold, RSI periods, stop-loss levels) "
            "to increase profitability and reduce risk."
        )

        try:
            result = await self._llm.complete(prompt, max_tokens=500)
            if result.text:
                return result.text
        except Exception:
            pass

        # Rule-based fallback
        if execution_rate < 0.5:
            return "Execution rate below threshold: consider tightening confidence_threshold."
        return "Performance within acceptable range: monitor metrics and consider loosening confidence_threshold if execution rate improves."

    async def generate_parameter_variants(
        self,
        agent_name: str,
        strategy: str,
        base_params: dict,
        perf_snapshot: dict,
    ) -> list[dict]:
        """Generate parameter variants using fallback-chain LLM, returning JSON list of dicts."""
        metrics_summary = ", ".join(f"{k}={v}" for k, v in perf_snapshot.items())

        prompt = (
            f"Agent '{agent_name}' using strategy '{strategy}' has metrics: {metrics_summary}.\n"
            f"Its current parameters are: {json.dumps(base_params)}\n\n"
            "I want to explore new parameters to improve Sharpe ratio and profitability.\n"
            "Provide exactly 3 different variant configurations. Return ONLY a valid JSON array of 3 objects.\n"
            "Do not include any markdown formatting, backticks, or explanations, just the JSON array of objects."
        )

        try:
            result = await self._llm.complete(prompt, max_tokens=600)
            text_resp = result.text.strip()
            if text_resp.startswith("```"):
                lines = text_resp.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].startswith("```"):
                    lines = lines[:-1]
                text_resp = "\n".join(lines).strip()

            variants = json.loads(text_resp)
            if isinstance(variants, list) and len(variants) > 0:
                return variants
        except Exception as e:
            logger.warning("Failed to generate LLM variants for %s: %s", agent_name, e)

        return []

    async def run_tuning_cycle(self) -> None:
        for agent_info in self._runner.list_agents():
            await self.tune_agent(agent_info.name)

    async def grid_search(
        self,
        agent_name: str,
        param_space: dict[str, list],
        backtest_fn: Any,
    ) -> list[dict]:
        """Run grid search over parameter combinations.

        Args:
            agent_name: Agent to tune
            param_space: Dict mapping param names to lists of values
                        e.g. {"confidence_threshold": [0.5, 0.6, 0.7], "rsi_period": [7, 14, 21]}
            backtest_fn: Async callable(params: dict) -> dict with sharpe_ratio, win_rate, etc.

        Returns:
            List of result dicts sorted by sharpe_ratio descending.
        """
        import itertools

        param_names = list(param_space.keys())
        param_values = list(param_space.values())
        combinations = list(itertools.product(*param_values))

        logger.info(
            "Grid search for %s: %d combinations", agent_name, len(combinations)
        )

        results = []
        for combo in combinations:
            params = dict(zip(param_names, combo))
            try:
                metrics = await backtest_fn(params)
                results.append(
                    {
                        "params": params,
                        "sharpe_ratio": metrics.get("sharpe_ratio", 0.0),
                        "win_rate": metrics.get("win_rate", 0.0),
                        "max_drawdown": metrics.get("max_drawdown", 0.0),
                        "total_trades": metrics.get("total_trades", 0),
                    }
                )
            except Exception as e:
                logger.warning("Grid search failed for params %s: %s", params, e)

        results.sort(key=lambda x: x["sharpe_ratio"], reverse=True)

        if results:
            best = results[0]
            logger.info(
                "Grid search best for %s: params=%s, sharpe=%.3f",
                agent_name,
                best["params"],
                best["sharpe_ratio"],
            )

        return results

    async def genetic_optimize(
        self,
        agent_name: str,
        param_bounds: dict[str, tuple[float, float]],
        backtest_fn: Any,
        *,
        population_size: int = 20,
        generations: int = 10,
        mutation_rate: float = 0.1,
        elite_count: int = 2,
    ) -> dict:
        """Genetic algorithm for continuous parameter optimization.

        Args:
            agent_name: Agent to optimize
            param_bounds: Dict mapping param names to (min, max) tuples
                         e.g. {"confidence_threshold": (0.3, 0.9), "rsi_period": (5, 30)}
            backtest_fn: Async callable(params: dict) -> dict with sharpe_ratio
            population_size: Number of individuals per generation
            generations: Number of generations to evolve
            mutation_rate: Probability of mutation per gene
            elite_count: Number of top individuals to preserve

        Returns:
            Dict with best_params, best_sharpe, and evolution history.
        """
        import random

        param_names = list(param_bounds.keys())
        bounds = list(param_bounds.values())

        def random_individual():
            return {
                name: random.uniform(lo, hi)
                for name, (lo, hi) in zip(param_names, bounds)
            }

        def crossover(parent1: dict, parent2: dict) -> dict:
            child = {}
            for name in param_names:
                if random.random() < 0.5:
                    child[name] = parent1[name]
                else:
                    child[name] = parent2[name]
            return child

        def mutate(individual: dict) -> dict:
            mutated = individual.copy()
            for name, (lo, hi) in zip(param_names, bounds):
                if random.random() < mutation_rate:
                    range_size = hi - lo
                    delta = random.gauss(0, range_size * 0.1)
                    mutated[name] = max(lo, min(hi, individual[name] + delta))
            return mutated

        population = [random_individual() for _ in range(population_size)]
        history = []

        for gen in range(generations):
            scored = []
            for ind in population:
                try:
                    metrics = await backtest_fn(ind)
                    sharpe = metrics.get("sharpe_ratio", -999.0)
                except Exception:
                    sharpe = -999.0
                scored.append((ind, sharpe))

            scored.sort(key=lambda x: x[1], reverse=True)
            best_sharpe = scored[0][1]
            history.append({"generation": gen, "best_sharpe": best_sharpe})

            logger.info(
                "GA gen %d for %s: best_sharpe=%.3f", gen, agent_name, best_sharpe
            )

            elites = [ind for ind, _ in scored[:elite_count]]

            new_population = elites.copy()
            while len(new_population) < population_size:
                p1 = random.choice(elites)
                p2 = random.choice(elites)
                child = mutate(crossover(p1, p2))
                new_population.append(child)

            population = new_population

        final_best = scored[0]
        return {
            "best_params": final_best[0],
            "best_sharpe": final_best[1],
            "history": history,
        }

    async def monte_carlo_simulation(
        self,
        returns: list[float],
        *,
        n_simulations: int = 1000,
        n_periods: int = 252,
        confidence_level: float = 0.95,
    ) -> dict:
        """Monte Carlo simulation for confidence intervals on trading metrics.

        Uses bootstrap resampling of historical returns to project future performance.

        Args:
            returns: List of historical daily returns (e.g., [0.01, -0.005, ...])
            n_simulations: Number of Monte Carlo simulations to run
            n_periods: Number of future periods to simulate (default: 252 = 1 year)
            confidence_level: Confidence level for intervals (default: 0.95)

        Returns:
            Dict with mean, std, confidence intervals for: sharpe, cumulative_return, max_drawdown
        """
        import random
        import math

        if len(returns) < 10:
            return {"error": "Insufficient return data (need >= 10 samples)"}

        mean_return = sum(returns) / len(returns)
        std_return = math.sqrt(
            sum((r - mean_return) ** 2 for r in returns) / len(returns)
        )

        sharpe_results = []
        cum_return_results = []
        max_dd_results = []

        for _ in range(n_simulations):
            sim_returns = [random.choice(returns) for _ in range(n_periods)]

            cum_return = 1.0
            peak = 1.0
            max_dd = 0.0
            for r in sim_returns:
                cum_return *= 1 + r
                peak = max(peak, cum_return)
                dd = (peak - cum_return) / peak if peak > 0 else 0
                max_dd = max(max_dd, dd)

            annualized_return = cum_return ** (252 / n_periods) - 1
            sharpe = (
                (annualized_return - 0.04) / (std_return * math.sqrt(252))
                if std_return > 0
                else 0
            )

            sharpe_results.append(sharpe)
            cum_return_results.append(cum_return - 1)
            max_dd_results.append(max_dd)

        def percentile(sorted_list: list, p: float) -> float:
            idx = int(len(sorted_list) * p)
            return sorted_list[min(idx, len(sorted_list) - 1)]

        sorted_sharpe = sorted(sharpe_results)
        sorted_cum = sorted(cum_return_results)
        sorted_dd = sorted(max_dd_results)

        alpha = (1 - confidence_level) / 2

        return {
            "n_simulations": n_simulations,
            "n_periods": n_periods,
            "sharpe_ratio": {
                "mean": sum(sharpe_results) / len(sharpe_results),
                "std": math.sqrt(
                    sum(
                        (s - sum(sharpe_results) / len(sharpe_results)) ** 2
                        for s in sharpe_results
                    )
                    / len(sharpe_results)
                ),
                "ci_lower": percentile(sorted_sharpe, alpha),
                "ci_upper": percentile(sorted_sharpe, 1 - alpha),
            },
            "cumulative_return": {
                "mean": sum(cum_return_results) / len(cum_return_results),
                "ci_lower": percentile(sorted_cum, alpha),
                "ci_upper": percentile(sorted_cum, 1 - alpha),
            },
            "max_drawdown": {
                "mean": sum(max_dd_results) / len(max_dd_results),
                "ci_lower": percentile(sorted_dd, alpha),
                "ci_upper": percentile(sorted_dd, 1 - alpha),
            },
        }
