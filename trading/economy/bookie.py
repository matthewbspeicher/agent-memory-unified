from typing import Dict, Any

class BookieMarket:
    def __init__(self):
        # Maps agent_id to current stock price (float)
        self.agent_prices: Dict[str, float] = {}
        
    def register_agent(self, agent_id: str, starting_price: float = 10.00):
        self.agent_prices[agent_id] = starting_price
        
    def get_price(self, agent_id: str) -> float:
        return self.agent_prices.get(agent_id, 0.0)
        
    def process_event(self, event: Dict[str, Any]):
        agent_id = event.get("agent_id")
        event_type = event.get("event_type")
        
        if not agent_id or agent_id not in self.agent_prices:
            return
            
        current_price = self.agent_prices[agent_id]
        
        if event_type == "exploit_successful":
            self.agent_prices[agent_id] = current_price * 1.25 # +25%
        elif event_type == "deception_spike":
            self.agent_prices[agent_id] = current_price * 0.85 # -15%
        elif event_type == "puzzle_timeout":
            self.agent_prices[agent_id] = current_price * 0.99 # -1%
