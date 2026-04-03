from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from observability.emitter import ObservabilityEmitter

logger = logging.getLogger(__name__)

_ISO_FORMATS = ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z")


def _parse_iso(ts: str) -> datetime:
    for fmt in _ISO_FORMATS:
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse timestamp: {ts!r}")


async def check_heartbeats(
    supabase_client: Any,
    emitter: "ObservabilityEmitter",
    threshold_seconds: int = 120,
) -> None:
    """Query agent_heartbeats; emit critical alert for any stale agent."""
    try:
        result = await (
            supabase_client.table("agent_heartbeats").select("*").execute()
        )
    except Exception:
        logger.exception("check_heartbeats: failed to query Supabase")
        return

    now = datetime.now(timezone.utc)
    for row in result.data:
        last_seen = _parse_iso(row["last_seen"])
        elapsed = (now - last_seen).total_seconds()
        if elapsed > threshold_seconds:
            await emitter.emit(
                event_type="agent_heartbeat_stale",
                level="critical",
                agent_name=row["agent_name"],
                message=(
                    f"agent {row['agent_name']} has not heartbeated in {int(elapsed)}s"
                ),
                metadata={"last_seen": row["last_seen"], "elapsed_seconds": int(elapsed)},
            )


async def heartbeat_watchdog_loop(
    supabase_client: Any,
    emitter: "ObservabilityEmitter",
    interval_seconds: int = 60,
    threshold_seconds: int = 120,
) -> None:
    """Run check_heartbeats on a fixed interval. Intended as an asyncio.Task."""
    while True:
        await asyncio.sleep(interval_seconds)
        await check_heartbeats(
            supabase_client=supabase_client,
            emitter=emitter,
            threshold_seconds=threshold_seconds,
        )
