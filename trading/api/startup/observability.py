"""Observability, journal, and WhatsApp notification startup."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from config import Config
    
logger = logging.getLogger(__name__)


async def setup_journal(
    config: Config,
    event_bus: Any,
    task_manager: Any,
) -> tuple[Any, Any]:
    """
    Initialize journal manager and optional vector indexer.
    
    Returns:
        (journal_manager, journal_indexer) or (None, None) if not configured
    """
    if not config.remembr_agent_token:
        return None, None
    
    try:
        from remembr.client import AsyncRemembrClient
        from journal.manager import JournalManager

        _remembr_client = AsyncRemembrClient(
            agent_token=config.remembr_agent_token,
            base_url=config.remembr_base_url,
        )

        journal_indexer = None
        if config.journal_index_enabled:
            try:
                from journal.indexer import JournalIndexer

                journal_indexer = JournalIndexer(
                    event_bus=event_bus,
                    remembr_client=_remembr_client,
                    gpu_enabled=config.gpu_enabled,
                    model_name=config.journal_index_model,
                    index_path=config.journal_index_path,
                    space=config.journal_index_space,
                    ef_construction=config.journal_index_ef_construction,
                    m=config.journal_index_m,
                    ef_search=config.journal_index_ef_search,
                    max_elements=config.journal_index_max_elements,
                )
                await journal_indexer.start()
                logger.info("JournalIndexer started (background rehydration)")

                from journal.persistence_task import journal_persistence_loop

                task_manager.create_task(
                    journal_persistence_loop(journal_indexer, config),
                    name="journal_persistence"
                )
                logger.info("Journal persistence loop launched")
            except ImportError:
                logger.warning(
                    "sentence-transformers/hnswlib not installed — indexer disabled"
                )
            except Exception as idx_exc:
                logger.warning("JournalIndexer startup failed: %s", idx_exc)

        journal_manager = JournalManager(
            client=_remembr_client,
            event_bus=event_bus,
            indexer=journal_indexer,
            oracle_url=config.oracle_url,
        )
        logger.info("JournalManager initialized for semantic trade memory")
        return journal_manager, journal_indexer
    except ImportError:
        logger.warning("remembr SDK not installed. Skipping JournalManager.")
        return None, None


async def setup_observability(
    config: Config,
    event_bus: Any,
    notifier: Any,
    task_manager: Any,
) -> Any:
    """
    Initialize observability emitter with Supabase.
    
    Returns:
        ObservabilityEmitter or None if not configured
    """
    if not config.supabase_url or not config.supabase_service_key:
        return None
    
    try:
        from supabase import create_async_client
        from observability.emitter import ObservabilityEmitter
        from observability.alerting import AlertRouter

        _sb_client = await create_async_client(
            config.supabase_url,
            config.supabase_service_key,
        )
        _alert_router = AlertRouter(notifier=notifier)
        _alert_router.start()
        _emitter = ObservabilityEmitter(
            supabase_client=_sb_client,
            alert_router=_alert_router,
        )
        _emitter.start(event_bus)
        
        from observability.heartbeat_watchdog import heartbeat_watchdog_loop

        task_manager.create_task(
            heartbeat_watchdog_loop(
                supabase_client=_sb_client,
                emitter=_emitter,
            ),
            name="heartbeat_watchdog"
        )
        logger.info("ObservabilityEmitter started (Supabase: %s)", config.supabase_url)
        return _emitter
    except Exception as exc:
        logger.warning("Observability setup failed (continuing without it): %s", exc)
        return None


async def setup_whatsapp(
    config: Config,
    db: Any,
) -> tuple[Any, list[str]]:
    """
    Initialize WhatsApp client and load sessions.
    
    Returns:
        (wa_client, allowed_numbers) or (None, []) if not configured
    """
    if not config.whatsapp_phone_id or not config.whatsapp_token:
        return None, []
    
    try:
        from whatsapp.client import WhatsAppClient

        wa_client = WhatsAppClient(
            phone_id=config.whatsapp_phone_id,
            token=config.whatsapp_token,
            app_secret=config.whatsapp_app_secret or "",
        )
        await wa_client.load_sessions(db)

        wa_numbers = [
            n.strip()
            for n in (config.whatsapp_allowed_numbers or "").split(",")
            if n.strip()
        ]
        
        logger.info("WhatsApp client initialized")
        return wa_client, wa_numbers
    except Exception as exc:
        logger.warning("WhatsApp setup failed (continuing without it): %s", exc)
        return None, []
