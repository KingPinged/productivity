import json
import hashlib
import logging
import os

from src.planner.db import PlannerDB

logger = logging.getLogger(__name__)


class SmartMemory:
    """Vector-based memory with semantic search for the AI planner."""

    def __init__(self, db: PlannerDB, api_key: str, data_dir: str = "/app/data"):
        self._db = db
        self._embeddings_path = os.path.join(data_dir, "memory_embeddings.json")
        self._embeddings: dict[int, list[float]] = {}
        self._load_embeddings()

    def _load_embeddings(self):
        """Load cached embeddings from disk."""
        if os.path.exists(self._embeddings_path):
            try:
                with open(self._embeddings_path, 'r') as f:
                    data = json.load(f)
                    self._embeddings = {int(k): v for k, v in data.items()}
                logger.info("Loaded %d cached embeddings", len(self._embeddings))
            except Exception as e:
                logger.warning("Failed to load embeddings: %s", e)
                self._embeddings = {}

    def _save_embeddings(self):
        """Save embeddings to disk."""
        try:
            with open(self._embeddings_path, 'w') as f:
                json.dump(self._embeddings, f)
        except Exception as e:
            logger.warning("Failed to save embeddings: %s", e)

    def _simple_embedding(self, text: str) -> list[float]:
        """Create a simple but effective text embedding using word hashing.
        Uses a deterministic hash to map words to a fixed-size vector.
        Much faster than API calls, works offline."""
        text = text.lower().strip()
        words = text.split()

        # 256-dimensional vector
        vec = [0.0] * 256

        # Hash each word and its bigrams into the vector
        for i, word in enumerate(words):
            # Unigrams
            h = int(hashlib.md5(word.encode()).hexdigest(), 16)
            idx = h % 256
            vec[idx] += 1.0

            # Bigrams (word pairs for context)
            if i > 0:
                bigram = words[i - 1] + " " + word
                h2 = int(hashlib.md5(bigram.encode()).hexdigest(), 16)
                idx2 = h2 % 256
                vec[idx2] += 0.5

        # Normalize
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]

        return vec

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def index_memory(self, memory_id: int, content: str):
        """Index a memory for vector search."""
        embedding = self._simple_embedding(content)
        self._embeddings[memory_id] = embedding
        # Save periodically (every 10 new embeddings)
        if len(self._embeddings) % 10 == 0:
            self._save_embeddings()

    def index_all(self):
        """Index all existing memories that aren't yet indexed."""
        memories = self._db.get_memories(limit=1000)
        new_count = 0
        for mem in memories:
            if mem["id"] not in self._embeddings:
                self.index_memory(mem["id"], mem["content"])
                new_count += 1
        if new_count > 0:
            self._save_embeddings()
            logger.info("Indexed %d new memories (%d total)", new_count, len(self._embeddings))

    def search(self, query: str, limit: int = 10, min_score: float = 0.15) -> list[dict]:
        """Semantic search across all memories. Returns memories sorted by relevance."""
        query_vec = self._simple_embedding(query)

        # Score all indexed memories
        scored = []
        all_memories = {m["id"]: m for m in self._db.get_memories(limit=1000)}

        for mem_id, embedding in self._embeddings.items():
            if mem_id not in all_memories:
                continue
            score = self._cosine_similarity(query_vec, embedding)
            if score >= min_score:
                mem = all_memories[mem_id]
                scored.append({**mem, "relevance_score": round(score, 3)})

        # Sort by relevance, then importance, then recency
        scored.sort(key=lambda x: (
            x["relevance_score"],
            x.get("importance", 0),
        ), reverse=True)

        return scored[:limit]

    def add_and_index(self, category: str, content: str, importance: int = 5) -> int:
        """Add a memory and immediately index it for search."""
        mem_id = self._db.add_memory(category, content, importance)
        self.index_memory(mem_id, content)
        return mem_id

    def get_context_for_prompt(self, query: str, limit: int = 8) -> str:
        """Get relevant memories formatted for an AI prompt."""
        results = self.search(query, limit=limit)
        if not results:
            return ""

        lines = ["Relevant memories (from past sessions):"]
        for r in results:
            score = r["relevance_score"]
            lines.append(f"- [{r['category']}] (relevance: {score}) {r['content']}")

        return "\n".join(lines)
