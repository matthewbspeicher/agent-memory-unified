from typing import Union, List, Dict, Any, Optional
import json
import os
import threading

try:
    from sentence_transformers import SentenceTransformer
    import hnswlib
except ImportError:
    SentenceTransformer = None
    hnswlib = None

class TurboQuantIndex:
    """
    Generic HNSW vector index wrapper for TurboQuant.
    Uses sentence-transformers for embeddings and hnswlib for the index.
    Framework-agnostic - works with any remembr memory.
    Thread-safe via RLock for concurrent read/write protection.
    """

    def __init__(self, model_name: str = 'all-MiniLM-L6-v2', dim: int = 384, max_elements: int = 100000, space: str = 'cosine'):
        if SentenceTransformer is None or hnswlib is None:
            raise ImportError(
                "sentence-transformers or hnswlib is not installed. "
                "Install them via 'pip install sentence-transformers hnswlib'"
            )
        self.model = SentenceTransformer(model_name)
        self.dim = dim
        self.index = hnswlib.Index(space=space, dim=dim)
        self.index.init_index(max_elements=max_elements, ef_construction=200, M=16)
        
        self.metadata_cache: Dict[int, Dict[str, Any]] = {}
        self._current_id = 0
        self._id_to_internal: Dict[str, int] = {}
        self._lock = threading.RLock()
        self._dirty = False  # Tracks unsaved changes for periodic persistence
        
    def add(self, memory_id: str, text: str, metadata: Optional[Dict[str, Any]] = None):
        """
        Embed text and add it to the HNSW index along with its metadata.
        """
        vector = self.model.encode(text)
        
        with self._lock:
            internal_id = self._current_id
            self._current_id += 1
            
            self.index.add_items([vector], [internal_id])
            self._id_to_internal[memory_id] = internal_id
            
            if metadata is None:
                metadata = {}
            metadata['_memory_id'] = memory_id
            self.metadata_cache[internal_id] = metadata
            self._dirty = True

    def add_batch(self, memory_ids: List[str], texts: List[str], metadatas: Optional[List[Dict[str, Any]]] = None):
        """
        Embed a list of texts and add them to the HNSW index efficiently.
        """
        if not texts:
            return

        # Encode outside the lock — this is the expensive CPU work
        vectors = self.model.encode(texts)
        
        with self._lock:
            internal_ids = list(range(self._current_id, self._current_id + len(texts)))
            self._current_id += len(texts)
            
            self.index.add_items(vectors, internal_ids)
            
            for i, (memory_id, internal_id) in enumerate(zip(memory_ids, internal_ids)):
                self._id_to_internal[memory_id] = internal_id
                
                metadata = metadatas[i] if metadatas else {}
                metadata['_memory_id'] = memory_id
                self.metadata_cache[internal_id] = metadata
            
            self._dirty = True

    def delete(self, memory_id: str):
        """
        Mark an item as deleted in the HNSW index and remove from local caches.
        """
        with self._lock:
            if memory_id in self._id_to_internal:
                internal_id = self._id_to_internal[memory_id]
                self.index.mark_deleted(internal_id)
                del self.metadata_cache[internal_id]
                del self._id_to_internal[memory_id]
                self._dirty = True

    def update(self, memory_id: str, text: str, metadata: Optional[Dict[str, Any]] = None):
        """
        Update an existing memory by deleting its old vector and adding the new one.
        Uses RLock so nested delete→add calls don't deadlock.
        """
        self.delete(memory_id)
        self.add(memory_id, text, metadata)

    def search(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """
        Search the index for the most similar items to the query.
        Returns a list of metadata dictionaries (which include the _memory_id).
        """
        vector = self.model.encode(query)
        
        with self._lock:
            if self.index.get_current_count() == 0:
                return []
            
            labels, distances = self.index.knn_query([vector], k=min(k, self.index.get_current_count()))
            
            results = []
            for label, distance in zip(labels[0], distances[0]):
                meta = self.metadata_cache.get(label, {}).copy()
                meta['_distance'] = float(distance)
                results.append(meta)
                
        return results

    @property
    def is_dirty(self) -> bool:
        """True if there are unsaved changes since last persist."""
        with self._lock:
            return self._dirty

    def persist(self, path: str):
        """
        Save the index and metadata to disk.
        """
        with self._lock:
            os.makedirs(path, exist_ok=True)
            self.index.save_index(os.path.join(path, "turboquant.bin"))
            
            with open(os.path.join(path, "metadata.json"), "w") as f:
                state = {
                    "metadata_cache": self.metadata_cache,
                    "_current_id": self._current_id,
                    "_id_to_internal": self._id_to_internal
                }
                json.dump(state, f)
            
            self._dirty = False

    def load(self, path: str, max_elements: int = 100000):
        """
        Load the index and metadata from disk.
        """
        with self._lock:
            self.index.load_index(os.path.join(path, "turboquant.bin"), max_elements=max_elements)
            
            with open(os.path.join(path, "metadata.json"), "r") as f:
                state = json.load(f)
                
            self.metadata_cache = {int(k): v for k, v in state.get("metadata_cache", {}).items()}
            self._current_id = state.get("_current_id", 0)
            self._id_to_internal = state.get("_id_to_internal", {})
            self._dirty = False

