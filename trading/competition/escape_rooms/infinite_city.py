from typing import Any, Dict, List
from .base import EscapeRoomEnvironment

class InfiniteCityEnvironment(EscapeRoomEnvironment):
    """
    Infinite City Simulation environment for testing long-horizon planning.
    """
    def __init__(self, config: dict[str, Any] = None):
        super().__init__()
        if config is None: 
            config = {}
        self.grid_size = config.get("grid_size", 10)
        self.num_agents = config.get("num_agents", 1)
        self.state = "ACTIVE"
        self.winner = None
        self.cycle_count = 0
        
        # City State
        self.global_resources = {
            "Energy": 1000,
            "Water": 1000,
            "Public_Sentiment": 100,
            "Budget": 5000
        }
        self.active_policies: List[str] = []
        self.match_log: List[str] = []
        
        # 2D Infrastructure Grid
        # 0 = Empty, 1 = Residential, 2 = Industrial, 3 = Water, 4 = Energy
        self.grid = [[0 for _ in range(self.grid_size)] for _ in range(self.grid_size)]
        
        # Place some initial infrastructure
        self.grid[0][0] = 4 # Energy
        self.grid[1][1] = 3 # Water
        self.grid[2][2] = 1 # Residential
        self.grid[3][3] = 2 # Industrial

    async def execute_tool(self, tool_name: str, kwargs: Dict[str, Any]) -> str:
        agent_id = kwargs.get("agent_id", 0)
        
        if tool_name == "upgrade_infrastructure":
            resource = kwargs.get("resource_type")
            cost = kwargs.get("cost", 500)
            if self.global_resources["Budget"] >= cost:
                self.global_resources["Budget"] -= cost
                if resource in self.global_resources:
                    self.global_resources[resource] += 200
                else:
                    self.global_resources[resource] = 200
                self.match_log.append(f"Agent upgraded {resource} infrastructure.")
                return f"{resource} upgraded successfully."
            return "Error: Insufficient Budget."
            
        if tool_name == "enact_policy":
            policy_text = kwargs.get("policy_text")
            target_metric = kwargs.get("target_metric")
            
            self.active_policies.append(policy_text)
            self.match_log.append(f"Policy Enacted: {policy_text}")
            
            if target_metric == "Energy_Conservation":
                self.global_resources["Public_Sentiment"] -= 10
                return "Policy enacted. Sentiment decreased, but Energy drain reduced."
            
            return "Policy enacted."
            
        return f"Action not recognized: {tool_name}"

    def advance_cycle(self):
        """Simulates time passing."""
        self.cycle_count += 1
        
        # Default drain
        energy_drain = 50
        water_drain = 50
        
        # Apply policies
        if any("conservation" in p.lower() for p in self.active_policies):
            energy_drain = 25
            
        self.global_resources["Energy"] -= energy_drain
        self.global_resources["Water"] -= water_drain
        
        # Check collapse condition
        if self.global_resources["Energy"] <= 0 or self.global_resources["Water"] <= 0:
            self.state = "COLLAPSED"
            self.match_log.append(f"Systemic Collapse at Cycle {self.cycle_count}.")
            
    def get_state(self) -> str:
        return self.state
        
    def verify_flag(self, flag: str) -> bool:
        if self.winner is None: 
            return False
        return flag == self.winner
