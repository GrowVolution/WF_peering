from webfluid.core.ext import events
from webfluid.utils.logging import factory as log_factory
from datetime import datetime

from wf_peering import NodeRole, __version__
from wf_peering.protocol.entries import utc_now
from wf_peering.services.identity import NodeIdentity
from wf_peering.services.ledger import Ledger
from wf_peering.services.store import State
from wf_peering.settings import settings


class HostRole(NodeRole):
    name = "host"

    @property
    def software(self) -> str:
        from .. import additive
        return f"peering/{additive.version} wf-peering/{__version__}"

    async def startup(self) -> None:
        size, _ = await Ledger.head()
        if size == 0:
            await Ledger.append("peering:genesis", "peering", {
                "node": NodeIdentity.node_id(), "key": NodeIdentity.public_key(), "origin": settings.origin,
                "created_at": utc_now()
            }, subject="host", ref=f"genesis:{NodeIdentity.node_id()}")
        await Ledger.append("peering:restart", "peering", {
            "boot": NodeIdentity.boot_id, "started_at": NodeIdentity.started_at,
            "key": NodeIdentity.public_key()
        }, subject="host", ref=f"restart:{NodeIdentity.boot_id}")
        from .aggregation import run
        await run("startup")

    async def discover(self) -> None:
        await State.set("host_check", await State.get("self_check"))

    async def checkpoint_basis(self, day: str, moment: datetime) -> tuple[int, str, dict]:
        size, _ = await Ledger.head()
        report = await Ledger.verify(NodeIdentity.public_key(), size)
        status = "verified" if report["valid"] else "failed"
        return size, status, { "status": "self", "id": None, "finished_at": None, "to_seq": size,
                               "problems": report["problems"][:10] }

    async def publish_checkpoint(self, signed: dict) -> None:
        day = signed["checkpoint"]["day"]
        await Ledger.append("peering:checkpoint", "peering", signed, subject=f"checkpoint:{day}",
                            ref=f"checkpoint:{NodeIdentity.node_id()}:{day}")

    async def status(self) -> dict:
        from ..ws.peer import active
        return { "connected_peers": active() }

    def live_connections(self) -> set[int]:
        from ..ws.peer import live_connections
        return live_connections()

    def alert(self, data: dict) -> None:
        from .. import additive
        try: events.trigger(additive.unique_name("alert"), data)
        except ValueError: pass
        except Exception as exc: log_factory.exception(exc, "[peering] The alert signal failed.")
