"""
Scheduler Admin Endpoints (dev/debug only)
---------------------------------------------
GET  /api/v1/scheduler/status         → see registered jobs and next run times
POST /api/v1/scheduler/trigger/{job}  → manually fire a job right now (skip the wait)

Useful while developing: trigger 'publish_due_posts' immediately after scheduling
a test post instead of waiting up to 60 seconds for the next tick.

These are NOT scoped to a specific user — they operate on the scheduler itself.
In production, you may want to restrict these behind an admin-only check.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import get_current_active_user
from app.models.user import User
from app.core.scheduler import scheduler
from app.services.scheduler_jobs import publish_due_posts, refresh_expiring_tokens

router = APIRouter(prefix="/scheduler", tags=["scheduler"])

_MANUAL_JOBS = {
    "publish_due_posts": publish_due_posts,
    "refresh_expiring_tokens": refresh_expiring_tokens,
}


@router.get("/status")
async def scheduler_status(
    current_user: User = Depends(get_current_active_user),
):
    """List all registered background jobs and their next scheduled run time."""
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
        })
    return {"running": scheduler.running, "jobs": jobs}


@router.post("/trigger/{job_id}")
async def trigger_job(
    job_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """
    Manually run a job immediately, outside its normal schedule.
    Valid job_id values: 'publish_due_posts', 'refresh_expiring_tokens'
    """
    job_func = _MANUAL_JOBS.get(job_id)
    if not job_func:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown job '{job_id}'. Valid options: {list(_MANUAL_JOBS.keys())}",
        )

    await job_func()
    return {"status": "triggered", "job_id": job_id}
