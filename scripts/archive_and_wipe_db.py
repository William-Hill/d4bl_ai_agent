"""
Archive and wipe database for fresh testing.

This script:
1. Exports current data to CSV files (optional backup)
2. Clears all data from research_jobs and evaluation_results tables
3. Optionally clears Phoenix traces (requires manual confirmation)

Usage:
    python scripts/archive_and_wipe_db.py [--no-archive] [--yes]
    
    --no-archive: Skip CSV export
    --yes: Skip confirmation prompt (useful for Docker/automation)
"""
import asyncio
import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sqlalchemy import text, select
from d4bl.infra import database as db
from d4bl.infra.database import ResearchJob, EvaluationResult


async def export_data_to_csv():
    """Export current data to CSV files for backup"""
    print("📦 Exporting current data to CSV files...")
    
    if db.async_session_maker is None:
        db.init_db()
    
    archive_dir = project_root / "archive"
    archive_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    try:
        async with db.async_session_maker() as session:
            # Export research_jobs
            result = await session.execute(select(ResearchJob))
            jobs = result.scalars().all()
            
            if jobs:
                jobs_file = archive_dir / f"research_jobs_{timestamp}.csv"
                with open(jobs_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=[
                        'job_id', 'query', 'summary_format', 'status', 'progress',
                        'error', 'created_at', 'updated_at', 'completed_at'
                    ])
                    writer.writeheader()
                    for job in jobs:
                        writer.writerow({
                            'job_id': str(job.job_id),
                            'query': job.query,
                            'summary_format': job.summary_format,
                            'status': job.status,
                            'progress': job.progress,
                            'error': job.error,
                            'created_at': job.created_at.isoformat() if job.created_at else None,
                            'updated_at': job.updated_at.isoformat() if job.updated_at else None,
                            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                        })
                print(f"✅ Exported {len(jobs)} research jobs to {jobs_file}")
            else:
                print("ℹ️  No research jobs to export")
            
            # Export evaluation_results
            result = await session.execute(select(EvaluationResult))
            evals = result.scalars().all()
            
            if evals:
                evals_file = archive_dir / f"evaluation_results_{timestamp}.csv"
                with open(evals_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=[
                        'id', 'span_id', 'trace_id', 'job_id', 'eval_name',
                        'label', 'score', 'explanation', 'created_at'
                    ])
                    writer.writeheader()
                    for eval_result in evals:
                        writer.writerow({
                            'id': str(eval_result.id),
                            'span_id': eval_result.span_id,
                            'trace_id': eval_result.trace_id,
                            'job_id': str(eval_result.job_id) if eval_result.job_id else None,
                            'eval_name': eval_result.eval_name,
                            'label': eval_result.label,
                            'score': eval_result.score,
                            'explanation': eval_result.explanation,
                            'created_at': eval_result.created_at.isoformat() if eval_result.created_at else None,
                        })
                print(f"✅ Exported {len(evals)} evaluation results to {evals_file}")
            else:
                print("ℹ️  No evaluation results to export")
    
    except Exception as e:
        print(f"⚠️  Error exporting data: {e}")
        import traceback
        traceback.print_exc()


async def wipe_database():
    """Clear all data from research_jobs and evaluation_results tables"""
    print("\n🗑️  Wiping database...")
    
    if db.async_session_maker is None:
        db.init_db()
    
    try:
        async with db.engine.begin() as conn:
            # Delete evaluation_results first (due to foreign key constraint)
            delete_evals = text("DELETE FROM evaluation_results")
            result = await conn.execute(delete_evals)
            print(f"✅ Deleted {result.rowcount} evaluation results")
            
            # Delete research_jobs
            delete_jobs = text("DELETE FROM research_jobs")
            result = await conn.execute(delete_jobs)
            print(f"✅ Deleted {result.rowcount} research jobs")
            
            # Reset sequences (optional, but good for clean state)
            reset_evals_seq = text("ALTER SEQUENCE IF EXISTS evaluation_results_id_seq RESTART WITH 1")
            await conn.execute(reset_evals_seq)
            
            print("\n✅ Database wiped successfully!")
            print("   You can now run fresh jobs and evaluations.")
    
    except Exception as e:
        print(f"❌ Error wiping database: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


async def main(no_archive=False, skip_confirm=False):
    """Main function"""
    print("=" * 60)
    print("Database Archive and Wipe Script")
    print("=" * 60)
    print()
    
    # Step 1: Export data (unless --no-archive)
    if not no_archive:
        await export_data_to_csv()
    else:
        print("⏭️  Skipping data export (--no-archive flag)")
    
    # Step 2: Confirm wipe (unless --yes)
    if not skip_confirm:
        print("\n" + "=" * 60)
        print("⚠️  WARNING: This will DELETE ALL DATA from:")
        print("   - research_jobs table")
        print("   - evaluation_results table")
        print("=" * 60)
        print()
        
        response = input("Type 'YES' to confirm database wipe: ").strip()
        if response != 'YES':
            print("❌ Database wipe cancelled.")
            return False
    else:
        print("\n⚠️  WARNING: Deleting ALL DATA from database (--yes flag used)")
    
    # Step 3: Wipe database
    success = await wipe_database()
    
    if success:
        print("\n" + "=" * 60)
        print("✅ Database cleanup complete!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Run a new research job through the frontend")
        print("2. Run evaluations: docker compose exec d4bl-api python /app/scripts/run_evals.py")
        print("3. Check that evaluations are linked to the job in the frontend")
        return True
    else:
        print("\n❌ Database wipe failed. Check errors above.")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Archive and wipe database for fresh testing")
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Skip CSV export of existing data"
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt (useful for Docker/automation)"
    )
    
    args = parser.parse_args()
    
    success = asyncio.run(main(no_archive=args.no_archive, skip_confirm=args.yes))
    sys.exit(0 if success else 1)

