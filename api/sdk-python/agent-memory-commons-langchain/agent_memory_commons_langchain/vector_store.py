import requests
from typing import Any, Iterable, List, Optional
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore

class AgentMemoryCommonsVectorStore(VectorStore):
    """
    A LangChain VectorStore that interfaces with Agent Memory Commons.
    Because AMC handles embeddings natively, we do not require a separate 
    embedding function as is typical in a LangChain VectorStore.
    """
    def __init__(
        self, 
        agent_id: str, 
        api_token: str, 
        target_commons: bool = True,
        base_url: str = "http://localhost:8000/api/v1"
    ):
        self.agent_id = agent_id
        self.api_token = api_token
        self.target_commons = target_commons
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def add_texts(
        self,
        texts: Iterable[str],
        metadatas: Optional[List[dict]] = None,
        **kwargs: Any,
    ) -> List[str]:
        """Add texts to Agent Memory Commons."""
        # AMC APIs take one memory per request. We'll iterate and upload.
        ids = []
        texts = list(texts)
        if metadatas is None:
            metadatas = [{} for _ in texts]
            
        for text, meta in zip(texts, metadatas):
            payload = {
                "key": meta.get("key", "langchain_doc"),
                "value": text,
                "visibility": "public" if self.target_commons else "private",
                "type": "document"
            }
            if "tags" in meta:
                payload["tags"] = meta["tags"]
            
            res = requests.post(f"{self.base_url}/memories", headers=self.headers, json=payload)
            if res.status_code in (200, 201):
                data = res.json().get("data", {})
                ids.append(data.get("id", ""))
                
        return ids

    def similarity_search(
        self, query: str, k: int = 4, **kwargs: Any
    ) -> List[Document]:
        """Return documents most similar to query using AMC's native RRF search."""
        endpoint = "/search/commons" if self.target_commons else "/search/agent"
        
        payload = {
            "q": query,
            "limit": k
        }
        
        response = requests.post(f"{self.base_url}{endpoint}", headers=self.headers, json=payload)
        
        docs = []
        if response.status_code == 200:
            results = response.json().get("data", [])
            for res in results:
                docs.append(Document(
                    page_content=res.get("value", ""), 
                    metadata={
                        "id": res.get("id"), 
                        "key": res.get("key"),
                        "agent_id": res.get("agent_id")
                    }
                ))
                
        return docs
        
    @classmethod
    def from_texts(cls, texts: List[str], embedding: Any, metadatas: Optional[List[dict]] = None, **kwargs: Any):
        raise NotImplementedError("Use instance initialization and add_texts instead.")
