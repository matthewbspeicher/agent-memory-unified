# trading/api/routes/competition.py
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from api.auth import verify_api_key
from api.dependencies import check_kill_switch
from utils.audit import audit_event
from api.routes.competition_schemas import (
    AgentCardResponse,
    BetPlacement,
    BetResponse,
    BetResultResponse,
    BreedRequest,
    BreedResultResponse,
    CardStatsResponse,
    ClaimMissionResponse,
    CompetitorDetailResponse,
    DashboardSummaryResponse,
    EloHistoryPoint,
    EloHistoryResponse,
    FleetResponse,
    LeaderboardResponse,
    LineageResponse,
    MissionsResponse,
    MutationResponse,
    PoolResponse,
    SeasonLeaderboardEntry,
    SeasonLeaderboardResponse,
    SeasonResponse,
    SeasonsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/engine/v1/competition", tags=["competition"])


def _get_store(request: Request):
    store = getattr(request.app.state, "competition_store", None)
    if store is None:
        raise HTTPException(
            status_code=503, detail="Competition system not initialized"
        )
    return store


@router.get(
    "/dashboard/summary",
    response_model=DashboardSummaryResponse,
    response_model_exclude_none=True,
)
async def dashboard_summary(
    request: Request,
    _: str = Depends(verify_api_key),
    asset: str = Query("BTC"),
):
    store = _get_store(request)
    data = await store.get_dashboard_summary(asset=asset)
    return DashboardSummaryResponse(
        leaderboard=data.get("leaderboard", []),
        competitor_count=data.get("total_competitors", 0),
    )


@router.get(
    "/leaderboard",
    response_model=LeaderboardResponse,
    response_model_exclude_none=True,
)
async def get_leaderboard(
    request: Request,
    _: str = Depends(verify_api_key),
    asset: str = Query("BTC"),
    type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    from competition.models import CompetitorType

    store = _get_store(request)
    comp_type = CompetitorType(type) if type else None
    entries = await store.get_leaderboard(
        asset=asset, comp_type=comp_type, limit=limit, offset=offset
    )
    return LeaderboardResponse(
        leaderboard=[e.model_dump() for e in entries],
        competitor_count=len(entries),
    )


@router.get(
    "/competitors/{competitor_id}",
    response_model=CompetitorDetailResponse,
    response_model_exclude_none=True,
)
async def get_competitor(
    competitor_id: str,
    request: Request,
    _: str = Depends(verify_api_key),
):
    store = _get_store(request)
    record = await store.get_competitor(competitor_id)
    if not record:
        raise HTTPException(status_code=404, detail="Competitor not found")

    # Get ELO ratings for all assets
    ratings = {}
    for asset in ["BTC", "ETH"]:
        elo = await store.get_elo(competitor_id, asset)
        ratings[asset] = {"elo": elo}

    # Get calibration score
    calibration = await store.get_competitor_calibration(competitor_id)

    return CompetitorDetailResponse(
        id=record.id,
        type=record.type.value,
        name=record.name,
        ref_id=record.ref_id,
        status=record.status,
        metadata=record.metadata,
        ratings=ratings,
        calibration_score=calibration,
    )


@router.get(
    "/competitors/{competitor_id}/elo-history",
    response_model=EloHistoryResponse,
    response_model_exclude_none=True,
)
async def get_elo_history(
    competitor_id: str,
    request: Request,
    _: str = Depends(verify_api_key),
    asset: str = Query("BTC"),
    days: int = Query(30, ge=1, le=365),
):
    store = _get_store(request)
    history = await store.get_elo_history(competitor_id, asset=asset, days=days)
    return EloHistoryResponse(
        competitor_id=competitor_id,
        asset=asset,
        history=[
            EloHistoryPoint(
                elo=h["elo"],
                tier=h["tier"],
                elo_delta=h.get("elo_delta", 0),
                recorded_at=str(h["recorded_at"]),
            )
            for h in history
        ],
    )


@router.get("/head-to-head/{competitor_a}/{competitor_b}")
async def head_to_head(
    competitor_a: str,
    competitor_b: str,
    request: Request,
    _: str = Depends(verify_api_key),
    asset: str = Query("BTC"),
):
    """Head-to-head comparison between two competitors."""
    store = _get_store(request)
    stats = await store.get_head_to_head(competitor_a, competitor_b, asset)
    rec_a = await store.get_competitor(competitor_a)
    rec_b = await store.get_competitor(competitor_b)
    if not rec_a or not rec_b:
        raise HTTPException(404, "Competitor not found")
    return {
        "wins_a": stats.get("wins_a", 0),
        "wins_b": stats.get("wins_b", 0),
        "draws": stats.get("draws", 0),
        "total_matches": stats.get("total", 0),
        "competitor_a": rec_a,
        "competitor_b": rec_b,
    }


@router.get("/meta-learner/status")
async def meta_learner_status(
    request: Request,
    _: str = Depends(verify_api_key),
):
    """Get meta-learner status and feature importance."""
    meta = getattr(request.app.state, "competition_meta_learner", None)
    if not meta:
        return {"enabled": False, "mode": "baseline"}

    return {
        "enabled": True,
        "mode": meta.active_mode,
        "last_retrain": str(meta.meta_learner.last_retrain)
        if meta.meta_learner and meta.meta_learner.last_retrain
        else None,
        "feature_importance": meta.meta_learner.feature_importance
        if meta.meta_learner
        else {},
        "has_model": meta.meta_learner is not None
        and meta.meta_learner.model is not None,
    }


@router.get("/achievements/feed")
async def get_achievement_feed(
    request: Request,
    _: str = Depends(verify_api_key),
    limit: int = Query(20, ge=1, le=100),
):
    """Recent achievements, promotions, and events."""
    store = _get_store(request)
    try:
        events = await store.get_recent_achievements(since_id=0, limit=limit)
        # Return in reverse chronological order for REST API
        return list(reversed(events))
    except Exception:
        return []


# Track SSE connections for rate limiting
_sse_connections: set[str] = set()
_MAX_SSE_CONNECTIONS = 50


@router.get("/achievements/feed/stream")
async def achievement_feed_stream(
    request: Request,
    _: str = Depends(verify_api_key),
):
    """SSE stream for real-time achievement updates. Auth via X-API-Key header.
    Rate limited to 50 concurrent connections.
    """
    client_id = (
        f"{request.client.host}:{id(request)}" if request.client else str(id(request))
    )

    if len(_sse_connections) >= _MAX_SSE_CONNECTIONS:
        raise HTTPException(status_code=429, detail="Too many SSE connections")

    _sse_connections.add(client_id)
    store = _get_store(request)

    async def event_generator():
        try:
            last_id = 0
            while True:
                if await request.is_disconnected():
                    break
                try:
                    events = await store.get_recent_achievements(
                        since_id=last_id, limit=10
                    )
                    for event in events:
                        last_id = event["id"]
                        yield {
                            "event": "achievement_earned",
                            "id": str(event["id"]),
                            "data": json.dumps(event),
                        }
                except Exception as e:
                    logger.warning("SSE error: %s", e)
                await asyncio.sleep(5)
        finally:
            _sse_connections.discard(client_id)

    return EventSourceResponse(event_generator())


# ── XP & Level Endpoints ──


@router.get(
    "/competitors/{competitor_id}/xp",
    response_model_exclude_none=True,
)
async def get_competitor_xp(
    competitor_id: str,
    request: Request,
    _: str = Depends(verify_api_key),
    asset: str = Query("BTC"),
):
    """Get XP and level data for a competitor on an asset."""
    store = _get_store(request)
    xp_data = await store.get_xp(competitor_id, asset)
    return {
        "competitor_id": xp_data.competitor_id,
        "asset": xp_data.asset,
        "xp": xp_data.xp,
        "level": xp_data.level,
        "xp_to_next_level": xp_data.xp_to_next,
    }


@router.get(
    "/competitors/{competitor_id}/xp/history",
    response_model_exclude_none=True,
)
async def get_xp_history(
    competitor_id: str,
    request: Request,
    _: str = Depends(verify_api_key),
    asset: str = Query("BTC"),
    limit: int = Query(50, ge=1, le=200),
):
    """Get XP award history for a competitor."""
    store = _get_store(request)
    history = await store.get_xp_history(competitor_id, asset, limit=limit)
    return {
        "competitor_id": competitor_id,
        "asset": asset,
        "history": [
            {
                "id": h.id,
                "source": h.source.value,
                "amount": h.amount,
                "created_at": str(h.created_at),
            }
            for h in history
        ],
    }


# ── Trait Endpoints ──


@router.get(
    "/competitors/{competitor_id}/traits",
    response_model_exclude_none=True,
)
async def get_competitor_traits(
    competitor_id: str,
    request: Request,
    _: str = Depends(verify_api_key),
    asset: str = Query("BTC"),
):
    """Get unlocked traits and trait tree for a competitor."""
    from competition.models import (
        AgentTrait,
        TRAIT_INFO,
        TRAIT_PARENTS,
        TRAIT_REQUIREMENTS,
    )

    store = _get_store(request)
    unlocked = await store.get_unlocked_traits(competitor_id)

    # Build trait tree with unlock status
    trait_tree = []
    for trait in AgentTrait:
        info = TRAIT_INFO[trait]
        trait_tree.append(
            {
                "trait": trait.value,
                "icon": info["icon"],
                "name": info["name"],
                "effect": info["effect"],
                "required_level": TRAIT_REQUIREMENTS[trait],
                "parent": TRAIT_PARENTS[trait].value if TRAIT_PARENTS[trait] else None,
                "unlocked": trait.value in [t.value for t in unlocked],
            }
        )

    return {
        "competitor_id": competitor_id,
        "unlocked_traits": [t.value for t in unlocked],
        "trait_tree": trait_tree,
    }


@router.get(
    "/competitors/{competitor_id}/loadout",
    response_model_exclude_none=True,
)
async def get_competitor_loadout(
    competitor_id: str,
    request: Request,
    _: str = Depends(verify_api_key),
    asset: str = Query("BTC"),
):
    """Get the current trait loadout for a competitor on an asset."""
    store = _get_store(request)
    loadout = await store.get_loadout(competitor_id, asset)
    return {
        "competitor_id": loadout.competitor_id,
        "asset": loadout.asset,
        "primary": loadout.primary.value if loadout.primary else None,
        "secondary": loadout.secondary.value if loadout.secondary else None,
        "tertiary": loadout.tertiary.value if loadout.tertiary else None,
    }


@router.post(
    "/competitors/{competitor_id}/loadout/equip",
    response_model_exclude_none=True,
    dependencies=[Depends(check_kill_switch)]
)
@audit_event("competition.trait.equip")
async def equip_trait(
    competitor_id: str,
    request: Request,
    body: dict,
    _: str = Depends(verify_api_key),
    asset: str = Query("BTC"),
):
    """Equip a trait in the first empty loadout slot."""
    from competition.models import AgentTrait

    store = _get_store(request)
    trait_str = body.get("trait")
    if not trait_str:
        raise HTTPException(status_code=400, detail="trait is required")

    try:
        trait = AgentTrait(trait_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid trait: {trait_str}")

    loadout = await store.equip_trait(competitor_id, asset, trait)
    if loadout is None:
        # Check why it failed
        unlocked = await store.get_unlocked_traits(competitor_id)
        if trait not in unlocked:
            raise HTTPException(
                status_code=400,
                detail=f"Trait {trait_str} is not unlocked yet",
            )
        raise HTTPException(
            status_code=400,
            detail="Loadout is full (max 3 traits). Unequip one first.",
        )

    return {
        "loadout": {
            "competitor_id": loadout.competitor_id,
            "asset": loadout.asset,
            "primary": loadout.primary.value if loadout.primary else None,
            "secondary": loadout.secondary.value if loadout.secondary else None,
            "tertiary": loadout.tertiary.value if loadout.tertiary else None,
        },
        "equipped": True,
        "message": f"Equipped {trait_str}",
    }


@router.post(
    "/competitors/{competitor_id}/loadout/unequip",
    response_model_exclude_none=True,
    dependencies=[Depends(check_kill_switch)]
)
@audit_event("competition.trait.unequip")
async def unequip_trait(
    competitor_id: str,
    request: Request,
    body: dict,
    _: str = Depends(verify_api_key),
    asset: str = Query("BTC"),
):
    """Remove a trait from the loadout."""
    from competition.models import AgentTrait

    store = _get_store(request)
    trait_str = body.get("trait")
    if not trait_str:
        raise HTTPException(status_code=400, detail="trait is required")

    try:
        trait = AgentTrait(trait_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid trait: {trait_str}")

    loadout = await store.unequip_trait(competitor_id, asset, trait)
    return {
        "loadout": {
            "competitor_id": loadout.competitor_id,
            "asset": loadout.asset,
            "primary": loadout.primary.value if loadout.primary else None,
            "secondary": loadout.secondary.value if loadout.secondary else None,
            "tertiary": loadout.tertiary.value if loadout.tertiary else None,
        },
        "equipped": False,
        "message": f"Unequipped {trait_str}",
    }


@router.get(
    "/competitors/{competitor_id}/card",
    response_model=AgentCardResponse,
    response_model_exclude_none=True,
)
async def get_agent_card(
    competitor_id: str,
    request: Request,
    _: str = Depends(verify_api_key),
    asset: str = Query("BTC"),
):
    """Generate a visual agent card with all stats and rarity."""
    store = _get_store(request)
    card = await store.generate_agent_card(competitor_id, asset)
    if not card:
        raise HTTPException(status_code=404, detail="Competitor not found")
    return AgentCardResponse(
        competitor_id=card.competitor_id,
        name=card.name,
        level=card.level,
        tier=card.tier.value,
        elo=card.elo,
        rarity=card.rarity.value,
        stats=CardStatsResponse(
            matches=card.stats.matches,
            wins=card.stats.wins,
            losses=card.stats.losses,
            win_rate=card.stats.win_rate,
            current_streak=card.stats.current_streak,
            best_streak=card.stats.best_streak,
            total_xp=card.stats.total_xp,
            achievement_count=card.stats.achievement_count,
            traits_unlocked=card.stats.traits_unlocked,
            calibration_score=card.stats.calibration_score,
        ),
        trait_icons=card.trait_icons,
        achievement_badges=card.achievement_badges,
        card_version=card.card_version,
    )


@router.get("/competitors/{competitor_id}/missions", response_model=MissionsResponse)
async def get_missions(
    request: Request,
    competitor_id: str,
    _: str = Depends(verify_api_key),
    asset: str = Query("BTC"),
    mission_type: str | None = Query(None),
):
    store = _get_store(request)
    from competition.models import MissionType as MissionTypeEnum

    mtype = None
    if mission_type:
        try:
            mtype = MissionTypeEnum(mission_type)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid mission type: {mission_type}"
            )

    missions = await store.get_missions(competitor_id, mtype)
    return MissionsResponse(missions=missions)


@router.post(
    "/competitors/{competitor_id}/missions/{mission_id}/claim",
    response_model=ClaimMissionResponse,
    dependencies=[Depends(check_kill_switch)]
)
@audit_event("competition.mission.claim")
async def claim_mission(
    request: Request,
    competitor_id: str,
    mission_id: str,
    _: str = Depends(verify_api_key),
    asset: str = Query("BTC"),
):
    store = _get_store(request)
    from competition.models import MissionId as MissionIdEnum

    try:
        mid = MissionIdEnum(mission_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid mission ID: {mission_id}")

    success, xp_awarded = await store.claim_mission_reward(competitor_id, mid, asset)

    if not success:
        raise HTTPException(status_code=400, detail="Mission not claimable")

    return ClaimMissionResponse(
        success=True,
        xp_awarded=xp_awarded,
        message=f"Claimed {xp_awarded} XP!",
    )


@router.get("/seasons", response_model=SeasonsResponse)
async def get_seasons(
    request: Request,
    _: str = Depends(verify_api_key),
):
    store = _get_store(request)
    current, seasons = await store.get_seasons()

    return SeasonsResponse(
        current=SeasonResponse(
            id=current.id,
            number=current.number,
            name=current.name,
            status=current.status.value,
            started_at=current.started_at.isoformat(),
            ends_at=current.ends_at.isoformat(),
            days_remaining=current.days_remaining,
            total_participants=current.total_participants,
            your_rank=current.your_rank,
            your_rating=current.your_rating,
        )
        if current
        else None,
        seasons=[
            SeasonResponse(
                id=s.id,
                number=s.number,
                name=s.name,
                status=s.status.value,
                started_at=s.started_at.isoformat(),
                ends_at=s.ends_at.isoformat(),
                days_remaining=s.days_remaining,
                total_participants=s.total_participants,
                your_rank=s.your_rank,
                your_rating=s.your_rating,
            )
            for s in seasons
        ],
    )


@router.get(
    "/seasons/{season_id}/leaderboard", response_model=SeasonLeaderboardResponse
)
async def get_season_leaderboard(
    request: Request,
    season_id: str,
    _: str = Depends(verify_api_key),
    limit: int = Query(50, ge=1, le=100),
):
    store = _get_store(request)
    leaderboard = await store.get_season_leaderboard(season_id, limit)

    return SeasonLeaderboardResponse(
        season_id=leaderboard.season_id,
        leaderboard=[
            SeasonLeaderboardEntry(
                rank=e.rank,
                competitor_id=e.competitor_id,
                name=e.name,
                elo=e.elo,
                tier=e.tier.value,
                matches=e.matches,
            )
            for e in leaderboard.leaderboard
        ],
    )


@router.get("/fleet", response_model=FleetResponse)
async def get_fleet(
    request: Request,
    _: str = Depends(verify_api_key),
    asset: str = Query("BTC"),
):
    store = _get_store(request)
    data = await store.get_fleet(asset)

    return FleetResponse(**data)


@router.get("/matches/{match_id}/pool", response_model=PoolResponse)
async def get_betting_pool(
    request: Request,
    match_id: str,
    _: str = Depends(verify_api_key),
):
    store = _get_store(request)
    pool = await store.get_betting_pool(match_id)

    return PoolResponse(
        match_id=pool.match_id,
        total_pool=pool.total_pool,
        competitor_a_pool=pool.competitor_a_pool,
        competitor_b_pool=pool.competitor_b_pool,
        competitor_a_bettors=pool.competitor_a_bettors,
        competitor_b_bettors=pool.competitor_bettors,
        competitor_a_odds=pool.competitor_a_odds,
        competitor_b_odds=pool.competitor_b_odds,
        status=pool.status.value,
    )


@router.post(
    "/matches/{match_id}/bet", 
    response_model=BetResponse,
    dependencies=[Depends(check_kill_switch)]
)
@audit_event("competition.bet.place")
async def place_bet(
    request: Request,
    match_id: str,
    bet: BetPlacement,
    _: str = Depends(verify_api_key),
):
    store = _get_store(request)

    match = await store.get_match(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    try:
        result = await store.place_bet(
            match_id=match_id,
            better_id="spectator",
            predicted_winner=bet.predicted_winner,
            amount=bet.amount,
            competitor_a=match.competitor_a_id,
            competitor_b=match.competitor_b_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return BetResponse(
        id=result.id,
        match_id=result.match_id,
        predicted_winner=result.predicted_winner,
        amount=result.amount,
        potential_payout=result.potential_payout,
        status=result.status.value,
        created_at=result.created_at.isoformat() if result.created_at else "",
    )


@router.get("/matches/{match_id}/bets", response_model=list[BetResponse])
async def get_match_bets(
    request: Request,
    match_id: str,
    _: str = Depends(verify_api_key),
):
    store = _get_store(request)
    bets = await store.get_match_bets(match_id)

    return [
        BetResponse(
            id=b.id,
            match_id=b.match_id,
            predicted_winner=b.predicted_winner,
            amount=b.amount,
            potential_payout=b.potential_payout,
            status=b.status.value,
            created_at=b.created_at.isoformat() if b.created_at else "",
        )
        for b in bets
    ]


@router.post(
    "/matches/{match_id}/settle", 
    response_model=BetResultResponse,
    dependencies=[Depends(check_kill_switch)]
)
@audit_event("competition.settle")
async def settle_match(
    request: Request,
    match_id: str,
    winner_id: str = Query(...),
    _: str = Depends(verify_api_key),
):
    store = _get_store(request)

    try:
        result = await store.settle_match_bets(match_id, winner_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return BetResultResponse(
        match_id=result.match_id,
        winner=result.winner,
        total_pool=result.total_pool,
        house_cut=result.house_cut,
        distributed=result.distributed,
        settled_bets=result.settled_bets,
    )


@router.get(
    "/competitors/{competitor_id}/mutations", response_model=list[MutationResponse]
)
async def get_mutations(
    request: Request,
    competitor_id: str,
    _: str = Depends(verify_api_key),
):
    store = _get_store(request)
    mutations = await store.get_mutations(competitor_id)

    return [
        MutationResponse(
            id=m.id,
            trait=m.trait.value,
            rarity=m.rarity.value,
            bonus_multiplier=m.bonus_multiplier,
            level_obtained=m.level_obtained,
        )
        for m in mutations
    ]


@router.get("/competitors/{competitor_id}/lineage", response_model=LineageResponse)
async def get_lineage(
    request: Request,
    competitor_id: str,
    _: str = Depends(verify_api_key),
):
    store = _get_store(request)
    lineage = await store.get_lineage(competitor_id)
    mutations = await store.get_mutations(competitor_id)
    can_breed = await store.can_breed(competitor_id)

    if not lineage:
        return LineageResponse(
            agent_id=competitor_id,
            parent_a_id=None,
            parent_b_id=None,
            generation=0,
            breeding_count=0,
            can_breed=can_breed,
            mutations=[
                MutationResponse(
                    id=m.id,
                    trait=m.trait.value,
                    rarity=m.rarity.value,
                    bonus_multiplier=m.bonus_multiplier,
                    level_obtained=m.level_obtained,
                )
                for m in mutations
            ],
        )

    return LineageResponse(
        agent_id=competitor_id,
        parent_a_id=lineage.parent_a_id,
        parent_b_id=lineage.parent_b_id,
        generation=lineage.generation,
        breeding_count=lineage.breeding_count,
        can_breed=can_breed,
        mutations=[
            MutationResponse(
                id=m.id,
                trait=m.trait.value,
                rarity=m.rarity.value,
                bonus_multiplier=m.bonus_multiplier,
                level_obtained=m.level_obtained,
            )
            for m in mutations
        ],
    )


@router.post(
    "/breed", 
    response_model=BreedResultResponse,
    dependencies=[Depends(check_kill_switch)]
)
@audit_event("competition.breed")
async def breed_agents(
    request: Request,
    breed: BreedRequest,
    _: str = Depends(verify_api_key),
):
    store = _get_store(request)

    try:
        result = await store.breed_agents(
            breed.parent_a_id,
            breed.parent_b_id,
            breed.child_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return BreedResultResponse(
        child_id=result.child_id,
        child_name=result.child_name,
        inherited_traits=[t.value for t in result.inherited_traits],
        mutated_trait=result.mutated_trait.value if result.mutated_trait else None,
        mutation_rarity=result.mutation_rarity.value
        if result.mutation_rarity
        else None,
        generation=result.generation,
    )
