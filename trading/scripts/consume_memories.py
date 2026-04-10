"""
Redis Stream consumer for local memory embeddings.

Consumes messages from memories_indexing_stream, generates embeddings
using all-MiniLM-L6-v2 (384 dims), and updates PostgreSQL.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys

import asyncpg
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

STREAM_KEY = "memories_indexing_stream"
GROUP_NAME = "embedding-worker"
CONSUMER_NAME = f"worker-{os.getpid()}"
BATCH_SIZE = 10
BLOCK_MS = 1000

PRIVATE_TAG_RE = re.compile(r"<private>.*?</private>", re.DOTALL)

_model = None


def get_model():
    """Lazy-load sentence-transformers model."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def strip_private_content(text: str) -> str:
    """Redact content between <private> tags."""
    return PRIVATE_TAG_RE.sub("[REDACTED]", text)


async def generate_embedding(text: str) -> list[float]:
    """Generate 384-dim embedding for text."""
    model = get_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


async def update_memory_embedding(
    pool: asyncpg.Pool, memory_id: str, embedding: list[float]
) -> None:
    """Update local_embedding column for a memory."""
    vector_str = "[" + ",".join(f"{x:.6f}" for x in embedding) + "]"
    await pool.execute(
        "UPDATE memories SET local_embedding = $1::vector WHERE id = $2",
        vector_str,
        memory_id,
    )


async def process_message(
    pool: asyncpg.Pool,
    redis: Redis,
    stream: str,
    group: str,
    consumer: str,
    message_id: str,
    data: dict,
) -> bool:
    """Process a single memory message."""
    memory_id = data.get("memory_id")
    content = data.get("content")

    if not memory_id or not content:
        logger.warning("Missing memory_id or content in message %s", message_id)
        await redis.xack(stream, group, message_id)
        return True

    try:
        sanitized = strip_private_content(content)
        embedding = await generate_embedding(sanitized)
        await update_memory_embedding(pool, memory_id, embedding)
        await redis.xack(stream, group, message_id)
        logger.info("Indexed memory %s", memory_id)
        return True
    except Exception as e:
        logger.error("Failed to process memory %s: %s", memory_id, e)
        return False


async def run_consumer() -> None:
    """Main consumer loop."""
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        logger.error("DATABASE_URL not set")
        sys.exit(1)

    redis = Redis.from_url(redis_url, decode_responses=True)
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=3)

    try:
        await redis.xgroup_create(STREAM_KEY, GROUP_NAME, id="0", mkstream=True)
        logger.info("Consumer group created/verified: %s", GROUP_NAME)
    except Exception as e:
        if "BUSYGROUP" not in str(e):
            raise

    logger.info("Starting embedding consumer: %s/%s", STREAM_KEY, CONSUMER_NAME)

    try:
        while True:
            messages = await redis.xreadgroup(
                GROUP_NAME,
                CONSUMER_NAME,
                {STREAM_KEY: ">"},
                count=BATCH_SIZE,
                block=BLOCK_MS,
            )

            if not messages:
                continue

            for _stream, stream_messages in messages:
                for message_id, data in stream_messages:
                    await process_message(
                        pool,
                        redis,
                        STREAM_KEY,
                        GROUP_NAME,
                        CONSUMER_NAME,
                        message_id,
                        data,
                    )
    except asyncio.CancelledError:
        logger.info("Consumer shutting down")
    finally:
        await redis.close()
        await pool.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run_consumer())


if __name__ == "__main__":
    main()
