#!/usr/bin/env python3
"""
Create the evaluation_results table if it does not already exist.

Usage:
    python scripts/add_evaluation_results_table.py
"""

import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

# Ensure src directory is on the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from d4bl.infra.database import init_db


async def create_evaluation_results_table():
    print("🔧 Ensuring evaluation_results table exists...")
    try:
        init_db()
        from d4bl.infra.database import engine

        if engine is None:
            print("❌ Database engine not initialized. Check connection settings.")
            return False

        async with engine.begin() as conn:
            # Check if table already exists
            exists_query = text(
                """
                SELECT to_regclass('public.evaluation_results');
                """
            )
            result = await conn.execute(exists_query)
            table_exists = result.scalar() is not None

            if table_exists:
                print("✅ evaluation_results table already exists")
                return True

            create_table = text(
                """
                CREATE TABLE evaluation_results (
                    id UUID PRIMARY KEY,
                    span_id VARCHAR(64) NOT NULL,
                    trace_id VARCHAR(64),
                    eval_name VARCHAR(100) NOT NULL,
                    label VARCHAR(100),
                    score DOUBLE PRECISION,
                    explanation TEXT,
                    input_text TEXT,
                    output_text TEXT,
                    context_text TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            create_idx_span = text(
                "CREATE INDEX idx_evaluation_results_span_id ON evaluation_results(span_id)"
            )
            create_idx_trace = text(
                "CREATE INDEX idx_evaluation_results_trace_id ON evaluation_results(trace_id)"
            )
            create_idx_eval = text(
                "CREATE INDEX idx_evaluation_results_eval_name ON evaluation_results(eval_name)"
            )

            await conn.execute(create_table)
            await conn.execute(create_idx_span)
            await conn.execute(create_idx_trace)
            await conn.execute(create_idx_eval)
            print("✅ Created evaluation_results table")
            return True
    except Exception as exc:
        print(f"❌ Error creating evaluation_results table: {exc}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(create_evaluation_results_table())
    sys.exit(0 if success else 1)


