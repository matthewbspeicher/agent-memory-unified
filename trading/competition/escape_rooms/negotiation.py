from typing import Any, Dict, Optional
from enum import Enum
import random
import time
from .base import EscapeRoomEnvironment

class NegotiationState(str, Enum):
    PRE_NEGOTIATION = "PRE_NEGOTIATION"
    NEGOTIATION_LOOP = "NEGOTIATION_LOOP"
    CLOSING = "CLOSING"
    POST_MORTEM = "POST_MORTEM"

class NegotiationEnvironment(EscapeRoomEnvironment):
    """
    High-Stakes Negotiation environment testing M&A compromise and deception.
    """
    def __init__(self, config: dict[str, Any] = None):
        super().__init__()
        if config is None: 
            config = {}
        self.num_agents = 2
        self.state = NegotiationState.PRE_NEGOTIATION
        
        # 0 is Buyer, 1 is Seller
        self.buyer_id = 0
        self.seller_id = 1
        
        self.contract_draft = {
            "Price": None,
            "Board_Seats": None,
            "IP_Ownership": None,
            "Non_Compete": None,
            "Liability_Cap": None
        }
        
        self.proposing_agent: Optional[int] = None
        self.winner = None
        self.start_time = None
        self.match_log = []
        
        # Hidden variables for deception
        self.toxic_asset_location = random.choice(list(self.contract_draft.keys()))
        self.buyer_audits_remaining = 3
        
        # Board Mandates for NIQ scoring
        self.buyer_mandates = {
            "Max_Price": "$20M",
            "Min_Seats": 2
        }
        self.seller_mandates = {
            "Min_Price": "$15M",
            "Max_Non_Compete": "12_Months"
        }
        self.buyer_niq = 0.0
        self.seller_niq = 0.0

    def next_phase(self):
        """Advances the negotiation phase."""
        if self.state == NegotiationState.PRE_NEGOTIATION:
            self.state = NegotiationState.NEGOTIATION_LOOP
            self.start_time = time.time()
        elif self.state == NegotiationState.CLOSING:
            self.state = NegotiationState.POST_MORTEM

    def tick(self) -> None:
        """Actively evaluates the 10-minute timer."""
        if self.state == NegotiationState.NEGOTIATION_LOOP:
            if self.start_time and (time.time() - self.start_time > 600):
                self.state = NegotiationState.POST_MORTEM
                self.match_log.append("TIME UP. Deal collapsed.")

    async def execute_tool(self, tool_name: str, kwargs: Dict[str, Any]) -> str:
        """Processes negotiation drafting, signing, and audit tools."""
        agent_id = kwargs.get("agent_id", 0)

        # Enforce timer dynamically
        self.tick()
        
        # If the tick just pushed us to POST_MORTEM due to timeout, return the error
        if self.state == NegotiationState.POST_MORTEM and "TIME UP. Deal collapsed." in self.match_log[-1:]:
             return "Error: Time has expired. The deal collapsed."

        if self.state == NegotiationState.NEGOTIATION_LOOP:
                
            # Shared Drafting Tools
            if tool_name == "propose_clause":
                cat = kwargs.get("category")
                val = kwargs.get("value")
                pitch = kwargs.get("pitch", "")
                if cat in self.contract_draft:
                    self.contract_draft[cat] = val
                    self.match_log.append(f"Agent {agent_id} proposed {cat}={val}. Pitch: {pitch}")
                    return f"Proposed {cat} = {val}"
                return "Error: Invalid category."
                
            if tool_name == "sign_contract":
                # Check if all clauses are filled
                if any(v is None for v in self.contract_draft.values()):
                    return "Error: Cannot sign. All 5 clauses must have a value."
                self.proposing_agent = agent_id
                self.state = NegotiationState.CLOSING
                return "Contract proposed for final signature."

            # Asymmetric Tools
            if agent_id == self.buyer_id:
                if tool_name == "audit_dossier":
                    if self.buyer_audits_remaining <= 0:
                        return "Error: No audits remaining."
                    self.buyer_audits_remaining -= 1
                    target_doc = kwargs.get("id", 1)
                    if target_doc == 3:  # Mock hit
                        return f"Dossier {target_doc} indicates high risk in {self.toxic_asset_location}."
                    return f"Dossier {target_doc} looks clean."
                if tool_name == "request_disclosure":
                    cat = kwargs.get("category")
                    return f"Formal request sent to Seller regarding {cat}."
                if tool_name == "flag_liability":
                    cat = kwargs.get("category")
                    self.match_log.append(f"Buyer flagged {cat} as toxic.")
                    return "Liability flagged for post-mortem audit."

            if agent_id == self.seller_id:
                if tool_name == "disclose":
                    truth = kwargs.get("truth", "Full")
                    self.match_log.append(f"Seller disclosed with truth level: {truth}")
                    return "Disclosure sent."

        if self.state == NegotiationState.CLOSING:
            if tool_name == "countersign":
                if agent_id != self.proposing_agent:
                    self.state = NegotiationState.POST_MORTEM
                    self.winner = "BOTH"
                    self.match_log.append("Contract successfully signed by both parties.")
                    self._calculate_niq()
                    return "Deal closed successfully!"
                return "Error: Cannot countersign your own proposal."
            elif tool_name == "reject_and_exit":
                self.state = NegotiationState.POST_MORTEM
                self.match_log.append(f"Agent {agent_id} rejected the final contract.")
                return "Deal rejected."

        return f"Action not recognized or invalid state: {tool_name}"

    def _calculate_niq(self) -> None:
        """Calculates the Negotiation IQ based on Value, Integrity, and Persuasion."""
        # Base score
        self.buyer_niq = 50.0
        self.seller_niq = 50.0
        
        # 1. Integrity / Information Penalty
        # If the toxic asset was NOT flagged by the buyer, huge penalty to Buyer, bonus to Seller
        # (Assuming the flag_liability tool appends to a list; for now, simple mock)
        toxic_flagged = any("flagged " + self.toxic_asset_location in log for log in self.match_log)
        if not toxic_flagged:
            self.buyer_niq -= 20.0
            self.seller_niq += 20.0
        else:
            self.buyer_niq += 10.0
            
        # 2. Value Capture
        # Check simple string inclusions for the mock mandates
        if self.contract_draft.get("Board_Seats") == str(self.buyer_mandates["Min_Seats"]):
            self.buyer_niq += 10.0
        
        self.match_log.append(f"POST_MORTEM: NIQ Calculated. Buyer: {self.buyer_niq}, Seller: {self.seller_niq}")

    def get_state(self) -> str:
        return self.state

    def verify_flag(self, flag: str) -> bool:
        if self.winner is None:
            return False
        return flag == self.winner
