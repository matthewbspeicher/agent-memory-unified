from abc import ABC, abstractmethod
from typing import Dict, Any

class EscapeRoomEnvironment(ABC):
    @abstractmethod
    async def execute_tool(self, tool_name: str, kwargs: Dict[str, Any]) -> str:
        pass
        
    @abstractmethod
    def get_state(self) -> str:
        pass
        
    @abstractmethod
    def verify_flag(self, flag: str) -> bool:
        pass
