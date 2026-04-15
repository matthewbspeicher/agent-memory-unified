import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from models.user import PlatformTier, User
from uuid import uuid4
from datetime import datetime

# We need to mock the dependencies before importing the app
from api.auth.users import get_identity_store
from api.app import create_app

@pytest.fixture
def mock_store():
    store = AsyncMock()
    
    # Mock get_user_by_email
    mock_user = User(
        id=uuid4(),
        email="test@example.com",
        hashed_password="hashed",
        tier=PlatformTier.EXPLORER,
        stripe_customer_id="cus_123",
        stripe_subscription_id="sub_123",
        created_at=datetime.now()
    )
    store.get_user_by_email.return_value = mock_user
    
    # Mock update_user_tier
    store.update_user_tier.return_value = None
    
    return store

@pytest.fixture
def client(mock_store):
    app = create_app()
    app.dependency_overrides[get_identity_store] = lambda: mock_store
    return TestClient(app)

def test_stripe_webhook_checkout_session_completed(client, mock_store):
    payload = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer_details": {
                    "email": "test@example.com"
                }
            }
        }
    }
    
    response = client.post(
        "/stripe/webhooks",
        json=payload,
        headers={"Stripe-Signature": "test_sig"}
    )
    
    assert response.status_code == 200
    assert response.json() == {"status": "success"}
    
    mock_store.get_user_by_email.assert_called_once_with("test@example.com")
    mock_store.update_user_tier.assert_called_once()
    
    # Check that update_user_tier was called with the correct tier
    args, _ = mock_store.update_user_tier.call_args
    assert args[1] == PlatformTier.TRADER

def test_stripe_webhook_subscription_deleted(client, mock_store):
    payload = {
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "customer_details": {
                    "email": "test@example.com"
                }
            }
        }
    }
    
    response = client.post(
        "/stripe/webhooks",
        json=payload,
        headers={"Stripe-Signature": "test_sig"}
    )
    
    assert response.status_code == 200
    assert response.json() == {"status": "success"}
    
    # We haven't implemented the downgrade logic yet, so it shouldn't call update_user_tier
    mock_store.update_user_tier.assert_not_called()
