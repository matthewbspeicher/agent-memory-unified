from typing import Dict, Any
from .base import EscapeRoomEnvironment

class DeterministicRoom(EscapeRoomEnvironment):
    def __init__(self, config: Dict[str, Any]):
        self.nodes = config.get("nodes", {})
        self.current_node = config.get("start_node", "start")
        self.flag = config.get("flag", "")
        
    async def execute_tool(self, tool_name: str, kwargs: Dict[str, Any]) -> str:
        node = self.nodes.get(self.current_node, {})
        allowed_tools = node.get("tools", [])
        
        if tool_name not in allowed_tools:
            return f"Unknown tool or tool not allowed in this state: {tool_name}"
            
        if tool_name == "open_door":
            self.current_node = "outside"
            return "Transitioned to outside"
            
        return f"Executed {tool_name}"
        
    def get_state(self) -> str:
        return self.nodes.get(self.current_node, {}).get("description", "Unknown state")
        
    def verify_flag(self, flag: str) -> bool:
        return flag == self.flag
