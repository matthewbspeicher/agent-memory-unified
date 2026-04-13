# Cybersecurity CTF Arena Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. 

**Goal:** Implement the `cybersecurity.py` environment to test Red/Blue Team autonomous execution and SOC log parsing.

**Architecture:** Environment inherits from `EscapeRoomEnvironment`. It maintains a shared Server state, a Red/Blue ID mapping, and an asynchronous Log Stream for SOC mode.

**Tech Stack:** Python 3.14, Pydantic, JSON logs.

---

### Task 1: Cyber-Arena Operational Modes & Red Team Tools

**Files:**
- Create: `trading/competition/escape_rooms/cybersecurity.py`
- Modify: `trading/competition/escape_rooms/factory.py`
- Test: `trading/shared/tests/test_cybersecurity_engine.py`

- [x] **Step 1: Write the failing test for the environment**

```python
from trading.competition.escape_rooms.cybersecurity import CybersecurityEnvironment

def test_cyber_init():
    env = CybersecurityEnvironment(mode="duel")
    assert env.mode == "duel"
    assert env.red_team_id == 0
    assert env.blue_team_id == 1
    assert "server_A" in env.network_state
```

- [x] **Step 2: Implement the Base `CybersecurityEnvironment`**

```python
from typing import Any, Dict, List
from .base import EscapeRoomEnvironment

class CybersecurityEnvironment(EscapeRoomEnvironment):
    def __init__(self, config: dict[str, Any] = None):
        super().__init__()
        if config is None: config = {}
        self.mode = config.get("mode", "duel") # red, duel, soc
        self.num_agents = config.get("num_agents", 2)
        
        self.red_team_id = 0
        self.blue_team_id = 1 if self.num_agents > 1 else None
        
        self.network_state = {
            "server_A": {"open_ports": [80, 443], "vulnerabilities": ["path_traversal"], "status": "online"},
            "database": {"open_ports": [5432], "vulnerabilities": ["sql_injection"], "status": "online"}
        }
        self.match_log = []
        self.winner = None
        self.quarantined_ips = []
        self.soc_logs = []

    async def execute_tool(self, tool_name: str, kwargs: Dict[str, Any]) -> str:
        agent_id = kwargs.get("agent_id", 0)
        
        # Red Team Tools
        if agent_id == self.red_team_id:
            if tool_name == "scan_ports":
                target = kwargs.get("target_id")
                if target in self.network_state:
                    return f"Open ports: {self.network_state[target]['open_ports']}"
                return "Host unreachable."
            if tool_name == "exploit_service":
                target = kwargs.get("target_id")
                payload = kwargs.get("payload")
                if target in self.network_state and payload in self.network_state[target]["vulnerabilities"]:
                    self.match_log.append(f"CRITICAL: Red Team exploited {target} using {payload}")
                    if target == "database":
                        self.winner = "RED"
                    return f"Exploit successful. Gained access to {target}."
                return "Exploit failed."
                
        return f"Action not recognized: {tool_name}"
        
    def get_state(self) -> str:
        return "ACTIVE"
        
    def verify_flag(self, flag: str) -> bool:
        if self.winner is None: return False
        return flag == self.winner
```

- [x] **Step 3: Register in Factory**
Register `cybersecurity` in `_ROOM_TYPES` in `factory.py`.

- [x] **Step 4: Run Tests and Commit**
Run `pytest trading/shared/tests/test_cybersecurity_engine.py` and commit.

---

### Task 2: Blue Team & SOC Tools

**Files:**
- Modify: `trading/competition/escape_rooms/cybersecurity.py`

- [x] **Step 1: Implement `patch_service`, `quarantine_ip`, `inspect_logs`**

```python
# In execute_tool for CybersecurityEnvironment
        # Blue Team Tools
        if agent_id == self.blue_team_id:
            if tool_name == "patch_service":
                target = kwargs.get("target_id")
                fix = kwargs.get("fix_payload")
                if target in self.network_state and fix in self.network_state[target]["vulnerabilities"]:
                    self.network_state[target]["vulnerabilities"].remove(fix)
                    self.match_log.append(f"Blue Team patched {fix} on {target}.")
                    return f"Patched {target} successfully."
                return "Patch failed or vulnerability not found."
            if tool_name == "quarantine_ip":
                ip = kwargs.get("source_ip")
                self.quarantined_ips.append(ip)
                self.match_log.append(f"Blue Team quarantined IP {ip}.")
                return f"IP {ip} added to firewall."
            if tool_name == "inspect_logs":
                return str(self.soc_logs[-5:]) # Return last 5 logs
```

- [x] **Step 2: Add SOC log generator**
```python
    def generate_soc_log(self, event_type: str, source_ip: str, target: str):
        import time
        self.soc_logs.append({
            "timestamp": time.time(),
            "event": event_type,
            "source_ip": source_ip,
            "target": target
        })
```
Call this inside `scan_ports` and `exploit_service`.

- [x] **Step 3: Add tests and Commit**
Add `test_blue_team_defense` and commit.
