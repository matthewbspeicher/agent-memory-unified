import pytest
from trading.competition.escape_rooms.gauntlet import GauntletEnvironment, SharedSandboxManager

class TestGauntletInitialization:
    def test_gauntlet_sandbox_init(self):
        env = GauntletEnvironment({"num_agents": 4, "puzzle_type": "sql"})
        assert isinstance(env.sandbox, SharedSandboxManager)
        assert len(env.sandbox.locked_resources) == 0
        assert env.state == "ACTIVE"

class TestGauntletSQLPuzzle:
    @pytest.mark.asyncio
    async def test_sql_puzzle_execution(self):
        env = GauntletEnvironment({"puzzle_type": "sql"})
        
        # Test basic query
        res = await env.execute_tool("execute_sql", {"query": "SELECT * FROM _tmp_v42"})
        assert "0xABC" in res
        
        # Test join to find flag
        join_query = "SELECT _sys_x99.auth_token FROM _tmp_v42 JOIN _sys_x99 ON _tmp_v42.user_hash = _sys_x99.hash"
        res = await env.execute_tool("execute_sql", {"query": join_query})
        assert "FLAG{sql_master}" in res

class TestGauntletNetworkPuzzle:
    @pytest.mark.asyncio
    async def test_network_puzzle_query(self):
        env = GauntletEnvironment({"puzzle_type": "network"})
        
        res1 = await env.execute_tool("query_server", {"server_id": "server_A"})
        assert "8080" in res1
        
        res2 = await env.execute_tool("query_server", {"server_id": "server_B"})
        assert "auth_token_xyz" in res2

        res3 = await env.execute_tool("query_server", {"server_id": "mainframe"})
        assert "FLAG{network_ghost}" in res3

class TestGauntletAdversarial:
    @pytest.mark.asyncio
    async def test_lock_resource(self):
        env = GauntletEnvironment()
        res = await env.execute_tool("lock_resource", {"resource_id": "_tmp_v42"})
        
        assert "_tmp_v42" in env.sandbox.locked_resources
        assert env.sandbox.locked_resources["_tmp_v42"] == 2
        assert len(env.sandbox.system_alerts) == 1
        assert "Locked _tmp_v42" in res
        
        # Test tick locks
        env.sandbox.tick_locks()
        assert env.sandbox.locked_resources["_tmp_v42"] == 1
        env.sandbox.tick_locks()
        assert "_tmp_v42" not in env.sandbox.locked_resources

    @pytest.mark.asyncio
    async def test_corrupt_resource_sql(self):
        env = GauntletEnvironment({"puzzle_type": "sql"})
        res = await env.execute_tool("corrupt_resource", {"resource_id": "_sys_x99"})
        
        assert "Corrupted" in res
        assert len(env.sandbox.system_alerts) == 1
        
        # Verify table is dropped
        query_res = await env.execute_tool("execute_sql", {"query": "SELECT * FROM _sys_x99"})
        assert "SQL Error" in query_res

    @pytest.mark.asyncio
    async def test_corrupt_resource_network(self):
        env = GauntletEnvironment({"puzzle_type": "network"})
        res = await env.execute_tool("corrupt_resource", {"resource_id": "server_A"})
        
        assert "Corrupted" in res
        
        # Verify server corrupted
        query_res = await env.execute_tool("query_server", {"server_id": "server_A"})
        assert "CORRUPTED DATA" in query_res

    @pytest.mark.asyncio
    async def test_spoof_event(self):
        env = GauntletEnvironment()
        res = await env.execute_tool("spoof_event", {"message": "Player 2 is disconnected."})
        
        assert "spoofed" in res
        assert "[SPOOF] Player 2 is disconnected." in env.sandbox.system_alerts