from .health import handle_request as health
from .v1 import setup as setup_v1

__all__ = [
    "health",
    "setup_v1"
]
