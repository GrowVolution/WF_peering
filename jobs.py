from webfluid.core.ext import scheduler
from apscheduler.triggers.interval import IntervalTrigger


def setup():
    from wf_peering.services.settings import settings
    from wf_peering.services.tasks import guarded
    from ..services.aggregation import run

    @guarded("integrity")
    async def integrity():
        await run("scheduled")

    scheduler.add_job(integrity, IntervalTrigger(seconds=settings.integrity_interval))
