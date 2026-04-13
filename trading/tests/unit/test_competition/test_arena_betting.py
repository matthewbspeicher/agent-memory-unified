import pytest
import uuid
import json
from datetime import datetime
from competition.store import CompetitionStore

class MockCursor:
    def __init__(self, rows):
        self.rows = rows
        self.index = 0
    async def fetchone(self):
        if self.index < len(self.rows):
            row = self.rows[self.index]
            self.index += 1
            return row
        return None
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass

class MockDB:
    def __init__(self, rows=None):
        self.calls = []
        self.rows = rows or []
    async def fetch(self, sql, *params):
        self.calls.append((sql, list(params)))
        return self.rows
    async def fetchrow(self, sql, *params):
        self.calls.append((sql, list(params)))
        return self.rows[0] if self.rows else None
    async def execute(self, sql, *params):
        self.calls.append((sql, list(params)))
        return "INSERT 0 1"

@pytest.fixture
def competition_store():
    # We use a MockDB that records calls and returns controlled data
    # This avoids the aiosqlite / asyncpg placeholder mismatch issue
    return CompetitionStore(MockDB())

@pytest.mark.asyncio
async def test_arena_betting_odds_calculation(competition_store):
    # Setup mock responses for the store's internal queries
    db = competition_store._db
    
    # 1. Mock get_arena_session response
    session_id = str(uuid.uuid4())
    db.rows = [{
        "id": session_id,
        "challenge_id": "challenge-1",
        "agent_id": "agent-1",
        "status": "in_progress",
        "total_pool": 4000,
        "a_pool": 2000,
        "b_pool": 2000,
        "a_bettors": 2,
        "b_bettors": 1
    }]
    
    # 2. Verify pool and odds
    # Since get_arena_betting_pool is what we want to test, we need to ensure 
    # the SQL it generates matches our expectations and it parses the DB result correctly.
    
    pool = await competition_store.get_arena_betting_pool(session_id)
    
    assert pool["total_pool"] == 4000
    assert pool["player_a_pool"] == 2000
    assert pool["player_b_pool"] == 2000
    assert pool["player_a_odds"] == 0.5
    assert pool["player_b_odds"] == 0.5
    
    # Verify the SQL call
    sql, params = db.calls[0]
    assert "SELECT" in sql
    assert "FROM match_bets" in sql
    assert params == [session_id]

@pytest.mark.asyncio
async def test_arena_betting_place_bet_validation(competition_store):
    db = competition_store._db
    session_id = str(uuid.uuid4())
    
    # Mock session not found
    db.rows = []
    with pytest.raises(ValueError, match="Session not found"):
        await competition_store.place_arena_bet(session_id, "user-1", "player_a", 100)
    
    # Mock session found but invalid player
    db.rows = [{"id": session_id, "challenge_id": "c1", "agent_id": "a1"}]
    with pytest.raises(ValueError, match="Predicted winner must be one of"):
        await competition_store.place_arena_bet(session_id, "user-1", "invalid_player", 100)
