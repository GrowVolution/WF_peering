from fastapi import APIRouter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from webfluid import Additive, Fluid

v1 = APIRouter(prefix="/v1")


def setup(a: "Additive", f: "Fluid"):
    from wf_peering.api import register, route, connections_request
    register(v1, f.limit)
    route(v1, f.limit, "/peers/connections", "60/minute", connections_request)
    a.api.include_router(v1)
