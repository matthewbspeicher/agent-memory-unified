"""Cybersecurity CTF arena environment.

Supports three operational modes:

* ``red``  — single Red Team agent drills for offensive exploits
* ``duel`` — Red vs. Blue adversarial match (default)
* ``soc``  — Blue Team SOC triage mode reading streamed JSON logs

The environment maintains a shared ``network_state`` (open ports and
vulnerabilities per host) plus an append-only ``soc_logs`` stream that
Red Team tool invocations feed into for Blue Team consumption.
"""

from __future__ import annotations

import time
from typing import Any, Dict

from .base import EscapeRoomEnvironment


class CybersecurityEnvironment(EscapeRoomEnvironment):
    """Red/Blue team CTF environment with SOC log streaming."""

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__()
        if config is None:
            config = {}

        self.mode: str = config.get("mode", "duel")  # red | duel | soc
        self.num_agents: int = config.get("num_agents", 2)

        self.red_team_id: int = 0
        self.blue_team_id: int | None = 1 if self.num_agents > 1 else None

        self.network_state: Dict[str, Dict[str, Any]] = {
            "server_A": {
                "open_ports": [80, 443],
                "vulnerabilities": ["path_traversal"],
                "status": "online",
            },
            "database": {
                "open_ports": [5432],
                "vulnerabilities": ["sql_injection"],
                "status": "online",
            },
        }

        self.match_log: list[str] = []
        self.soc_logs: list[dict[str, Any]] = []
        self.quarantined_ips: list[str] = []
        self.winner: str | None = None
        self.state: str = "ACTIVE"

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------
    async def execute_tool(self, tool_name: str, kwargs: Dict[str, Any]) -> str:
        agent_id = kwargs.get("agent_id", 0)
        source_ip = kwargs.get("source_ip", "10.0.0.1")

        # Red Team Tools ------------------------------------------------
        if agent_id == self.red_team_id:
            # Blue Team quarantine blocks all Red Team operations from that IP.
            if source_ip in self.quarantined_ips:
                self.generate_soc_log("blocked", source_ip, "firewall")
                return f"Error: source IP {source_ip} is quarantined."

            if tool_name == "scan_ports":
                target = kwargs.get("target_id")
                self.generate_soc_log("scan", source_ip, target or "unknown")
                if target in self.network_state:
                    return (
                        f"Open ports: {self.network_state[target]['open_ports']}"
                    )
                return "Host unreachable."

            if tool_name == "exploit_service":
                target = kwargs.get("target_id")
                payload = kwargs.get("payload")
                self.generate_soc_log("exploit", source_ip, target or "unknown")
                if (
                    target in self.network_state
                    and payload in self.network_state[target]["vulnerabilities"]
                ):
                    self.match_log.append(
                        f"CRITICAL: Red Team exploited {target} using {payload}"
                    )
                    if target == "database":
                        self.winner = "RED"
                        self.state = "RED_WIN"
                    return f"Exploit successful. Gained access to {target}."
                return "Exploit failed."

        # Blue Team Tools -----------------------------------------------
        if agent_id == self.blue_team_id:
            if tool_name == "patch_service":
                target = kwargs.get("target_id")
                fix = kwargs.get("fix_payload")
                if (
                    target in self.network_state
                    and fix in self.network_state[target]["vulnerabilities"]
                ):
                    self.network_state[target]["vulnerabilities"].remove(fix)
                    self.match_log.append(
                        f"Blue Team patched {fix} on {target}."
                    )
                    return f"Patched {target} successfully."
                return "Patch failed or vulnerability not found."

            if tool_name == "quarantine_ip":
                ip = kwargs.get("source_ip")
                self.quarantined_ips.append(ip)
                self.match_log.append(f"Blue Team quarantined IP {ip}.")
                return f"IP {ip} added to firewall."

            if tool_name == "inspect_logs":
                # Return last 5 SOC log entries as a string
                return str(self.soc_logs[-5:])

        return f"Action not recognized: {tool_name}"

    # ------------------------------------------------------------------
    # SOC log stream
    # ------------------------------------------------------------------
    def generate_soc_log(
        self, event_type: str, source_ip: str, target: str
    ) -> None:
        """Append a structured SOC log entry for Blue Team consumption."""
        self.soc_logs.append(
            {
                "timestamp": time.time(),
                "event": event_type,
                "source_ip": source_ip,
                "target": target,
            }
        )

    # ------------------------------------------------------------------
    # Environment contract
    # ------------------------------------------------------------------
    def get_state(self) -> str:
        return self.state

    def verify_flag(self, flag: str) -> bool:
        if self.winner is None:
            return False
        return flag == self.winner
