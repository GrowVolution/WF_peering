from pathlib import Path
import hashlib

import wf_peering
from wf_peering.extension import ASSETS, PACKAGE
from wf_peering.protocol import integrity as spec
from wf_peering.protocol.entries import utc_now
from wf_peering.services.integrity import Integrity
from wf_peering.services.ledger import Ledger, LedgerError

_ROOT = Path(__file__).resolve().parent.parent
_SKIP = { "__pycache__", "keys", "tests", ".git", "node_modules", "frontend", ".pytest_cache", "build", "dist" }


def _source_digest(root: Path) -> tuple[str, int]:
    hasher = hashlib.sha256()
    count = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in _SKIP or part.endswith(".egg-info") for part in relative.parts) or not path.is_file(): continue
        if path.name == "_my_config.py": continue
        if path.suffix not in (".py", ".json", ".html", ".js", ".css"): continue
        data = path.read_bytes().replace(b"\r\n", b"\n")
        hasher.update(relative.as_posix().encode("utf-8") + b"\0" + hashlib.sha256(data).digest())
        count += 1
    return hasher.hexdigest(), count


async def provide(data) -> list[dict]:
    from .. import additive
    records = []
    script = PACKAGE / "static" / "js" / "status.js"
    if script.is_file():
        records.append({
            "id": "peering_status_js",
            "additive": additive.id,
            "type": "script",
            "algorithm": "sha256",
            "hash": hashlib.sha256(script.read_bytes()).hexdigest(),
            "version": wf_peering.__version__,
            "served_version": wf_peering.__version__,
            "url": f"{ASSETS}/js/status.js",
            "served": True,
            "computed_at": utc_now(),
            "label": "Peering status page script (wf-peering)",
            "provenance": { "status": "unsigned" }
        })
    value, count = _source_digest(_ROOT)
    records.append({
        "id": "peering_source",
        "additive": additive.id,
        "type": "source",
        "algorithm": "sha256",
        "hash": value,
        "version": str(additive.version),
        "computed_at": utc_now(),
        "label": "Peering additive source tree (self-reported)",
        "context": { "files": count, "normalization": "LF, sha256 per file over relative path" },
        "provenance": { "status": "unsigned" }
    })
    value, count = _source_digest(PACKAGE)
    records.append({
        "id": "wf_peering_source",
        "additive": additive.id,
        "type": "source",
        "algorithm": "sha256",
        "hash": value,
        "version": wf_peering.__version__,
        "computed_at": utc_now(),
        "label": "wf-peering extension source tree (self-reported)",
        "context": { "files": count, "normalization": "LF, sha256 per file over relative path" },
        "provenance": { "status": "unsigned" }
    })
    return records


async def record(data) -> dict | None:
    if not isinstance(data, dict): raise TypeError("Expected { kind, source, body }.")
    kind, source, body = data.get("kind"), data.get("source"), data.get("body")
    if not isinstance(kind, str) or not isinstance(source, str) or not isinstance(body, dict):
        raise TypeError("Expected { kind: str, source: str, body: dict }.")
    if kind.split(":", 1)[0] != source:
        raise ValueError("The kind of a ledger entry must start with its source additive id.")
    try:
        return await Ledger.append(kind, source, body, subject=data.get("subject"), ref=data.get("ref"),
                                   auth=data.get("auth"))
    except LedgerError as exc:
        raise ValueError(f"LEDGER_{exc.code}") from exc


async def publish(data) -> dict:
    from ..services.aggregation import push
    record = data.get("record") if isinstance(data, dict) else None
    try: return await push(record)
    except spec.IntegrityError as exc: raise ValueError(f"INTEGRITY_{exc}") from exc


async def retract(data) -> dict:
    from ..services.aggregation import retract as withdraw
    if not isinstance(data, dict) or not isinstance(data.get("id"), str) or not isinstance(data.get("additive"), str):
        raise TypeError("Expected { id: str, additive: str }.")
    return { "id": data["id"], "retracted": await withdraw(data["additive"], data["id"]) }


async def latest_hash(data) -> dict | None:
    artifact = data.get("id") if isinstance(data, dict) else data
    if not isinstance(artifact, str): raise TypeError("Expected an artifact id.")
    return await Integrity.latest(artifact)


async def status(_) -> dict:
    from wf_peering.services.status import summary
    return await summary()
