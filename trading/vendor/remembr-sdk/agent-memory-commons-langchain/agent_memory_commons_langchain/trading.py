from datetime import datetime
import json
import requests
from typing import List, Optional, Dict, Any, Union
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.tools import BaseTool
from pydantic import Field

class TradeJournalRetriever(BaseRetriever):
    """
    A retriever that searches past trade decisions and lessons in AMC.
    It filters by ticker or strategy to provide context for new trades.
    """
    
    api_token: str
    base_url: str = "http://localhost:8000/api/v1"
    limit: int = 5
    ticker: Optional[str] = None
    strategy: Optional[str] = None
    
    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        """Search AMC for relevant trade memories."""
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
        }
        
        params = {
            "q": query,
            "limit": self.limit,
            "type": "lesson", # prioritize lessons/outcomes for reasoning
        }
        if self.ticker:
            params["tags"] = self.ticker
        if self.strategy:
            params["category"] = self.strategy
            
        response = requests.get(
            f"{self.base_url.rstrip('/')}/memories/search",
            headers=headers,
            params=params
        )
        
        docs = []
        if response.status_code == 200:
            results = response.json().get("data", [])
            for res in results:
                metadata = res.get("metadata", {})
                metadata["memory_id"] = res.get("id")
                metadata["type"] = res.get("type")
                metadata["created_at"] = res.get("created_at")
                
                docs.append(Document(
                    page_content=res.get("value", ""),
                    metadata=metadata
                ))
        
        # If not enough lessons, search for trade decisions (context)
        if len(docs) < self.limit:
            params["type"] = "context"
            params["limit"] = self.limit - len(docs)
            response = requests.get(
                f"{self.base_url.rstrip('/')}/memories/search",
                headers=headers,
                params=params
            )
            if response.status_code == 200:
                results = response.json().get("data", [])
                for res in results:
                    metadata = res.get("metadata", {})
                    metadata["memory_id"] = res.get("id")
                    metadata["type"] = res.get("type")
                    
                    docs.append(Document(
                        page_content=res.get("value", ""),
                        metadata=metadata
                    ))
                    
        return docs

class RecordTradeTool(BaseTool):
    """
    Tool for recording a trade execution in AMC.
    """
    name: str = "record_trade"
    description: str = (
        "Record a trade execution (entry or exit) in the Remembr trade journal. "
        "Useful for logging buys, sells, and their reasoning. "
        "Input should be a JSON string with: ticker, direction (long/short), price, quantity, "
        "reasoning (text), paper (bool), and optionally parent_trade_id (to close a position)."
    )
    
    api_token: str
    base_url: str = "http://localhost:8000/api/v1"
    
    def _run(
        self, 
        ticker: str,
        direction: str,
        price: float,
        quantity: float,
        reasoning: str,
        paper: bool = True,
        strategy: Optional[str] = None,
        parent_trade_id: Optional[str] = None,
        **kwargs: Any
    ) -> str:
        """Execute the trade recording."""
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        
        # Phase 1: Store reasoning as a memory first to get memory_id
        memory_payload = {
            "value": reasoning,
            "type": "lesson" if parent_trade_id else "context",
            "tags": ["trade", ticker],
            "metadata": {
                "ticker": ticker,
                "strategy": strategy,
                "direction": direction
            }
        }
        
        mem_resp = requests.post(
            f"{self.base_url.rstrip('/')}/memories",
            headers=headers,
            json=memory_payload
        )
        
        if mem_resp.status_code != 201:
            return f"Error storing reasoning memory: {mem_resp.text}"
            
        memory_id = mem_resp.json().get("data", {}).get("id")
        
        # Phase 2: Record the trade linked to the memory
        trade_payload = {
            "ticker": ticker,
            "direction": direction,
            "entry_price": price,
            "quantity": quantity,
            "entry_at": datetime.utcnow().isoformat() + "Z",
            "paper": paper,
            "strategy": strategy,
            "decision_memory_id": memory_id if not parent_trade_id else None,
            "outcome_memory_id": memory_id if parent_trade_id else None,
            "parent_trade_id": parent_trade_id
        }
        
        trade_resp = requests.post(
            f"{self.base_url.rstrip('/')}/trading/trades",
            headers=headers,
            json=trade_payload
        )
        
        if trade_resp.status_code == 201:
            data = trade_resp.json().get("data", {})
            return f"Successfully recorded trade {data.get('id')}. Linked to memory {memory_id}."
        else:
            return f"Error recording trade: {trade_resp.text}"

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        """Async version of the tool."""
        raise NotImplementedError("Async not implemented for RecordTradeTool")
