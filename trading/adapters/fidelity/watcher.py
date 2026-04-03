"""
FidelityFileWatcher — watches a directory for Fidelity CSV exports and
automatically imports them on detection.

Behaviour:
- On startup and every `poll_interval` seconds, scans `import_dir` for *.csv files
- Parses each file with FidelityCSVParser
- Imports via ExternalPortfolioStore
- On success: moves file to `import_dir/processed/` with a timestamp suffix
- On failure: moves file to `import_dir/failed/` and logs the error
- Files younger than `min_age_seconds` (default 3s) are skipped to avoid
  reading partially-written uploads

Usage (wired in api/app.py lifespan):
    watcher = FidelityFileWatcher(store=ext_store, import_dir=settings.import_dir)
    asyncio.create_task(watcher.run())
"""
from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from adapters.fidelity.parser import parse_fidelity_csv, extract_balances

logger = logging.getLogger(__name__)


class FidelityFileWatcher:
    def __init__(
        self,
        store,  # ExternalPortfolioStore — typed loosely to avoid circular import
        import_dir: str = "data/imports",
        poll_interval: int = 60,
        min_age_seconds: int = 3,
    ) -> None:
        self._store = store
        self._import_dir = Path(import_dir)
        self._poll_interval = poll_interval
        self._min_age_seconds = min_age_seconds
        self._processed_dir = self._import_dir / "processed"
        self._failed_dir = self._import_dir / "failed"

    def _ensure_dirs(self) -> None:
        self._import_dir.mkdir(parents=True, exist_ok=True)
        self._processed_dir.mkdir(parents=True, exist_ok=True)
        self._failed_dir.mkdir(parents=True, exist_ok=True)

    async def run(self) -> None:
        """Main loop — runs indefinitely as an asyncio task."""
        self._ensure_dirs()
        logger.info("FidelityFileWatcher started, watching %s", self._import_dir)
        while True:
            try:
                await self._scan()
            except asyncio.CancelledError:
                logger.info("FidelityFileWatcher stopped")
                return
            except Exception as exc:
                logger.error("FidelityFileWatcher scan error: %s", exc)
            await asyncio.sleep(self._poll_interval)

    async def _scan(self) -> None:
        self._ensure_dirs()
        candidates = list(self._import_dir.glob("*.csv"))
        if not candidates:
            return

        import time
        now = time.time()

        for path in candidates:
            try:
                age = now - path.stat().st_mtime
            except OSError:
                continue  # file disappeared between glob and stat

            if age < self._min_age_seconds:
                logger.debug("Skipping %s — too young (%.1fs)", path.name, age)
                continue

            await self._process_file(path)

    async def _process_file(self, path: Path) -> None:
        logger.info("FidelityFileWatcher: processing %s", path.name)
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            positions = parse_fidelity_csv(content)
            balances = extract_balances(content)

            if not positions and not balances:
                raise ValueError("No positions or balances found in CSV")

            # Group positions by account
            from collections import defaultdict
            by_account: dict[str, list] = defaultdict(list)
            for p in positions:
                by_account[p.account_id].append({
                    "symbol": p.symbol,
                    "description": p.description,
                    "quantity": str(p.quantity),
                    "last_price": str(p.last_price),
                    "current_value": str(p.current_value),
                    "cost_basis": str(p.cost_basis) if p.cost_basis is not None else None,
                })

            total_positions = 0
            total_accounts = 0
            for account_id, acct_positions in by_account.items():
                bal = balances.get(account_id)
                await self._store.import_positions(
                    broker="fidelity",
                    account_id=account_id,
                    account_name=bal.account_name if bal else "",
                    positions=acct_positions,
                    balance={
                        "net_liquidation": str(bal.net_liquidation) if bal else "0",
                        "cash": str(bal.cash) if bal else "0",
                    },
                )
                total_positions += len(acct_positions)
                total_accounts += 1

            # Import cash-only accounts that have balances but no positions
            for account_id, bal in balances.items():
                if account_id not in by_account:
                    await self._store.import_positions(
                        broker="fidelity",
                        account_id=account_id,
                        account_name=bal.account_name,
                        positions=[],
                        balance={
                            "net_liquidation": str(bal.net_liquidation),
                            "cash": str(bal.cash),
                        },
                    )
                    total_accounts += 1

            # Move to processed/
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            dest = self._processed_dir / f"{path.stem}_{ts}{path.suffix}"
            shutil.move(str(path), str(dest))
            logger.info(
                "FidelityFileWatcher: imported %d accounts, %d positions from %s → processed/",
                total_accounts, total_positions, path.name,
            )

        except Exception as exc:
            logger.error("FidelityFileWatcher: failed to process %s: %s", path.name, exc)
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            dest = self._failed_dir / f"{path.stem}_{ts}{path.suffix}"
            try:
                shutil.move(str(path), str(dest))
            except Exception as move_exc:
                logger.error("FidelityFileWatcher: also failed to move to failed/: %s", move_exc)
