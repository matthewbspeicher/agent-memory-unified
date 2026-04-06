import os

# Prevent libomp fatal abort when hnswlib and torch (via sentence-transformers)
# both link duplicate OpenMP runtimes — standard macOS/Homebrew workaround.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from broker.models import BrokerCapabilities


@pytest.fixture
def mock_broker():
    broker = MagicMock()
    broker.connection.is_connected.return_value = True
    broker.connection.connect = AsyncMock()
    broker.connection.disconnect = AsyncMock()
    broker.connection._reconnecting = False
    broker.capabilities.return_value = BrokerCapabilities(
        stocks=True,
        options=True,
        futures=True,
        forex=True,
        bonds=True,
        streaming=True,
    )
    return broker


@pytest.fixture
def client(mock_broker):
    os.environ["STA_API_KEY"] = "test-key"
    from api.app import create_app
    from api.deps import _init_state

    app = create_app(mock_broker)
    _init_state(app.state)
    return TestClient(app)
