from webfluid.core.ext import scheduler
from apscheduler.triggers.interval import IntervalTrigger


def setup():
    from wf_peering.settings import settings
    from wf_peering.jobs import guarded
    from .utils.aggregation import run

    @guarded("integrity")
    async def integrity():
        await run("scheduled")

    scheduler.add_job(integrity, IntervalTrigger(seconds=settings.integrity_interval))
