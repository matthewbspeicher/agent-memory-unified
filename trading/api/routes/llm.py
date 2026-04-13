from fastapi import APIRouter
from llm.stats import get_stats_collector

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/stats")
def get_llm_stats():
    collector = get_stats_collector()
    return collector.get_all_stats()


@router.get("/stats/{provider}")
def get_provider_stats(provider: str):
    collector = get_stats_collector()
    return collector.get_provider_stats(provider)


@router.post("/stats/reset")
def reset_llm_stats():
    collector = get_stats_collector()
    collector.reset()
    return {"status": "reset"}
