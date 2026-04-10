import pytest

from trading.competition.escape_rooms.cybersecurity import CybersecurityEnvironment


class TestCybersecurityInitialization:
    def test_cyber_init_defaults(self):
        env = CybersecurityEnvironment()
        assert env.mode == "duel"
        assert env.red_team_id == 0
        assert env.blue_team_id == 1
        assert "server_A" in env.network_state
        assert "database" in env.network_state
        assert env.network_state["server_A"]["status"] == "online"
        assert env.winner is None
        assert env.soc_logs == []
        assert env.quarantined_ips == []

    def test_cyber_init_red_only(self):
        env = CybersecurityEnvironment({"mode": "red", "num_agents": 1})
        assert env.mode == "red"
        assert env.red_team_id == 0
        assert env.blue_team_id is None

    def test_cyber_init_soc_mode(self):
        env = CybersecurityEnvironment({"mode": "soc"})
        assert env.mode == "soc"


class TestCybersecurityRedTeam:
    @pytest.mark.asyncio
    async def test_scan_ports_known_target(self):
        env = CybersecurityEnvironment()
        res = await env.execute_tool(
            "scan_ports", {"agent_id": 0, "target_id": "server_A"}
        )
        assert "80" in res
        assert "443" in res
        # Scan should emit a SOC log entry
        assert len(env.soc_logs) == 1
        assert env.soc_logs[-1]["event"] == "scan"
        assert env.soc_logs[-1]["target"] == "server_A"

    @pytest.mark.asyncio
    async def test_scan_ports_unknown_target(self):
        env = CybersecurityEnvironment()
        res = await env.execute_tool(
            "scan_ports", {"agent_id": 0, "target_id": "mystery_host"}
        )
        assert "unreachable" in res.lower()

    @pytest.mark.asyncio
    async def test_exploit_service_success_triggers_win(self):
        env = CybersecurityEnvironment()
        res = await env.execute_tool(
            "exploit_service",
            {
                "agent_id": 0,
                "target_id": "database",
                "payload": "sql_injection",
            },
        )
        assert "successful" in res.lower()
        assert env.winner == "RED"
        # CRITICAL match log entry
        assert any("CRITICAL" in entry for entry in env.match_log)
        # Exploit should also emit a SOC log entry
        assert any(log["event"] == "exploit" for log in env.soc_logs)

    @pytest.mark.asyncio
    async def test_exploit_service_wrong_payload_fails(self):
        env = CybersecurityEnvironment()
        res = await env.execute_tool(
            "exploit_service",
            {
                "agent_id": 0,
                "target_id": "server_A",
                "payload": "sql_injection",
            },
        )
        assert "failed" in res.lower()
        assert env.winner is None

    @pytest.mark.asyncio
    async def test_verify_flag_after_red_win(self):
        env = CybersecurityEnvironment()
        await env.execute_tool(
            "exploit_service",
            {
                "agent_id": 0,
                "target_id": "database",
                "payload": "sql_injection",
            },
        )
        assert env.verify_flag("RED") is True
        assert env.verify_flag("BLUE") is False


class TestCybersecurityBlueTeam:
    @pytest.mark.asyncio
    async def test_patch_service_removes_vuln(self):
        env = CybersecurityEnvironment()
        assert "sql_injection" in env.network_state["database"]["vulnerabilities"]
        res = await env.execute_tool(
            "patch_service",
            {
                "agent_id": 1,
                "target_id": "database",
                "fix_payload": "sql_injection",
            },
        )
        assert "patched" in res.lower()
        assert "sql_injection" not in env.network_state["database"]["vulnerabilities"]

    @pytest.mark.asyncio
    async def test_patch_prevents_exploit(self):
        env = CybersecurityEnvironment()
        # Blue patches the database
        await env.execute_tool(
            "patch_service",
            {
                "agent_id": 1,
                "target_id": "database",
                "fix_payload": "sql_injection",
            },
        )
        # Red now attempts exploit; should fail and not win
        res = await env.execute_tool(
            "exploit_service",
            {
                "agent_id": 0,
                "target_id": "database",
                "payload": "sql_injection",
            },
        )
        assert "failed" in res.lower()
        assert env.winner is None

    @pytest.mark.asyncio
    async def test_patch_unknown_vuln_fails(self):
        env = CybersecurityEnvironment()
        res = await env.execute_tool(
            "patch_service",
            {
                "agent_id": 1,
                "target_id": "server_A",
                "fix_payload": "sql_injection",
            },
        )
        assert "failed" in res.lower() or "not found" in res.lower()

    @pytest.mark.asyncio
    async def test_quarantine_ip(self):
        env = CybersecurityEnvironment()
        res = await env.execute_tool(
            "quarantine_ip",
            {"agent_id": 1, "source_ip": "10.0.0.42"},
        )
        assert "10.0.0.42" in res
        assert "10.0.0.42" in env.quarantined_ips
        assert any("quarantined" in entry.lower() for entry in env.match_log)

    @pytest.mark.asyncio
    async def test_inspect_logs_returns_recent(self):
        env = CybersecurityEnvironment()
        # Generate a few log entries via red scans
        await env.execute_tool(
            "scan_ports", {"agent_id": 0, "target_id": "server_A"}
        )
        await env.execute_tool(
            "scan_ports", {"agent_id": 0, "target_id": "database"}
        )
        res = await env.execute_tool("inspect_logs", {"agent_id": 1})
        assert "scan" in res
        assert "server_A" in res or "database" in res


class TestCybersecuritySocLogging:
    def test_generate_soc_log_shape(self):
        env = CybersecurityEnvironment()
        env.generate_soc_log("exploit", "10.0.0.5", "database")
        assert len(env.soc_logs) == 1
        entry = env.soc_logs[0]
        assert entry["event"] == "exploit"
        assert entry["source_ip"] == "10.0.0.5"
        assert entry["target"] == "database"
        assert "timestamp" in entry


class TestCybersecurityMisc:
    @pytest.mark.asyncio
    async def test_unknown_tool_returns_not_recognized(self):
        env = CybersecurityEnvironment()
        res = await env.execute_tool("launch_nukes", {"agent_id": 0})
        assert "not recognized" in res.lower()

    def test_get_state_starts_active(self):
        env = CybersecurityEnvironment()
        assert env.get_state() == "ACTIVE"

    @pytest.mark.asyncio
    async def test_get_state_transitions_on_red_win(self):
        env = CybersecurityEnvironment()
        await env.execute_tool(
            "exploit_service",
            {
                "agent_id": 0,
                "target_id": "database",
                "payload": "sql_injection",
            },
        )
        assert env.get_state() == "RED_WIN"
        assert env.winner == "RED"


class TestCybersecurityQuarantineEnforcement:
    @pytest.mark.asyncio
    async def test_quarantine_blocks_red_scan(self):
        env = CybersecurityEnvironment()
        await env.execute_tool(
            "quarantine_ip",
            {"agent_id": 1, "source_ip": "10.0.0.42"},
        )
        # Red Team attempts a scan from the quarantined IP
        res = await env.execute_tool(
            "scan_ports",
            {"agent_id": 0, "source_ip": "10.0.0.42", "target_id": "server_A"},
        )
        assert "quarantined" in res.lower()

    @pytest.mark.asyncio
    async def test_quarantine_blocks_red_exploit(self):
        env = CybersecurityEnvironment()
        await env.execute_tool(
            "quarantine_ip",
            {"agent_id": 1, "source_ip": "10.0.0.42"},
        )
        res = await env.execute_tool(
            "exploit_service",
            {
                "agent_id": 0,
                "source_ip": "10.0.0.42",
                "target_id": "database",
                "payload": "sql_injection",
            },
        )
        assert "quarantined" in res.lower()
        # Winner must NOT be set because the exploit was blocked
        assert env.winner is None
        assert env.get_state() == "ACTIVE"

    @pytest.mark.asyncio
    async def test_quarantine_does_not_block_other_red_ips(self):
        env = CybersecurityEnvironment()
        await env.execute_tool(
            "quarantine_ip",
            {"agent_id": 1, "source_ip": "10.0.0.42"},
        )
        # Red Team pivots to a different IP
        res = await env.execute_tool(
            "scan_ports",
            {"agent_id": 0, "source_ip": "10.0.0.99", "target_id": "server_A"},
        )
        assert "quarantined" not in res.lower()
        assert "80" in res


class TestCybersecurityCrossRoleAbuse:
    @pytest.mark.asyncio
    async def test_blue_cannot_call_red_scan(self):
        env = CybersecurityEnvironment()
        # Blue Team agent_id=1 tries to call a Red Team tool
        res = await env.execute_tool(
            "scan_ports", {"agent_id": 1, "target_id": "server_A"}
        )
        assert "not recognized" in res.lower()

    @pytest.mark.asyncio
    async def test_red_cannot_call_blue_patch(self):
        env = CybersecurityEnvironment()
        res = await env.execute_tool(
            "patch_service",
            {
                "agent_id": 0,
                "target_id": "database",
                "fix_payload": "sql_injection",
            },
        )
        assert "not recognized" in res.lower()
        # Vulnerability must still exist
        assert "sql_injection" in env.network_state["database"]["vulnerabilities"]
