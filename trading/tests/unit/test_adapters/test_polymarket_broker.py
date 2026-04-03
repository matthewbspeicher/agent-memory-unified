import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal

from adapters.polymarket.client import PolymarketClient
from adapters.polymarket.data_source import PolymarketDataSource
from adapters.polymarket.broker import PolymarketBroker
from broker.models import LimitOrder, MarketOrder, Symbol, AssetType, OrderSide, OrderStatus
from py_clob_client.client import ClobClient, ApiCreds

@pytest.fixture
def mock_clob():
    with patch("adapters.polymarket.client.ClobClient") as MockClob:
        mock_instance = MockClob.return_value
        # For health check
        mock_instance.get_server_time.return_value = "12345"
        # For L2 creds derivation
        mock_instance.create_or_derive_api_creds.return_value = ApiCreds("key", "secret", "pass")
        mock_instance.fetch_creds.return_value = ApiCreds("key", "secret", "pass")
        yield mock_instance

@pytest.fixture
def mock_w3():
    with patch("adapters.polymarket.client.Web3") as MockW3:
        w3_instance = MockW3.return_value
        usdc_mock = MagicMock()
        ct_mock = MagicMock()
        
        usdc_mock.functions.balanceOf.return_value.call.return_value = 1500000
        usdc_mock.functions.allowance.return_value.call.return_value = 0
        ct_mock.functions.isApprovedForAll.return_value.call.return_value = False
        
        # We replace the eth.contract to return usdc_mock then ct_mock as needed
        # In client.py usdc is initialized on init. ct_mock is in setup_approvals.
        w3_instance.eth.contract.side_effect = lambda address, abi: usdc_mock if "balanceOf" in str(abi) else ct_mock
        yield w3_instance, usdc_mock, ct_mock

@pytest.fixture
def poly_broker(mock_clob, mock_w3, tmp_path):
    creds_file = tmp_path / "creds.json"
    client = PolymarketClient(private_key="0x" + "1"*64, rpc_url="http://fake")
    ds = PolymarketDataSource(client)
    broker = PolymarketBroker(client, ds, creds_path=str(creds_file), dry_run=False)
    return broker

@pytest.mark.asyncio
async def test_auth_flow_and_idempotent_approval(poly_broker, mock_clob, mock_w3, tmp_path):
    w3_instance, usdc_mock, ct_mock = mock_w3
    
    # First connect
    await poly_broker.connection.connect()
    
    assert mock_clob.create_or_derive_api_creds.called
    assert usdc_mock.functions.approve.called
    assert ct_mock.functions.setApprovalForAll.called
    
    # Verify file written
    creds_path = tmp_path / "creds.json"
    assert creds_path.exists()

    # Reset mocks for second call to simulate idempotency
    mock_clob.create_or_derive_api_creds.reset_mock()
    usdc_mock.functions.approve.reset_mock()
    ct_mock.functions.setApprovalForAll.reset_mock()
    
    # Fake that allowance exists
    usdc_mock.functions.allowance.return_value.call.return_value = 1000000 
    ct_mock.functions.isApprovedForAll.return_value.call.return_value = True

    # Recreate broker to load from file
    client2 = PolymarketClient(private_key="0x" + "1"*64, rpc_url="http://fake")
    client2._w3 = w3_instance
    client2._usdc = usdc_mock
    broker2 = PolymarketBroker(client2, PolymarketDataSource(client2), str(creds_path), dry_run=False)
    
    await broker2.connection.connect()
    
    # Should not re-derive creds
    assert not mock_clob.create_or_derive_api_creds.called
    # Should not re-approve
    assert not usdc_mock.functions.approve.called
    assert not ct_mock.functions.setApprovalForAll.called

@pytest.mark.asyncio
async def test_usdc_decimal_balance(poly_broker, mock_clob):
    # Mock clob balance endpoint failure to trigger on-chain fallback
    mock_clob.session.get.side_effect = Exception("HTTP 500")
    
    bal = await poly_broker.account.get_balances()
    assert bal.cash == Decimal("1.50") # 1500000 / 10**6
    assert bal.buying_power == Decimal("1.50")

@pytest.mark.asyncio
async def test_order_building_and_dry_run(poly_broker):
    sym = Symbol("0xABC", AssetType.PREDICTION)
    poly_broker.orders.ds._token_id_cache["0xABC"] = ("0xYES", "0xNO")

    order = LimitOrder(symbol=sym, side=OrderSide.BUY, quantity=Decimal("10"), account_id="POLY", limit_price=Decimal("0.65"))
    
    result = await poly_broker.orders.place_order(order.account_id, order)
    # mock_clob.create_order returns empty by default, so it fails gracefully or we mock it.
    
    poly_broker.orders.dry_run = True
    dry_result = await poly_broker.orders.place_order(order.account_id, order)
    assert dry_result.order_id.startswith("dry-run")
    assert dry_result.status == OrderStatus.SUBMITTED

@pytest.mark.asyncio
async def test_market_order_rejected(poly_broker):
    order = MarketOrder(symbol=Symbol("0xABC"), side=OrderSide.BUY, quantity=Decimal("10"), account_id="POLY")
    with pytest.raises(ValueError, match="does not support MarketOrders"):
        await poly_broker.orders.place_order(order.account_id, order)

@pytest.mark.asyncio
async def test_capabilities(poly_broker):
    caps = poly_broker.capabilities()
    assert caps.prediction_markets is True
    assert caps.stocks is False
