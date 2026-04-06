from __future__ import annotations

import json
from datetime import datetime, timezone

import aiosqlite


class TournamentRunner:
    """
    Manages tournament rounds for continuous parameter refinement.

    The current live parameters are the "champion", random perturbations are
    "challengers". After the evaluation window, the best challenger can be
    promoted if it beats the champion by a configurable margin.
    """

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def start_round(
        self,
        *,
        agent_name: str,
        champion_params: dict,
        challenger_params_list: list[dict],
    ) -> int:
        """
        Insert a new tournament round and its variants.

        The champion is inserted first (variant_label='champion'), followed by
        each challenger (variant_label='challenger_N'). Returns the round_id.
        """
        started_at = datetime.now(timezone.utc).isoformat()
        cursor = await self.db.execute(
            """
            INSERT INTO tournament_rounds (agent_name, status, champion_params, started_at)
            VALUES (?, 'running', ?, ?)
            """,
            (agent_name, json.dumps(champion_params), started_at),
        )
        round_id = cursor.lastrowid

        await self.db.execute(
            """
            INSERT INTO tournament_variants (round_id, variant_label, parameters)
            VALUES (?, 'champion', ?)
            """,
            (round_id, json.dumps(champion_params)),
        )

        for i, params in enumerate(challenger_params_list):
            await self.db.execute(
                """
                INSERT INTO tournament_variants (round_id, variant_label, parameters)
                VALUES (?, ?, ?)
                """,
                (round_id, f"challenger_{i}", json.dumps(params)),
            )

        await self.db.commit()
        return round_id

    async def get_round(self, round_id: int) -> dict | None:
        """SELECT a single tournament round by id."""
        cursor = await self.db.execute(
            """
            SELECT id, agent_name, status, champion_params, started_at,
                   ended_at, winner_params, winner_sharpe, champion_sharpe
            FROM tournament_rounds
            WHERE id = ?
            """,
            (round_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._round_row_to_dict(row)

    async def get_active_round(self, agent_name: str) -> dict | None:
        """SELECT the first running round for an agent."""
        cursor = await self.db.execute(
            """
            SELECT id, agent_name, status, champion_params, started_at,
                   ended_at, winner_params, winner_sharpe, champion_sharpe
            FROM tournament_rounds
            WHERE agent_name = ? AND status = 'running'
            LIMIT 1
            """,
            (agent_name,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._round_row_to_dict(row)

    async def get_variants(self, round_id: int) -> list[dict]:
        """SELECT all variants for a round ordered by id."""
        cursor = await self.db.execute(
            """
            SELECT id, round_id, variant_label, parameters,
                   sharpe_ratio, profit_factor, total_pnl, total_trades
            FROM tournament_variants
            WHERE round_id = ?
            ORDER BY id
            """,
            (round_id,),
        )
        rows = await cursor.fetchall()
        return [self._variant_row_to_dict(row) for row in rows]

    async def update_variant(
        self,
        variant_id: int,
        *,
        sharpe_ratio: float,
        profit_factor: float,
        total_pnl: str,
        total_trades: int,
    ) -> None:
        """UPDATE performance metrics for a variant."""
        await self.db.execute(
            """
            UPDATE tournament_variants
            SET sharpe_ratio = ?, profit_factor = ?, total_pnl = ?, total_trades = ?
            WHERE id = ?
            """,
            (sharpe_ratio, profit_factor, total_pnl, total_trades, variant_id),
        )
        await self.db.commit()

    async def complete_round(
        self,
        round_id: int,
        *,
        promotion_margin: float = 0.10,
        min_trades: int = 30,
    ) -> dict | None:
        """
        Evaluate variants and complete the round.

        Champion is variants[0]. Finds the best challenger with >= min_trades
        and the highest sharpe. If the best challenger's sharpe beats the
        champion's sharpe by >= promotion_margin (relative), returns that
        challenger dict. Otherwise returns None.

        Updates the round to status='completed' and stores winner info.
        """
        variants = await self.get_variants(round_id)
        champion = variants[0]

        challengers = [
            v for v in variants[1:] if (v["total_trades"] or 0) >= min_trades
        ]

        winner: dict | None = None
        if challengers:
            best_challenger = max(
                challengers,
                key=lambda v: (
                    v["sharpe_ratio"]
                    if v["sharpe_ratio"] is not None
                    else float("-inf")
                ),
            )
            champion_sharpe = champion["sharpe_ratio"] or 0.0
            challenger_sharpe = best_challenger["sharpe_ratio"] or 0.0

            if champion_sharpe > 0 and challenger_sharpe >= champion_sharpe * (
                1 + promotion_margin
            ):
                winner = best_challenger
            elif champion_sharpe <= 0 and challenger_sharpe > champion_sharpe:
                # Edge case: champion has non-positive sharpe; any improvement wins
                winner = best_challenger

        ended_at = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            """
            UPDATE tournament_rounds
            SET status = 'completed',
                ended_at = ?,
                winner_params = ?,
                winner_sharpe = ?,
                champion_sharpe = ?
            WHERE id = ?
            """,
            (
                ended_at,
                json.dumps(winner["parameters"]) if winner else None,
                winner["sharpe_ratio"] if winner else None,
                champion["sharpe_ratio"],
                round_id,
            ),
        )
        await self.db.commit()

        return winner

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _round_row_to_dict(self, row: aiosqlite.Row) -> dict:
        return {
            "id": row[0],
            "agent_name": row[1],
            "status": row[2],
            "champion_params": json.loads(row[3]),
            "started_at": row[4],
            "ended_at": row[5],
            "winner_params": json.loads(row[6]) if row[6] else None,
            "winner_sharpe": row[7],
            "champion_sharpe": row[8],
        }

    def _variant_row_to_dict(self, row: aiosqlite.Row) -> dict:
        return {
            "id": row[0],
            "round_id": row[1],
            "variant_label": row[2],
            "parameters": json.loads(row[3]),
            "sharpe_ratio": row[4],
            "profit_factor": row[5],
            "total_pnl": row[6],
            "total_trades": row[7],
        }
