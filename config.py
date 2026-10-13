from webfluid.core.config import register_config

try: from ._my_config import MyConfig
except ImportError:
    class MyConfig: pass


class DefaultConfig:
    PEERING_PUBLIC_URL = None
    PEERING_KEY_FILE = "keys/node.key"
    PEERING_PEERS = []
    PEERING_ALLOW_INSECURE = False
    PEERING_MAX_PEERS = 64
    PEERING_PEER_INACTIVE_DAYS = 30
    PEERING_REGISTRATIONS_PER_HOUR = 20
    PEERING_SCHEDULE = True
    PEERING_CHECKPOINT_TIME = (0, 0)
    PEERING_INTEGRITY_INTERVAL = 900
    PEERING_MODELS_DB_BIND = None


@register_config()
class Config(MyConfig, DefaultConfig): pass
