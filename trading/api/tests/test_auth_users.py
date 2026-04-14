import pytest
from fastapi.testclient import TestClient
from api.app import create_app
from config import load_config
import bcrypt
import jwt
from datetime import datetime, timedelta, timezone

class MockIdentityStore:
    def __init__(self):
        self.users = {}
        
    async def get_user_by_email(self, email: str):
        return self.users.get(email)
        
    async def create_user(self, email: str, password: str):
        from trading.models.user import User, PlatformTier
        import uuid
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            hashed_password=hashed,
            tier=PlatformTier.EXPLORER
        )
        self.users[email] = user
        return user

@pytest.fixture
def mock_store():
    return MockIdentityStore()

@pytest.fixture
def client(mock_store):
    config = load_config()
    app = create_app(enable_agent_framework=True, config=config)
    
    from api.auth.users import get_identity_store
    app.dependency_overrides[get_identity_store] = lambda: mock_store
    
    return TestClient(app)

def test_signup_and_login(client):
    # Signup
    email = "test@example.com"
    password = "password123"
    response = client.post("/api/v1/auth/signup", json={"email": email, "password": password})
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == email
    assert "hashed_password" in data
    
    # Login
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    
    # Verify JWT
    token = data["access_token"]
    config = load_config()
    secret_key = config.api_key or "secret"
    payload = jwt.decode(token, secret_key, algorithms=["HS256"])
    assert payload["sub"] == email

def test_login_invalid_credentials(client):
    email = "test2@example.com"
    password = "password123"
    # Signup first
    client.post("/api/v1/auth/signup", json={"email": email, "password": password})
    
    # Login with wrong password
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "wrongpassword"})
    assert response.status_code == 401
    
    # Login with non-existent email
    response = client.post("/api/v1/auth/login", json={"email": "nonexistent@example.com", "password": password})
    assert response.status_code == 401
