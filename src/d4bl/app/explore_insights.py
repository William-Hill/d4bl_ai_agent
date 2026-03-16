"""Explore insights endpoints — state-level summary with rank, percentile, racial gap."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.app.auth import CurrentUser, get_current_user
from d4bl.app.schemas import RacialGap, RacialGapGroup, StateSummaryInsight
from d4bl.infra.database import get_db
from d4bl.infra.state_summary import StateSummary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/explore", tags=["explore-insights"])


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
