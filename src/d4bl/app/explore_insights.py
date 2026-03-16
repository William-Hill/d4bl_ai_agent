"""Explore insights endpoints — state-level summary with rank, percentile, racial gap."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from litellm import acompletion
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.app.auth import CurrentUser, get_current_user
from d4bl.app.schemas import (
    ExplainRequest,
    ExplainResponse,
    ExploreQueryRequest,
    ExploreQueryResponse,
    RacialGap,
    RacialGapGroup,
    StateSummaryInsight,
)
from d4bl.infra.database import get_db
from d4bl.infra.state_summary import StateSummary
from d4bl.query.engine import QueryEngine
from d4bl.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/explore", tags=["explore-insights"])

# ---------------------------------------------------------------------------
# Lazy-loaded QueryEngine singleton
# ---------------------------------------------------------------------------
_query_engine: QueryEngine | None = None


def _get_query_engine() -> QueryEngine:
    global _query_engine
    if _query_engine is None:
        _query_engine = QueryEngine()
    return _query_engine


@router.post("/query", response_model=ExploreQueryResponse)
async def explore_query(
    request: ExploreQueryRequest,
    _user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExploreQueryResponse:
    """Answer a natural-language question using the current explore context."""
    ctx = request.context
    context_parts = [f"Data source: {ctx.source}"]
    if ctx.metric:
        context_parts.append(f"Metric: {ctx.metric}")
    if ctx.state_fips:
        context_parts.append(f"State FIPS: {ctx.state_fips}")
    if ctx.race:
        context_parts.append(f"Race filter: {ctx.race}")
    if ctx.year:
        context_parts.append(f"Year: {ctx.year}")

    augmented = (
        f"Context: {', '.join(context_parts)}. "
        f"Question: {request.question}"
    )

    try:
        engine = _get_query_engine()
        result = await engine.query(db=db, question=augmented)
        return ExploreQueryResponse(
            answer=result.answer,
            data=None,
            visualization_hint=None,
        )
    except Exception as exc:
        logger.error("Explore query failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Query failed — the AI service may be unavailable",
        )


@router.get("/state-summary", response_model=StateSummaryInsight)
async def get_state_summary(
    source: str = Query(..., description="Data source key, e.g. 'census'"),
    state_fips: str = Query(..., description="Two-digit FIPS code"),
    metric: str = Query(..., description="Metric name"),
    year: int | None = Query(None, description="Optional year filter"),
    _user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StateSummaryInsight:
    """Return pre-computed stats for a state: rank, percentile, racial gap."""

    # ------------------------------------------------------------------
    # 1. Query all states for this source + metric + race="total"
    # ------------------------------------------------------------------
    q = select(StateSummary).where(
        StateSummary.source == source,
        StateSummary.metric == metric,
        StateSummary.race == "total",
    )
    if year is not None:
        q = q.where(StateSummary.year == year)

    result = await db.execute(q)
    all_rows = result.scalars().all()

    if not all_rows:
        raise HTTPException(
            status_code=404,
            detail=f"No data for source={source}, metric={metric}",
        )

    # ------------------------------------------------------------------
    # 2. Find target state (use latest year if multiple)
    # ------------------------------------------------------------------
    target_rows = [r for r in all_rows if r.state_fips == state_fips]
    if not target_rows:
        raise HTTPException(
            status_code=404,
            detail=f"No data for state_fips={state_fips}",
        )

    # Pick the latest year available for this state
    target = max(target_rows, key=lambda r: r.year)
    resolved_year = target.year

    # Filter all_rows to the same year for ranking
    year_rows = [r for r in all_rows if r.year == resolved_year]

    # ------------------------------------------------------------------
    # 3. Compute rank, percentile, national average
    # ------------------------------------------------------------------
    values = [r.value for r in year_rows]
    national_average = round(sum(values) / len(values), 4) if values else 0.0

    # Rank: descending (highest value = rank 1)
    sorted_desc = sorted(year_rows, key=lambda r: r.value, reverse=True)
    rank = next(
        (i + 1 for i, r in enumerate(sorted_desc) if r.state_fips == state_fips),
        len(sorted_desc),
    )
    total_states = len(sorted_desc)

    # Percentile: % of states with value <= this state's value
    states_at_or_below = sum(1 for r in year_rows if r.value <= target.value)
    percentile = round(states_at_or_below / total_states * 100, 1)

    # ------------------------------------------------------------------
    # 4. Query race data for racial gap
    # ------------------------------------------------------------------
    rq = select(StateSummary).where(
        StateSummary.source == source,
        StateSummary.metric == metric,
        StateSummary.state_fips == state_fips,
        StateSummary.year == resolved_year,
        StateSummary.race != "total",
    )
    race_result = await db.execute(rq)
    race_rows = race_result.scalars().all()

    racial_gap: RacialGap | None = None
    if race_rows:
        groups = [
            RacialGapGroup(race=r.race, value=round(r.value, 4))
            for r in race_rows
        ]
        min_val = min(r.value for r in race_rows)
        max_val = max(r.value for r in race_rows)
        max_race = next(r.race for r in race_rows if r.value == max_val)
        min_race = next(r.race for r in race_rows if r.value == min_val)

        max_ratio = round(max_val / min_val, 2) if min_val > 0 else 0.0
        max_ratio_label = f"{max_race} vs {min_race}"

        racial_gap = RacialGap(
            groups=groups,
            max_ratio=max_ratio,
            max_ratio_label=max_ratio_label,
        )

    return StateSummaryInsight(
        state_fips=target.state_fips,
        state_name=target.state_name,
        metric=target.metric,
        value=round(target.value, 4),
        national_average=national_average,
        national_rank=rank,
        national_rank_total=total_states,
        percentile=percentile,
        racial_gap=racial_gap,
        year=resolved_year,
        source=source,
    )


_SYSTEM_PROMPT = (
    "You are a racial equity data analyst writing for policy researchers. "
    "You explain socioeconomic indicators clearly, noting disparities and "
    "structural context. Respond ONLY with valid JSON containing keys: "
    '"narrative" (str), "methodology_note" (str), "caveats" (list[str]).'
)


def _build_user_prompt(req: ExplainRequest) -> str:
    """Build a structured user prompt from the explain request."""
    gap_text = ""
    if req.racial_gap:
        groups = ", ".join(
            f"{g.race}: {g.value}" for g in req.racial_gap.groups
        )
        gap_text = (
            f"\nRacial breakdown: {groups}"
            f"\nMax disparity ratio: {req.racial_gap.max_ratio}"
            f" ({req.racial_gap.max_ratio_label})"
        )

    return (
        f"Data source: {req.source}\n"
        f"Metric: {req.metric}\n"
        f"State: {req.state_name} (FIPS {req.state_fips})\n"
        f"Value: {req.value}\n"
        f"National average: {req.national_average}\n"
        f"Year: {req.year}"
        f"{gap_text}\n\n"
        "Provide a concise narrative explaining what this data means for "
        "racial equity in this state, a brief methodology note about this "
        "metric, and a list of caveats researchers should keep in mind."
    )


@router.post("/explain", response_model=ExplainResponse)
async def explain_view(
    req: ExplainRequest,
    _user: CurrentUser = Depends(get_current_user),
) -> ExplainResponse:
    """Generate an LLM-powered narrative explanation for the current view."""

    settings = get_settings()
    model = f"ollama/{settings.ollama_model}"

    try:
        response = await acompletion(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(req)},
            ],
            max_tokens=500,
            temperature=0.3,
            timeout=30,
            api_base=settings.ollama_base_url,
        )
    except Exception:
        logger.exception("LLM call failed for /api/explore/explain")
        raise HTTPException(
            status_code=503,
            detail="AI analysis unavailable — Ollama may be down",
        )

    try:
        raw = response.choices[0].message.content or ""
    except (AttributeError, IndexError, TypeError):
        raw = ""

    # Try to parse as JSON; fall back to raw text as narrative
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise TypeError("LLM returned non-dict JSON")
        narrative = parsed.get("narrative", raw)
        methodology_note = parsed.get("methodology_note", "")
        caveats = parsed.get("caveats", [])
        if not isinstance(caveats, list):
            caveats = [str(caveats)]
    except (json.JSONDecodeError, AttributeError, TypeError):
        narrative = raw or "No analysis available."
        methodology_note = ""
        caveats = []

    return ExplainResponse(
        narrative=narrative,
        methodology_note=methodology_note,
        caveats=caveats,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
