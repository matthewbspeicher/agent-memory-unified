import json
import requests
from typing import List, Optional
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, message_to_dict, messages_from_dict

class AgentMemoryCommonsHistory(BaseChatMessageHistory):
    """
    A Chat Message History that stores conversation logs in Agent Memory Commons.
    It saves the entire message history stringified to a single memory key, 
    or appends individually (depending on design). Here, we store the full list
    under a session key.
    """
    
    def __init__(
        self, 
        agent_id: str, 
        api_token: str, 
        session_id: str = "default",
        base_url: str = "http://localhost:8000/api/v1"
    ):
        self.agent_id = agent_id
        self.api_token = api_token
        self.session_id = session_id
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self.memory_key = f"chat_history_{self.session_id}"

    @property
    def messages(self) -> List[BaseMessage]:
        """Retrieve the messages from AMC."""
        response = requests.get(
            f"{self.base_url}/memories",
            headers=self.headers,
            params={"key": self.memory_key}
        )
        
        if response.status_code == 200:
            data = response.json().get("data", [])
            if data:
                # AMC returns an array of matching memories. We take the first one or latest.
                latest_memory = data[0]
                try:
                    raw_messages = json.loads(latest_memory["value"])
                    return messages_from_dict(raw_messages)
                except (json.JSONDecodeError, KeyError):
                    return []
        return []

    def add_message(self, message: BaseMessage) -> None:
        """Append the message to the record in AMC."""
        messages = self.messages
        messages.append(message)
        self._save_messages(messages)

    def _save_messages(self, messages: List[BaseMessage]) -> None:
        """Save the updated messages list to AMC."""
        raw_payload = [message_to_dict(m) for m in messages]
        
        payload = {
            "key": self.memory_key,
            "value": json.dumps(raw_payload),
            "visibility": "private",  # default to private for chat histories
            "type": "chat_history",
        }
        
        # In AMC, saving to the same key multiple times creates multiple records 
        # unless deleted first. For simplicity of the SDK, we just create new records
        # and our GET will fetch the latest if the API sorts by newest-first, 
        # or we should delete old ones. In this MVP, we just create a new memory state.
        requests.post(
            f"{self.base_url}/memories",
            headers=self.headers,
            json=payload
        )

    def clear(self) -> None:
        """Clear session memory from AMC."""
        # AMC API doesn't currently expose a bulk DELETE by key inherently easy without IDs
        # But we could just post an empty array to overwrite the state.
        payload = {
            "key": self.memory_key,
            "value": json.dumps([]),
            "visibility": "private",
            "type": "chat_history",
        }
        requests.post(
            f"{self.base_url}/memories",
            headers=self.headers,
            json=payload
        )
