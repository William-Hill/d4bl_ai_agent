"""Flywheel metrics admin endpoint.

Aggregates corpus diversity, model accuracy, and research quality
metrics for the D4BL data flywheel dashboard.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from d4bl.app.auth import require_admin
from d4bl.app.schemas import (
    CorpusStats,
    FlywheelMetricsResponse,
    ResearchQualityItem,
    TimeSeriesPoint,
    TrainingRunItem,
)
from d4bl.infra.database import get_db

router = APIRouter()


async def _query_corpus(db: AsyncSession) -> tuple[dict[str, int], int, int]:
    result = await db.execute(
        text("""
            SELECT d.content_type,
                   COUNT(dc.id) AS chunk_count,
                   COALESCE(SUM(dc.token_count), 0) AS total_tokens
            FROM document_chunks dc
            JOIN documents d ON dc.document_id = d.id
            GROUP BY d.content_type
            ORDER BY chunk_count DESC
        """)
    )
    rows = result.mappings().all()

    content_types: dict[str, int] = {}
    total_chunks = 0
    total_tokens = 0
    for row in rows:
        content_types[row["content_type"]] = int(row["chunk_count"])
        total_chunks += int(row["chunk_count"])
        total_tokens += int(row["total_tokens"])

    return content_types, total_chunks, total_tokens


async def _query_training_runs(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        text("""
            SELECT model_version, task, metrics, ship_decision, created_at
            FROM model_eval_runs
            ORDER BY created_at DESC
            LIMIT 20
        """)
    )
    return [dict(row) for row in result.mappings().all()]


async def _query_evaluation_results(
    db: AsyncSession,
) -> tuple[dict[str, ResearchQualityItem], list[dict]]:
    """Single scan of evaluation_results returning both per-eval-name aggregates and monthly time-series."""
    result = await db.execute(
        text("""
            SELECT eval_name,
                   DATE_TRUNC('month', created_at) AS month,
                   AVG(score) AS avg_score,
                   COUNT(*) AS eval_count
            FROM evaluation_results
            WHERE score IS NOT NULL
              AND created_at >= NOW() - INTERVAL '24 months'
            GROUP BY eval_name, DATE_TRUNC('month', created_at)
            ORDER BY eval_name, month
        """)
    )
    rows = result.mappings().all()

    # Aggregate per eval_name (sum across months)
    by_name: dict[str, dict] = {}
    monthly: dict[str, list[float]] = {}
    for row in rows:
        name = row["eval_name"]
        avg = float(row["avg_score"])
        count = int(row["eval_count"])
        if name not in by_name:
            by_name[name] = {"total_score": 0.0, "total_count": 0}
        by_name[name]["total_score"] += avg * count
        by_name[name]["total_count"] += count

        month_key = str(row["month"])[:10]
        monthly.setdefault(month_key, []).append(avg * count)
        monthly.setdefault(f"{month_key}_count", []).append(count)

    research_quality = {
        name: ResearchQualityItem(
            avg_score=round(data["total_score"] / data["total_count"], 4),
            count=data["total_count"],
        )
        for name, data in by_name.items()
    }

    # Build monthly averages across all eval types
    month_keys = sorted(k for k in monthly if not k.endswith("_count"))
    timeseries_rows = []
    for mk in month_keys:
        total_score = sum(monthly[mk])
        total_count = sum(monthly[f"{mk}_count"])
        timeseries_rows.append({
            "month": mk,
            "avg_score": total_score / total_count if total_count else 0,
        })

    return research_quality, timeseries_rows


def _build_time_series(
    training_rows: list[dict],
    rq_timeseries_rows: list[dict],
) -> tuple[list[TimeSeriesPoint], list[TimeSeriesPoint], list[TimeSeriesPoint]]:
    """Derive time-series data from training runs and evaluation results."""
    corpus_diversity: list[TimeSeriesPoint] = []
    model_accuracy: list[TimeSeriesPoint] = []

    for run in training_rows:
        metrics = run.get("metrics") or {}
        created = run.get("created_at")
        if not created:
            continue
        date_str = created.strftime("%Y-%m-%d") if hasattr(created, "strftime") else str(created)[:10]

        corpus_stats = metrics.get("corpus_stats", {})
        structured = corpus_stats.get("structured_passages", 0)
        unstructured = corpus_stats.get("unstructured_passages", 0)
        total = structured + unstructured
        if total > 0:
            pct = round(unstructured / total * 100, 1)
            corpus_diversity.append(TimeSeriesPoint(date=date_str, value=pct))

        f1 = metrics.get("entity_f1")
        halluc = metrics.get("hallucination_accuracy")
        community_f1 = metrics.get("community_framing_f1")
        scores = [s for s in [f1, halluc, community_f1] if s is not None]
        if scores:
            composite = round(sum(scores) / len(scores), 4)
            model_accuracy.append(TimeSeriesPoint(date=date_str, value=composite))

    rq_points: list[TimeSeriesPoint] = []
    for row in rq_timeseries_rows:
        date_str = str(row["month"])[:10]
        rq_points.append(
            TimeSeriesPoint(date=date_str, value=round(float(row["avg_score"]), 4))
        )

    # Reverse so oldest is first (training_rows are DESC)
    corpus_diversity.reverse()
    model_accuracy.reverse()

    return corpus_diversity, model_accuracy, rq_points


@router.get("/api/admin/flywheel-metrics", response_model=FlywheelMetricsResponse)
async def get_flywheel_metrics(
    _user=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> FlywheelMetricsResponse:
    """Return aggregated flywheel metrics for the admin dashboard."""
    content_types, total_chunks, total_tokens = await _query_corpus(db)
    training_rows = await _query_training_runs(db)
    research_quality, rq_timeseries_rows = await _query_evaluation_results(db)

    training_items = [
        TrainingRunItem(
            model_version=r["model_version"],
            task=r["task"],
            metrics=r["metrics"] or {},
            ship_decision=r["ship_decision"],
            created_at=r["created_at"].isoformat() if r.get("created_at") else None,
        )
        for r in training_rows
    ]

    corpus_diversity, model_accuracy, rq_points = _build_time_series(
        training_rows, rq_timeseries_rows
    )

    unstructured_pct = corpus_diversity[-1].value if corpus_diversity else 0.0

    return FlywheelMetricsResponse(
        corpus=CorpusStats(
            total_chunks=total_chunks,
            total_tokens=total_tokens,
            content_types=content_types,
            unstructured_pct=unstructured_pct,
        ),
        training_runs=training_items,
        research_quality=research_quality,
        time_series={
            "corpus_diversity": corpus_diversity,
            "model_accuracy": model_accuracy,
            "research_quality": rq_points,
        },
    )
