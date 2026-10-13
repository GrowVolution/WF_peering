from webfluid.core.ext import events
from webfluid.utils.logging import factory as log_factory
import uuid

from wf_peering.protocol import integrity as spec
from wf_peering.protocol.entries import utc_now
from wf_peering.services.identity import NodeIdentity
from wf_peering.services.integrity import Integrity
from wf_peering.services.journal import Journal
from wf_peering.services.ledger import Ledger, LedgerError
from wf_peering.settings import settings


def collector() -> str:
    from .. import additive
    return additive.unique_name("integrity")


async def collect(run_id: str, reason: str) -> list:
    try:
        results = await events.request(collector(), {
            "run": run_id, "node": NodeIdentity.node_id(), "role": settings.role, "reason": reason
        })
    except ValueError as exc:
        log_factory.exception(exc, "[peering] The integrity collector is not registered.")
        return []
    except Exception as exc:
        log_factory.exception(exc, "[peering] An integrity provider failed inside a request context.")
        return [None]
    return results if isinstance(results, list) else [results]


async def run(reason: str = "scheduled") -> dict:
    async with Integrity.guard():
        run_id = uuid.uuid4().hex
        await Integrity.start_run(run_id, utc_now())

        groups = spec.aggregate(await collect(run_id, reason))
        changes = []
        for group in groups:
            for record in group["records"]:
                change = await Integrity.persist(group["provider"], record, run_id)
                if change: changes.append(change)
        missing = await Integrity.mark_missing(groups, run_id)

        summary = [
            { "provider": group["provider"], "status": group["status"],
              "records": len(group["records"]), "errors": group["errors"] }
            for group in groups
        ]
        status = "ok" if all(group["status"] == "ok" for group in groups) else "partial"
        await Integrity.finish_run(run_id, status, summary)

    for change in changes: await _record(change)
    for artifact in missing: await _record_missing(artifact, run_id)
    await Journal.append("peering:integrity-run", {
        "run": run_id, "status": status, "groups": summary,
        "changed": [change["artifact"] for change in changes], "missing": missing
    })
    return { "run": run_id, "status": status, "groups": summary, "changed": len(changes), "missing": missing }


async def push(record) -> dict:
    if not isinstance(record, dict): raise spec.IntegrityError("NOT_AN_OBJECT")
    provider = record.get("additive")
    if not isinstance(provider, str) or not provider: raise spec.IntegrityError("INVALID_ADDITIVE")
    normalized = spec.normalize(record, provider)
    run_id = Integrity.push_id(uuid.uuid4().hex)
    async with Integrity.guard():
        change = await Integrity.persist(provider, normalized, run_id)
    if change: await _record(change)
    latest = await Integrity.latest(normalized["id"])
    return {
        "id": normalized["id"], "changed": change is not None, "fingerprint": spec.fingerprint(normalized),
        "chain_length": latest.get("chain_length") if latest else None,
        "ledger_seq": latest.get("ledger_seq") if latest else None
    }


async def retract(provider: str, artifact: str) -> bool:
    async with Integrity.guard():
        retracted = await Integrity.retract(provider, artifact)
    if retracted: await _record_missing(artifact, Integrity.push_id(uuid.uuid4().hex))
    return retracted


async def _record(change: dict):
    try:
        entry = await Ledger.append(
            "peering:integrity", "peering",
            {
                "artifact": change["artifact"], "provider": change["provider"],
                "record": change["record"], "fingerprint": change["fingerprint"],
                "previous": change["previous"], "run": change["run"], "context": change["context"]
            },
            subject=f"artifact:{change['artifact']}",
            ref=f"integrity:{change['artifact']}:{change['fingerprint']}:{change['previous'] or '-'}:{change['run']}"
        )
    except LedgerError as exc:
        log_factory.error(f"[peering] Recording integrity of {change['artifact']} failed: {exc.code}")
        return
    await Integrity.link(change["id"], entry["seq"])


async def _record_missing(artifact: str, run_id: str):
    try:
        await Ledger.append(
            "peering:integrity-missing", "peering", { "artifact": artifact, "run": run_id },
            subject=f"artifact:{artifact}", ref=f"integrity-missing:{artifact}:{run_id}"
        )
    except LedgerError as exc:
        log_factory.error(f"[peering] Recording the disappearance of {artifact} failed: {exc.code}")
