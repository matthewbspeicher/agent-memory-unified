"""Owned storage lifecycle and bounded, read-only checks of configured stores.

These checks establish initialized structure and readability, not permission to
write, order admission, or worker health. Schema creation remains with its owners.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging

from storage.db import DatabaseConnection
from storage.inspection import CheckIssue, inspect_tables

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class StorageReport:
    ready: bool
    phase: str
    issues: tuple[CheckIssue, ...] = ()


class StorageUnavailable(RuntimeError):
    def __init__(self, report: StorageReport):
        self.report = report
        # Never include driver errors, connection strings or stored data.
        super().__init__(
            "Required storage unavailable: "
            + ", ".join(issue.name for issue in report.issues)
        )


# Explicit projections catch absent columns even on empty tables. Keep eager
# requirements here; paper_entry_exit_handoffs is deliberately provisioned lazily.
_CORE = {
    "opportunities": "id agent_name symbol signal confidence reasoning suggested_trade status expires_at data created_at updated_at",
    "trade_executions": "id opportunity_id agent_name order_result risk_evaluation created_at updated_at",
    "risk_events": "id event_type details created_at",
    "tracked_positions": "id agent_name opportunity_id symbol side entry_price entry_quantity entry_fees entry_time exit_price exit_fees exit_time exit_reason max_adverse_excursion status expires_at broker_id account_id created_at",
    "position_exit_rules": "position_id rules_json created_at",
}
_JOBS = {
    "paper_fill_jobs": "job_id broker_id account_id signal_id order_id role position_id payload done"
}
_MATCHING = {"paper_auto_ticks": "event_id sample_id"}


class StorageSession:
    """Retain one owner; certify after the existing store owners initialize.

    Enter once. Bind actual paper/tracking stores at certification; subsequent
    calls cannot replace those stores. A pending or closed session is never ready.
    A transient read failure after certification can recover on the next check.
    """

    def __init__(self, config, *, timeout_seconds: float = 3.0):
        if not 0 < timeout_seconds <= 30:
            raise ValueError("Storage check timeout must be in (0, 30]")
        self._owner = DatabaseConnection(config)
        self._paper = bool(config.paper_trading)
        self._reconcile = self._paper and not config.worker_mode
        self._matching = self._reconcile and config.paper_matching_enabled
        self._timeout = timeout_seconds
        self._phase = "pending"
        self._entered = False
        self._certified = False
        self._bindings = None
        self.db = None

    @property
    def initialization(self):
        return self._owner.initialization

    async def __aenter__(self):
        if self._entered:
            raise RuntimeError("Storage session cannot be reopened")
        self._entered = True
        try:
            self.db = await self._owner.connect()
        except BaseException:
            self._phase = "closed"
            raise
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        self._phase = "closed"
        try:
            await self._owner.close()
        except BaseException:
            if exc_type is None:
                raise
            log.warning("Storage cleanup failed while handling %s", exc_type.__name__)

    async def certify(self, *, paper_store=None, position_store=None) -> StorageReport:
        bindings = (paper_store, position_store)
        if self._bindings is not None and any(
            old is not new for old, new in zip(self._bindings, bindings)
        ):
            raise ValueError("Storage certification bindings cannot change")
        self._bindings = bindings
        report = await self._assess()
        if not report.ready:
            raise StorageUnavailable(report)
        self._certified = True
        self._phase = "ready"
        return StorageReport(True, self._phase)

    async def check(self) -> StorageReport:
        if not self._certified:
            return StorageReport(
                False, self._phase, (CheckIssue("initialization", "Incomplete"),)
            )
        return await self._assess()

    async def _assess(self) -> StorageReport:
        if self._phase == "closed" or self.db is None:
            return StorageReport(
                False, self._phase, (CheckIssue("connection", "Unavailable"),)
            )
        issues: list[CheckIssue] = []
        try:
            async with asyncio.timeout(self._timeout):
                issues.extend(await inspect_tables(self.db, _CORE))
                paper, positions = self._bindings or (None, None)
                if self._paper:
                    if paper is None:
                        issues.append(CheckIssue("paper_store", "Missing"))
                    else:
                        paper_issues = await paper.check_storage()
                        issues.extend(paper_issues)
                        if not paper_issues and self._reconcile:
                            await self._probe_store(paper, _JOBS, issues)
                        if not paper_issues and self._matching:
                            await self._probe_store(paper, _MATCHING, issues)
                if self._reconcile:
                    if positions is None:
                        issues.append(CheckIssue("position_store", "Missing"))
                    else:
                        issues.extend(await positions.check_storage())
        except Exception as error:
            issues.append(CheckIssue("storage_check", type(error).__name__))
        # Closure can race a live readiness request; never publish ready afterward.
        return StorageReport(
            not issues and self._phase != "closed", self._phase, tuple(issues)
        )

    async def _probe_store(self, store, tables, issues):
        try:
            # Jobs/matching belong to their existing owners but use this ledger's
            # actual handle. Do not open a transaction or run their initializers.
            issues.extend(await inspect_tables(await store._get_db(), tables))
        except Exception as error:
            issues.append(CheckIssue(next(iter(tables)), type(error).__name__))
