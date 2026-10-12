from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from webfluid import Additive


def setup(a: "Additive"):
    from .peer import handle_socket as handle_peer
    a.ws.websocket("/peer")(handle_peer)
