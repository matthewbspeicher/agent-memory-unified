from unittest.mock import AsyncMock
from types import SimpleNamespace

from execution.service import ExecutionRejected, ExecutionUnavailable

HEADERS = {"X-API-Key": "test-key"}
PATH = "/risk/execution/recovery"


def test_recovery_is_authenticated_and_inspectable(client):
    service = SimpleNamespace(
        reconciliation_status=AsyncMock(return_value={"lock": "dispatch"}),
        recover=AsyncMock(return_value={"status": "recovered"}),
    )
    client.app.state.execution_service = service
    assert client.get(PATH).status_code in (401, 403)
    assert client.post(PATH, json={"token": "dispatch"}).status_code in (401, 403)
    assert client.get(PATH, headers=HEADERS).json() == {"lock": "dispatch"}
    response = client.post(PATH, headers=HEADERS, json={"token": "dispatch"})
    assert response.status_code == 200
    service.recover.assert_awaited_once_with("dispatch")


def test_recovery_errors_do_not_claim_success(client):
    service = SimpleNamespace(
        recover=AsyncMock(side_effect=ExecutionRejected("Trading is not halted"))
    )
    client.app.state.execution_service = service
    assert (
        client.post(PATH, headers=HEADERS, json={"token": "dispatch"}).status_code
        == 409
    )
    service.recover.side_effect = ExecutionUnavailable("Evidence unavailable")
    assert (
        client.post(PATH, headers=HEADERS, json={"token": "dispatch"}).status_code
        == 503
    )
    service.recover.side_effect = TimeoutError("Redis reply lost")
    response = client.post(PATH, headers=HEADERS, json={"token": "dispatch"})
    assert response.status_code == 503
    assert "inspect recovery status" in response.json()["detail"]


def test_recovery_requires_both_control_and_order_scopes(client):
    from api.identity.dependencies import Identity, resolve_identity

    service = SimpleNamespace(
        reconciliation_status=AsyncMock(return_value={}),
        recover=AsyncMock(return_value={"status": "recovered"}),
    )
    client.app.state.execution_service = service
    for scopes in [frozenset(), frozenset({"risk:halt"}), frozenset({"write:orders"})]:

        async def identity():
            return Identity(name="limited", scopes=scopes, tier="agent")

        client.app.dependency_overrides[resolve_identity] = identity
        assert client.get(PATH, headers=HEADERS).status_code == 403
        assert (
            client.post(PATH, headers=HEADERS, json={"token": "dispatch"}).status_code
            == 403
        )
    service.recover.assert_not_awaited()
    service.reconciliation_status.assert_not_awaited()
