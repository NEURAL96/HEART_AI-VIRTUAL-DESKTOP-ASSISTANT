import asyncio
import uuid
import logging
import os
import math
from datetime import datetime, timezone
from typing import List, Optional
from collections import deque

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
import aiosqlite
from pydantic import BaseModel, Field

# Configure Logging (Minimal for Speed)
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("H.E.A.R.T")

_memory_engine = None


# ==========================================
# 1. ADVANCED DATA MODELS
# ==========================================

class MemoryRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str
    memory_type: str  # preference, identity, fact, instruction
    importance: float = Field(ge=0, le=10, default=5.0)
    strength: float = Field(ge=0, le=1, default=1.0)  # Starts at 1.0, decays over time
    last_accessed: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    access_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RetrievalResult(BaseModel):
    memory: MemoryRecord
    relevance_score: float


# ==========================================
# 2. SMART CLASSIFIER (Heuristic + Context)
# ==========================================

def smart_classify(message: str) -> dict:
    msg_lower = message.lower().strip()

    # High-Value Triggers
    if any(kw in msg_lower for kw in ["remember", "save", "yaad rakh", "mera naam", "i prefer", "i hate"]):
        return {"store": True, "type": "identity" if "name" in msg_lower else "preference", "importance": 9.0}

    # Transient/Low-Value
    if any(kw in msg_lower for kw in ["hi", "hello", "thanks", "ok", "time", "weather", "play"]):
        return {"store": False, "type": "transient", "importance": 0.0}

    # Substantive Statements
    if len(message.split()) > 6 and not message.endswith('?'):
        return {"store": True, "type": "fact", "importance": 6.0}

    return {"store": False, "type": "transient", "importance": 0.0}


# ==========================================
# 3. LONG-TERM MEMORY ENGINE (Async & Optimized)
# ==========================================

class LongTermMemory:
    def __init__(self, db_path: str = "heart_ltm.db"):
        self.db_path = db_path
        self.persist_dir = "./chroma_heart"

        # Initialize Embedding Function Once (Singleton Pattern)
        self.ef = embedding_functions.DefaultEmbeddingFunction()

        self.chroma_client = chromadb.Client(
            Settings(anonymized_telemetry=False, is_persistent=True, persist_directory=self.persist_dir))
        self.collection = self.chroma_client.get_or_create_collection(
            name="heart_memories_v2",
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"}
        )

    async def init_sqlite(self):
        self.db = await aiosqlite.connect(self.db_path)
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY, content TEXT, memory_type TEXT, 
                importance REAL, strength REAL, access_count INTEGER,
                last_accessed TEXT, created_at TEXT
            )
        """)
        await self.db.commit()

    async def store(self, record: MemoryRecord):
        """Stores memory in both Vector DB and SQLite asynchronously."""

        def _chroma_add():
            try:
                self.collection.add(
                    ids=[record.id],
                    documents=[record.content],
                    metadatas=[{
                        "memory_type": record.memory_type,
                        "importance": record.importance,
                        "strength": record.strength
                    }]
                )
            except Exception as e:
                logger.error(f"ChromaDB Error: {e}")

        await asyncio.to_thread(_chroma_add)

        await self.db.execute(
            """INSERT OR REPLACE INTO memories 
               (id, content, memory_type, importance, strength, access_count, last_accessed, created_at) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (record.id, record.content, record.memory_type, record.importance,
             record.strength, record.access_count, record.last_accessed.isoformat(), record.created_at.isoformat())
        )
        await self.db.commit()

    async def search(self, query: str, top_k: int = 5) -> List[MemoryRecord]:
        """Semantic Search with Re-ranking."""

        def _chroma_query():
            return self.collection.query(query_texts=[query], n_results=top_k * 2)

        results = await asyncio.to_thread(_chroma_query)
        records = []

        if results['ids'] and results['ids'][0]:
            for i, mem_id in enumerate(results['ids'][0]):
                record = await self.get_record(mem_id)
                if record:
                    # Calculate Dynamic Score: Semantic + Recency + Importance
                    dist = results['distances'][0][i] if 'distances' in results else 1.0
                    semantic_score = 1.0 - min(dist, 1.0)

                    recency_days = (datetime.now(timezone.utc) - record.last_accessed).days
                    recency_score = 1.0 / (1.0 + recency_days)

                    final_score = (semantic_score * 0.6) + (recency_score * 0.2) + ((record.importance / 10) * 0.2)
                    record.strength = min(1.0, record.strength + 0.05)  # Reinforce on retrieval
                    records.append((record, final_score))

                    # Update access stats in background
                    asyncio.create_task(self._update_access_stats(mem_id))

        # Sort by final score
        records.sort(key=lambda x: x[1], reverse=True)
        return [r[0] for r in records[:top_k]]

    async def get_record(self, memory_id: str) -> Optional[MemoryRecord]:
        async with self.db.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)) as cursor:
            row = await cursor.fetchone()
            if not row: return None
            return MemoryRecord(
                id=row[0], content=row[1], memory_type=row[2], importance=row[3],
                strength=row[4], access_count=row[5],
                last_accessed=datetime.fromisoformat(row[6]), created_at=datetime.fromisoformat(row[7])
            )

    async def _update_access_stats(self, memory_id: str):
        """Updates access count and last accessed time without blocking."""
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "UPDATE memories SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
            (now, memory_id)
        )
        await self.db.commit()

    async def apply_decay(self):
        """Simulates human forgetting curve. Deletes weak memories."""
        async with self.db.execute("SELECT id, strength FROM memories") as cursor:
            rows = await cursor.fetchall()

        for row in rows:
            mem_id, strength = row
            new_strength = strength * 0.98  # Decay factor

            if new_strength < 0.2:
                await self.delete_record(mem_id)
            else:
                await self.db.execute("UPDATE memories SET strength = ? WHERE id = ?", (new_strength, mem_id))

                # Update Chroma metadata
                def _update_meta():
                    self.collection.update(ids=[mem_id], metadatas=[{"strength": new_strength}])

                await asyncio.to_thread(_update_meta)

        await self.db.commit()

    async def delete_record(self, memory_id: str):
        def _chroma_delete():
            self.collection.delete(ids=[memory_id])

        await asyncio.to_thread(_chroma_delete)
        await self.db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        await self.db.commit()


# ==========================================
# 4. CORE ENGINE
# ==========================================

class HeartEngine:
    def __init__(self):
        self.working_mem: deque[str] = deque(maxlen=10)
        self.ltm = LongTermMemory()
        self._decay_task = None

    async def initialize(self):
        await self.ltm.init_sqlite()
        # Start background decay loop (runs every 1 hour)
        self._decay_task = asyncio.create_task(self._start_decay_loop())
        logger.info("🧠 H.E.A.R.T Cognitive Engine Initialized.")

    async def ingest(self, message: str):
        self.working_mem.append(message)
        classification = smart_classify(message)

        if not classification["store"]:
            return

        # Check for similar existing memories to avoid duplicates
        similar = await self.ltm.search(message, top_k=1)
        if similar and similar[0].strength > 0.8:
            # Refine existing memory instead of creating new one
            existing = similar[0]
            existing.content = message  # Update to latest version
            existing.strength = min(1.0, existing.strength + 0.1)
            await self.ltm.store(existing)
        else:
            # Create new memory
            record = MemoryRecord(
                content=message,
                memory_type=classification["type"],
                importance=classification["importance"]
            )
            await self.ltm.store(record)

    async def retrieve(self, query: str, top_k: int = 3) -> List[RetrievalResult]:
        records = await self.ltm.search(query, top_k=top_k)
        return [RetrievalResult(memory=r, relevance_score=1.0) for r in records]  # Score already calculated in search

    async def _start_decay_loop(self):
        while True:
            await asyncio.sleep(3600)  # Run every hour
            await self.ltm.apply_decay()


# ==========================================
# 5. GLOBAL ACCESS (Non-Blocking)
# ==========================================

async def init_memory_engine():
    global _memory_engine
    if _memory_engine is None:
        _memory_engine = HeartEngine()
        await _memory_engine.initialize()
    return _memory_engine


async def save_memory(message: str):
    """Fire-and-forget memory saving."""
    engine = await init_memory_engine()
    asyncio.create_task(engine.ingest(message))


async def recall_memory(query: str, top_k: int = 3):
    engine = await init_memory_engine()
    return await engine.retrieve(query, top_k)