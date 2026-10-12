from webfluid import Additive, Fluid
from pathlib import Path

additive = Additive(
    __name__,
	required_extensions=[
		"sqlalchemy",
		"events",
        "scheduling",
        "babel"
	]
)


@additive.before_enable
def before_enable(fluid: Fluid):
    from webfluid.utils.logging import factory as log_factory
    if fluid.config.get("PEERING_ROLE") not in (None, "host"):
        log_factory.warning("[peering] PEERING_ROLE is ignored: the peering Additive is always the host. "
                            "Peers run the peering app.")

    try: from wf_peering import peering
    except ImportError as exc:
        from webfluid.exceptions import FrameworkException
        raise FrameworkException(
            "The peering Additive needs the wf-peering extension: "
            "install it with `pip install wf-peering`."
        ) from exc
    from .services.role import HostRole
    peering.expand_fluid(fluid, role=HostRole(), root=Path(__file__).resolve().parent)

    from .api import setup_v1, health
    additive.api.get("/health")(health)
    setup_v1(additive, fluid)

    from .ws import setup as setup_ws
    setup_ws(additive)

    from .app import index
    additive.app.get("/")(index)

    from .events import setup as setup_events
    setup_events()

    from wf_peering.services.settings import settings
    if settings.schedule:
        from .jobs import setup as setup_jobs
        setup_jobs()
