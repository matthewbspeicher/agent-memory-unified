from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from config import Config, BrokerConfig
from execution.shadow import ShadowExecutor, ShadowOutcomeResolver
from storage.shadow import ShadowExecutionStore
from utils.background_tasks import BackgroundTaskManager


@pytest.mark.integration
def test_agent_framework_startup_loads_shared_learning_config(tmp_path) -> None:
    agents_path = tmp_path / "agents.empty.yaml"
    agents_path.write_text("agents: []\n")

    import_dir = tmp_path / "imports"
    import_dir.mkdir()

    db_path = tmp_path / "startup-test.db"
    config = Config(
        worker_mode=False,
        api_key="test-key",
        agents_config=str(agents_path),
        import_dir=str(import_dir),
        db_path=str(db_path),
        database_url=None,
        paper_trading=True,
        broker=BrokerConfig(ib_host="")
    )

    app = create_app(enable_agent_framework=True, config=config)

    with TestClient(app) as client:
        assert client.app.state.learning_config is not None
        assert client.app.state.health_engine is not None
        assert client.app.state.confidence_calibration_store is not None


@pytest.mark.integration
def test_agent_framework_startup_wires_shadow_services_into_app_state(
    tmp_path,
) -> None:
    agents_path = tmp_path / "agents.empty.yaml"
    agents_path.write_text("agents: []\n")

    import_dir = tmp_path / "imports"
    import_dir.mkdir()

    db_path = tmp_path / "startup-shadow-test.db"
    config = Config(
        worker_mode=False,
        api_key="test-key",
        agents_config=str(agents_path),
        import_dir=str(import_dir),
        db_path=str(db_path),
        database_url=None,
        paper_trading=True,
        broker=BrokerConfig(ib_host="")
    )

    app = create_app(enable_agent_framework=True, config=config)

    with TestClient(app) as client:
        shadow_store = client.app.state.shadow_execution_store
        shadow_executor = client.app.state.shadow_executor
        shadow_resolver = client.app.state.shadow_outcome_resolver
        task_manager = client.app.state.task_manager

        assert isinstance(shadow_store, ShadowExecutionStore)
        assert isinstance(shadow_executor, ShadowExecutor)
        assert isinstance(shadow_resolver, ShadowOutcomeResolver)
        assert isinstance(task_manager, BackgroundTaskManager)
        # Verify shadow_outcome_resolver task is running
        active_tasks = task_manager.active_tasks
        assert "shadow_outcome_resolver" in active_tasks
        assert not active_tasks["shadow_outcome_resolver"].done()
