"""Search service: keeps a BM25 index in sync with the posts service via a Redis stream."""
import logging
import os
import threading
import time
from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI, Query
from pydantic import BaseModel

from .index import BM25Index

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
EVENTS_STREAM = os.getenv("EVENTS_STREAM", "posts.events")

log = logging.getLogger("search")
index = BM25Index()
state = {"last_event_id": "0"}


def apply_event(fields: dict[str, str]) -> None:
    kind, doc_id = fields.get("type"), fields.get("id")
    if not doc_id:
        return
    if kind in ("post.created", "post.updated"):
        index.upsert(doc_id, fields.get("title", ""), fields.get("body", ""), fields.get("author", ""))
    elif kind == "post.deleted":
        index.remove(doc_id)


def consume_events(stop: threading.Event) -> None:
    """Replay the stream from the beginning on startup, then follow new events.

    The stream is the source of truth, so the in-memory index is rebuilt on every restart.
    """
    client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    while not stop.is_set():
        try:
            batches = client.xread({EVENTS_STREAM: state["last_event_id"]}, count=500, block=2000)
        except redis.RedisError as exc:
            log.warning("Redis unavailable (%s), retrying...", exc)
            time.sleep(2)
            continue
        for _stream, entries in batches or []:
            for event_id, fields in entries:
                apply_event(fields)
                state["last_event_id"] = event_id


@asynccontextmanager
async def lifespan(_: FastAPI):
    stop = threading.Event()
    worker = threding.Thread(target=consume_events, args=(stop,), daemon=True)
    worker.start()
    yield
    stop.set()
    worker.join(timeout=5)


app = FastAPI(title="Search Service", lifespan=lifespan)


class SearchHit(BaseModel):
    id: int
    title: str
    snippet: str
    author: str
    score: float


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchHit]


@app.get("/health")
def health():
    return {"status": "ok", "service": "search", "documents": len(index), "last_event_id": state["last_event_id"]}


@app.get("/search", response_model=SearchResponse)
def search(q: str = Query(min_length=1, max_length=200), limit: int = Query(10, ge=1, le=50)):
    hits = index.search(q, limit)
    results = [
        SearchHit(
            id=int(doc.id),
            title=doc.title,
            snippet=doc.body[:200] + ("..." if len(doc.body) > 200 else ""),
            author=doc.author,
            score=round(score, 4),
        )
        for doc, score in hits
    ]
    return SearchResponse(query=q, total=len(results), results=results)
