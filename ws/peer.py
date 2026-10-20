from fastapi import WebSocket, WebSocketDisconnect
from webfluid.utils.logging import factory as log_factory
from datetime import datetime, UTC
import asyncio, json, secrets, time

from wf_peering.protocol import entries
from wf_peering.protocol.handshake import HELLO_CONTEXT, AUTH_CONTEXT, WELCOME_CONTEXT, MAX_BATCH_BYTES
from wf_peering.protocol.signing import verify, fingerprint, valid_ed25519, b64encode
from wf_peering.services.identity import NodeIdentity
from wf_peering.services.journal import Journal
from wf_peering.services.ledger import Ledger
from wf_peering.services.peers import Peers, verify_claim
from wf_peering.settings import settings, PROTOCOL_VERSION, SCHEMA_VERSION

MAX_MESSAGE = 64 * 1024
FAILURE_WINDOW = 600
FAILURE_LIMIT = 10

_active: dict[int, str] = {}
_failures: dict[str, list[float]] = {}


def _blocked(address: str | None) -> bool:
    if not address: return False
    now = time.monotonic()
    recent = [moment for moment in _failures.get(address, []) if now - moment < FAILURE_WINDOW]
    _failures[address] = recent
    return len(recent) >= FAILURE_LIMIT


def _failed(address: str | None):
    if address: _failures.setdefault(address, []).append(time.monotonic())
    if len(_failures) > 4096:
        for key in list(_failures)[:1024]: _failures.pop(key, None)


async def _reject(websocket: WebSocket, address: str | None, code: str):
    _failed(address)
    await Peers.rejected(address, code)
    try:
        await websocket.send_text(json.dumps({ "type": "error", "code": code }))
        await websocket.close(code=1008)
    except Exception: pass


def _fresh(ts) -> bool:
    try: moment = entries.parse_ts(ts)
    except ValueError: return False
    return abs((datetime.now(UTC) - moment).total_seconds()) <= 300


async def _receive(websocket: WebSocket, timeout: float) -> dict | None:
    raw = await asyncio.wait_for(websocket.receive_text(), timeout=timeout)
    if len(raw) > MAX_MESSAGE: return None
    try: message = json.loads(raw)
    except ValueError: return None
    return message if isinstance(message, dict) else None


async def handle_socket(websocket: WebSocket):
    address = websocket.client.host if websocket.client else None
    if not settings.is_host:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    if _blocked(address): return await _reject(websocket, address, "TOO_MANY_FAILURES")
    if len(_active) >= settings.max_peers: return await _reject(websocket, address, "TOO_MANY_PEERS")

    challenge = b64encode(secrets.token_bytes(24))
    hello = {
        "node": NodeIdentity.node_id(), "key": NodeIdentity.public_key(), "origin": settings.origin,
        "challenge": challenge, "protocol": PROTOCOL_VERSION, "schema": SCHEMA_VERSION,
        "boot": NodeIdentity.boot_id, "ts": entries.utc_now()
    }
    await websocket.send_text(json.dumps({
        "type": "hello", "statement": hello, "signature": NodeIdentity.sign(HELLO_CONTEXT, hello),
        "head": await Ledger.signed_head()
    }))

    try: message = await _receive(websocket, settings.timeout)
    except (asyncio.TimeoutError, WebSocketDisconnect): return await _reject(websocket, address, "AUTH_TIMEOUT")
    statement = (message or {}).get("statement") or {}
    key = statement.get("key")
    if (message or {}).get("type") != "auth" or not valid_ed25519(key) or statement.get("node") != fingerprint(key):
        return await _reject(websocket, address, "INVALID_AUTH")
    if statement.get("challenge") != challenge or not _fresh(statement.get("ts")):
        return await _reject(websocket, address, "STALE_AUTH")
    if statement.get("protocol") != PROTOCOL_VERSION or statement.get("schema") != SCHEMA_VERSION:
        return await _reject(websocket, address, "PROTOCOL_MISMATCH")
    if not verify(key, AUTH_CONTEXT, statement, message.get("signature") or ""):
        return await _reject(websocket, address, "INVALID_SIGNATURE")
    if statement.get("node") == NodeIdentity.node_id():
        return await _reject(websocket, address, "SELF_CONNECTION")

    node = statement["node"]
    url = str(statement.get("url") or "")
    refusal = await verify_claim(url, node)
    if refusal: return await _reject(websocket, address, refusal)
    error, connection_id = await Peers.authenticated(node, key, url, address)
    if error: return await _reject(websocket, address, error)

    welcome = { "nonce": statement.get("nonce"), "node": node, "host": NodeIdentity.node_id(), "ts": entries.utc_now() }
    await websocket.send_text(json.dumps({
        "type": "welcome", "statement": welcome, "signature": NodeIdentity.sign(WELCOME_CONTEXT, welcome)
    }))
    await Journal.append("peering:peer-connected", { "node": node, "url": statement.get("url") })

    queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
    stalled = { "value": False }

    def listener(entry: dict):
        if stalled["value"]: return
        try: queue.put_nowait({ k: entry[k] for k in ("seq", "hash", "content", "signature") })
        except asyncio.QueueFull:
            stalled["value"] = True
            asyncio.ensure_future(websocket.close(code=1013))

    async def forward():
        while True:
            entry = await queue.get()
            await websocket.send_text(json.dumps({ "type": "entry", "entry": entry }))

    Ledger.subscribe(listener)
    _active[connection_id] = node
    sender = asyncio.create_task(forward())
    reason = "CLOSED"
    try:
        while True:
            try: message = await _receive(websocket, settings.heartbeat_interval * 4)
            except asyncio.TimeoutError:
                reason = "HEARTBEAT_TIMEOUT"
                break
            if message is None: continue
            kind = message.get("type")
            if kind == "heartbeat":
                head = message.get("head") or {}
                await Peers.heartbeat(node, head.get("seq"), head.get("hash"))
                seq, value = await Ledger.head()
                await websocket.send_text(json.dumps({
                    "type": "heartbeat", "head": { "seq": seq, "hash": value }, "ts": entries.utc_now()
                }))
            elif kind == "range":
                start = message.get("from")
                limit = message.get("limit")
                if not isinstance(start, int) or start < 1: continue
                limit = max(1, min(limit if isinstance(limit, int) else settings.ledger_page, settings.ledger_page))
                items, size = [], 0
                for item in await Ledger.range(start, limit):
                    payload = { k: item[k] for k in ("seq", "hash", "content", "signature") }
                    size += len(json.dumps(payload))
                    if items and size > MAX_BATCH_BYTES: break
                    items.append(payload)
                seq, _ = await Ledger.head()
                last = items[-1]["seq"] if items else start - 1
                await websocket.send_text(json.dumps({ "type": "entries", "entries": items, "more": last < seq }))
            elif kind == "checkpoint":
                from wf_peering.services.checkpoints import Checkpoints
                await Checkpoints.remember_remote(message, via="peer-push")
    except WebSocketDisconnect:
        reason = "BACKPRESSURE" if stalled["value"] else "DISCONNECTED"
    except Exception as exc:
        reason = type(exc).__name__
        log_factory.exception(exc, f"[peering] The connection to peer {node} failed.")
    finally:
        sender.cancel()
        Ledger.unsubscribe(listener)
        _active.pop(connection_id, None)
        await Peers.disconnected(node, connection_id, reason, node in _active.values())
        await Journal.append("peering:peer-disconnected", { "node": node, "reason": reason })


def active() -> list[str]:
    return sorted(set(_active.values()))


def live_connections() -> set[int]:
    return set(_active)
