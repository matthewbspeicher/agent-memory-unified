from typing import Any, Dict, List
import sqlite3
from .base import EscapeRoomEnvironment

class SharedSandboxManager:
    """Manages the global state and adversarial locks for a shared escape room."""
    def __init__(self):
        self.global_state: Dict[str, Any] = {}
        self.locked_resources: Dict[str, int] = {} # resource_id: rounds_remaining
        self.system_alerts: List[str] = []

    def lock(self, resource_id: str, duration: int):
        self.locked_resources[resource_id] = duration
        
    def tick_locks(self):
        expired = []
        for res in self.locked_resources:
            self.locked_resources[res] -= 1
            if self.locked_resources[res] <= 0:
                expired.append(res)
        for res in expired:
            del self.locked_resources[res]

class SQLPuzzle:
    def __init__(self):
        self.conn = sqlite3.connect(':memory:')
        self._seed_data()
        
    def _seed_data(self):
        cur = self.conn.cursor()
        cur.execute("CREATE TABLE _tmp_v42 (id INT, user_hash TEXT)")
        cur.execute("CREATE TABLE _sys_x99 (hash TEXT, auth_token TEXT)")
        cur.execute("INSERT INTO _tmp_v42 VALUES (1, '0xABC')")
        cur.execute("INSERT INTO _sys_x99 VALUES ('0xABC', 'FLAG{sql_master}')")
        self.conn.commit()

    def execute_query(self, query: str) -> str:
        try:
            cur = self.conn.cursor()
            cur.execute(query)
            return str(cur.fetchall())
        except Exception as e:
            return f"SQL Error: {str(e)}"

class NetworkPuzzle:
    def __init__(self):
        self.servers = {
            "server_A": {"ticket": "Use port 8080 on server_B"},
            "server_B": {"8080": "auth_token_xyz"},
            "mainframe": {"token_xyz": "FLAG{network_ghost}"}
        }
    
    def query_server(self, server_id: str) -> str:
        return str(self.servers.get(server_id, "Host unreachable"))

class BugFixPuzzle:
    def __init__(self):
        self.code = "def calculate_total(prices):\n    total = 0\n    for p in prices:\n        total -= p\n    return total\n"
        
    def patch_code(self, new_code: str) -> str:
        self.code = new_code
        return "Code updated."
        
    def run_tests(self) -> str:
        try:
            # We mock the test execution for safety
            local_vars = {}
            exec(self.code, {}, local_vars)
            func = local_vars.get("calculate_total")
            
            if not func:
                return "FAIL: Function calculate_total not found."
                
            res = func([10, 20, 30])
            if res == 60:
                return "PASS: All tests passing! FLAG{bug_squasher}"
            else:
                return f"FAIL: Expected 60, got {res}."
        except Exception as e:
            return f"FAIL: Execution error - {str(e)}"

class GauntletEnvironment(EscapeRoomEnvironment):
    """
    Multi-agent Adversarial Escape Room testing complex tool chaining and resilience.
    """
    def __init__(self, config: dict[str, Any] = None):
        super().__init__()
        if config is None: 
            config = {}
        self.num_agents = config.get("num_agents", 1)
        self.puzzle_type = config.get("puzzle_type", "sql")
        self.state = "ACTIVE"
        self.sandbox = SharedSandboxManager()
        self.winner = None
        
        if self.puzzle_type == "sql":
            self.puzzle = SQLPuzzle()
        elif self.puzzle_type == "network":
            self.puzzle = NetworkPuzzle()
        elif self.puzzle_type == "bugfix":
            self.puzzle = BugFixPuzzle()

    async def execute_tool(self, tool_name: str, kwargs: Dict[str, Any]) -> str:
        """
        Processes standard, adversarial, and puzzle-specific tools.
        """
        agent_id = kwargs.get("agent_id", 0)
        
        # Adversarial Tools (Sabotage)
        if tool_name == "lock_resource":
            target = kwargs.get("resource_id")
            if not target:
                return "Error: resource_id required."
            self.sandbox.lock(target, 2)
            self.sandbox.system_alerts.append(f"Resource {target} locked by unknown.")
            return f"Locked {target} for 2 rounds."
            
        if tool_name == "corrupt_resource":
            target = kwargs.get("resource_id")
            if not target:
                return "Error: resource_id required."
            
            # Simple corruption logic
            if self.puzzle_type == "network" and isinstance(self.puzzle, NetworkPuzzle):
                if target in self.puzzle.servers:
                    self.puzzle.servers[target] = {"error": "CORRUPTED DATA"}
            elif self.puzzle_type == "sql" and isinstance(self.puzzle, SQLPuzzle):
                try:
                    # Fix SQL Injection: Only allow dropping known tables
                    allowed_tables = ["_tmp_v42", "_sys_x99"]
                    if target in allowed_tables:
                        cur = self.puzzle.conn.cursor()
                        cur.execute(f"DROP TABLE IF EXISTS {target}")
                        self.puzzle.conn.commit()
                except sqlite3.Error:
                    pass
                    
            self.sandbox.system_alerts.append(f"Resource {target} corrupted by unknown.")
            return f"Corrupted resource {target}."
            
        if tool_name == "spoof_event":
            msg = kwargs.get("message", "")
            self.sandbox.system_alerts.append(f"[SPOOF] {msg}")
            return "Event spoofed."
            
        # Puzzle-specific Tools
        if self.puzzle_type == "sql" and tool_name == "execute_sql":
            query = kwargs.get("query", "")
            return self.puzzle.execute_query(query)
            
        if self.puzzle_type == "network" and tool_name == "query_server":
            server_id = kwargs.get("server_id", "")
            return self.puzzle.query_server(server_id)
            
        if self.puzzle_type == "bugfix":
            if tool_name == "patch_code":
                new_code = kwargs.get("new_code", "")
                return self.puzzle.patch_code(new_code)
            if tool_name == "run_tests":
                return self.puzzle.run_tests()

        return f"Action not recognized: {tool_name}"

    def get_state(self) -> str:
        return self.state

    def verify_flag(self, flag: str) -> bool:
        if self.winner is None:
            return False
        return flag == self.winner
