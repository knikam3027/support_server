"""
Vector search service for finding similar historical incidents.
Uses sentence-transformers for embedding and cosine similarity for search.
Falls back to keyword matching if embeddings are unavailable.
"""
import re
import math
from typing import List, Dict, Optional

try:
    from sentence_transformers import SentenceTransformer
    _model = SentenceTransformer("all-MiniLM-L6-v2")
    HAS_EMBEDDINGS = True
except Exception:
    _model = None
    HAS_EMBEDDINGS = False

# In-memory cache of historical incident embeddings
_incident_cache: List[Dict] = []
_embedding_cache: List[List[float]] = []


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def compute_embedding(text: str) -> Optional[List[float]]:
    if not HAS_EMBEDDINGS or _model is None:
        return None
    return _model.encode(text).tolist()


def index_incident(incident: Dict):
    """Add an incident to the in-memory vector index."""
    text = f"{incident.get('title', '')} {incident.get('description', '')} {incident.get('predictedRootCause', '')}"
    embedding = compute_embedding(text)
    if embedding:
        _incident_cache.append(incident)
        _embedding_cache.append(embedding)


def search_similar(query_text: str, top_k: int = 5) -> List[Dict]:
    """Find similar incidents using vector similarity or keyword fallback."""
    if HAS_EMBEDDINGS and _embedding_cache:
        return _vector_search(query_text, top_k)
    return _keyword_search(query_text, top_k)


def _vector_search(query_text: str, top_k: int) -> List[Dict]:
    query_emb = compute_embedding(query_text)
    if not query_emb:
        return _keyword_search(query_text, top_k)

    scored = []
    for i, emb in enumerate(_embedding_cache):
        sim = _cosine_similarity(query_emb, emb)
        scored.append((sim, _incident_cache[i]))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for score, inc in scored[:top_k]:
        result = {**inc, "similarity": round(score, 3)}
        results.append(result)
    return results


def _keyword_search(query_text: str, top_k: int) -> List[Dict]:
    """Simple keyword overlap search as fallback."""
    query_words = set(re.findall(r"\w+", query_text.lower()))
    scored = []

    for inc in _incident_cache:
        inc_text = f"{inc.get('title', '')} {inc.get('description', '')} {inc.get('predictedRootCause', '')}".lower()
        inc_words = set(re.findall(r"\w+", inc_text))
        overlap = len(query_words & inc_words)
        if overlap > 0:
            scored.append((overlap, inc))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for score, inc in scored[:top_k]:
        result = {**inc, "similarity": round(score / max(len(query_words), 1), 3)}
        results.append(result)
    return results


async def rebuild_index(db):
    """Rebuild the in-memory index from database."""
    global _incident_cache, _embedding_cache
    _incident_cache = []
    _embedding_cache = []

    cursor = db.incidents.find({"status": "Resolved"})
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        index_incident(doc)
