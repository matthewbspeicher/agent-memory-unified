import re
import sqlite3
from typing import Any, Dict, List

from .base import EscapeRoomEnvironment

# SQLite authorizer action codes (not exposed as module attributes; see
# https://www.sqlite.org/c3ref/c_alter_table.html).
_SQLITE_DENY = 1
_SQLITE_OK = 0
_SQLITE_ATTACH = 24
_SQLITE_DETACH = 25
_SQLITE_PRAGMA = 19
_SQLITE_FUNCTION = 31

# Dangerous function names that can escape the sandbox even without ATTACH.
_BLOCKED_SQL_FUNCTIONS = frozenset(
    {"load_extension", "readfile", "writefile", "edit", "fts3_tokenizer"}
)


def _sql_authorizer(action: int, arg1: Any, arg2: Any, _db: Any, _trigger: Any) -> int:
    """Deny ATTACH/DETACH/PRAGMA and dangerous functions on the in-memory DB."""
    if action in (_SQLITE_ATTACH, _SQLITE_DETACH, _SQLITE_PRAGMA):
        return _SQLITE_DENY
    if action == _SQLITE_FUNCTION and isinstance(arg2, str):
        if arg2.lower() in _BLOCKED_SQL_FUNCTIONS:
            return _SQLITE_DENY
    return _SQLITE_OK


# Identifier whitelist for any code path that interpolates a table/column
# name into a SQL statement (parameterized binds cannot bind identifiers).
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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

    def is_locked(self, resource_id: str) -> bool:
        return resource_id in self.locked_resources

class SQLPuzzle:
    def __init__(self):
        self.conn = sqlite3.connect(':memory:')
        # Seed data first (authorizer would deny CREATE TABLE without extra rules),
        # then install the authorizer to lock down user-supplied queries.
        self._seed_data()
        self.conn.set_authorizer(_sql_authorizer)

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
        except sqlite3.Error as e:
            return f"SQL Error: {e}"

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
    _KNOWN_PUZZLE_TYPES = frozenset({"sql", "network", "bugfix"})

    def __init__(self, config: dict[str, Any] = None):
        super().__init__()
        if config is None:
            config = {}
        self.num_agents = config.get("num_agents", 1)
        self.puzzle_type = config.get("puzzle_type", "sql")
        if self.puzzle_type not in self._KNOWN_PUZZLE_TYPES:
            raise ValueError(
                f"Unknown puzzle_type: {self.puzzle_type!r}. "
                f"Expected one of {sorted(self._KNOWN_PUZZLE_TYPES)}."
            )
        self.state = "ACTIVE"
        self.sandbox = SharedSandboxManager()
        self.winner: str | None = None

        if self.puzzle_type == "sql":
            self.puzzle = SQLPuzzle()
        elif self.puzzle_type == "network":
            self.puzzle = NetworkPuzzle()
        else:  # bugfix
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
            if not _IDENT_RE.match(str(target)):
                return f"Error: invalid resource identifier {target!r}."

            # Simple corruption logic
            if self.puzzle_type == "network" and isinstance(self.puzzle, NetworkPuzzle):
                if target in self.puzzle.servers:
                    self.puzzle.servers[target] = {"error": "CORRUPTED DATA"}
            elif self.puzzle_type == "sql" and isinstance(self.puzzle, SQLPuzzle):
                # Only allow dropping known tables; log (don't swallow) errors.
                allowed_tables = {"_tmp_v42", "_sys_x99"}
                if target in allowed_tables:
                    try:
                        cur = self.puzzle.conn.cursor()
                        cur.execute(f"DROP TABLE IF EXISTS {target}")
                        self.puzzle.conn.commit()
                    except sqlite3.Error as e:
                        self.sandbox.system_alerts.append(
                            f"Corruption of {target} failed: {e}"
                        )

            self.sandbox.system_alerts.append(f"Resource {target} corrupted by unknown.")
            return f"Corrupted resource {target}."
            
        if tool_name == "spoof_event":
            msg = kwargs.get("message", "")
            self.sandbox.system_alerts.append(f"[SPOOF] {msg}")
            return "Event spoofed."
            
        # Puzzle-specific Tools
        if self.puzzle_type == "sql" and tool_name == "execute_sql":
            assert isinstance(self.puzzle, SQLPuzzle)
            query = kwargs.get("query", "")
            # Block queries that reference any locked resource by name.
            for locked in self.sandbox.locked_resources:
                if locked in query:
                    return f"Error: resource {locked} is locked."
            result = self.puzzle.execute_query(query)
            if "FLAG{sql_master}" in result and self.winner is None:
                self.winner = f"AGENT_{agent_id}"
                self.state = "COMPLETE"
                self.sandbox.system_alerts.append(
                    f"FLAG{{sql_master}} captured by agent {agent_id}."
                )
            return result

        if self.puzzle_type == "network" and tool_name == "query_server":
            assert isinstance(self.puzzle, NetworkPuzzle)
            server_id = kwargs.get("server_id", "")
            if self.sandbox.is_locked(server_id):
                return f"Error: resource {server_id} is locked."
            result = self.puzzle.query_server(server_id)
            if "FLAG{network_ghost}" in result and self.winner is None:
                self.winner = f"AGENT_{agent_id}"
                self.state = "COMPLETE"
                self.sandbox.system_alerts.append(
                    f"FLAG{{network_ghost}} captured by agent {agent_id}."
                )
            return result

        if self.puzzle_type == "bugfix":
            assert isinstance(self.puzzle, BugFixPuzzle)
            if tool_name == "patch_code":
                new_code = kwargs.get("new_code", "")
                return self.puzzle.patch_code(new_code)
            if tool_name == "run_tests":
                result = self.puzzle.run_tests()
                if "FLAG{bug_squasher}" in result and self.winner is None:
                    self.winner = f"AGENT_{agent_id}"
                    self.state = "COMPLETE"
                return result

        return f"Action not recognized: {tool_name}"

    def get_state(self) -> str:
        return self.state

    def verify_flag(self, flag: str) -> bool:
        if self.winner is None:
            return False
        return flag == self.winner
