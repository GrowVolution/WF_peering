# Peering API — Contract

<!-- index -->
Read this file in parts. Each range is `first-last` as the file stands now — open one with the Read
tool's `offset`/`limit`, or `sed -n 'first,lastp'`.

- `29-41` **At a glance**
- `42-150` **Events / Queries**
  - `47-87` peering_integrity *(collector query, not singleton)*
  - `88-110` peering_artifact *(query)*
  - `111-116` peering_artifact:retract *(query)*
  - `117-134` peering_record *(query)*
  - `135-139` peering_hash *(query)*
  - `140-143` peering_status *(query)*
  - `144-150` peering_alert *(internal signal)*
- `151-192` **API**
  - `177-192` GET /peering/api/v1/hash?id=shop_checkout
- `193-215` **Peer socket**
<!-- /index -->

The host side of the peering network. Everything here is a contract of the **host**: the event-bus
integration for the host's other Additives, the peer socket, and the host API. Protocols, storage and the
response formats come from the `wf-peering` extension; its README describes them in full.

- API base: `/peering/api/v1` (peers serve the same read-only API under `/api/v1`)
- Peer socket: `WS /peering/ws/peer`
- Status page: `GET /peering/`

## At a glance

|                  |                                                                                                                                                                                                                                                                                 |
|------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Mount            | REST under `/peering/api/v1`, peer socket `WS /peering/ws/peer`, status page `/peering/`                                                                                                                                                                                        |
| Requires         | WebFluid `>=1.0.0rc1`; package `wf-peering` (protocol, ledger, node identity); extensions `sqlalchemy`, `events`, `scheduling`, `babel`                                                                                                                                          |
| Config           | `PEERING_PUBLIC_URL`, `PEERING_KEY_FILE`, `PEERING_PEERS`, `PEERING_ALLOW_INSECURE`, `PEERING_MAX_PEERS`, `PEERING_PEER_INACTIVE_DAYS`, `PEERING_REGISTRATIONS_PER_HOUR`, `PEERING_SCHEDULE`, `PEERING_CHECKPOINT_TIME`, `PEERING_INTEGRITY_INTERVAL`, `PEERING_MODELS_DB_BIND` |
| Emits            | `peering_alert` (internal)                                                                                                                                                                                                                                                      |
| Provides         | `peering_artifact`, `peering_artifact:retract`, `peering_record`, `peering_hash`, `peering_status`                                                                                                                                                                              |
| Extension points | `peering_integrity` (collector: report the artifacts you serve)                                                                                                                                                                                                                 |

---

# Events / Queries

Names are unique names of this Additive (`peering_*`). Other Additives use them only when `peering` is
enabled and must work without it.

## peering_integrity *(collector query, not singleton)*

Every Additive that publishes integrity data registers a handler:

```python
events.query("peering_integrity", False)(provide)

async def provide(data: dict) -> list[dict]:
    # data = { "run": str, "node": str, "role": "host", "reason": "scheduled" | "startup" | … }
    return [ { "id": "shop_checkout", "hash": "…", … } ]
```

`events.request("peering_integrity", …)` returns a **list of lists**: one list per provider, so the origin of
every record is kept. A provider that raises or returns garbage does not affect the others; its group is
reported as `failed` or `invalid`, and its previously known artifacts are **not** marked missing.

A record is a dictionary; only `id` and `hash` are required, everything else is optional and kept:

| Field                                         | Type    | Meaning                                                                |
|-----------------------------------------------|---------|------------------------------------------------------------------------|
| `id`                                          | str     | Artifact id, `^[a-z0-9][a-z0-9_.:-]{1,127}$`, unique across providers. |
| `hash`                                        | hex str | The digest, lower case.                                                |
| `algorithm`                                   | str     | `sha256` (default), `sha384`, `sha512`.                                |
| `additive`                                    | str     | The providing Additive; defaults to the provider's group.              |
| `type`, `label`, `parent`                     | str     | Free classification, human label, enclosing artifact.                  |
| `version`, `served_version`, `latest_version` | str     | What the host has, serves, and what the reference calls latest.        |
| `url`                                         | str     | Host-relative path where the artifact is publicly served (`/…`).       |
| `served`                                      | bool    | Whether the host actually serves it.                                   |
| `size`                                        | int     | Byte size.                                                             |
| `computed_at`                                 | str     | `YYYY-MM-DDTHH:MM:SSZ`; excluded from the record's fingerprint.        |
| `provenance`                                  | object  | `{ "status": "unsigned"                                                | "signed" | "reference-match" | "reference-mismatch" | "reference-unavailable" | "unknown", … }` |
| `reference`, `context`, `extra`               | object  | Type-specific data (reference repository, commit, generator state, …). |

At most 256 records per provider and 16 KiB per record. Each run stores what changed (a hash chain per
artifact: every new record points to the fingerprint of the previous one), records artifacts that
disappeared as missing — never deletes them — and appends every change to the signed ledger
(`peering:integrity`, `peering:integrity-missing`).

The Additive provides three records itself: `peering_status_js` (the status page script, served by
`wf-peering`), `peering_source` (this Additive's source tree) and `wf_peering_source` (the extension's).

## peering_artifact *(query)*

Pushes one record immediately instead of waiting for the next integrity run. Meant for artifacts that change
at moments the providing Additive knows — a release is published, a stored archive is rewritten — and that
are too many to report in every run.

```python
await events.request("peering_artifact", { "record": {
    "id": "example_release:…", "additive": "example", "type": "release", "hash": "…",
    "version": "1.0.0", "served": False, "label": "example 1.0.0", "extra": { … }
} })
# → { "id", "changed": bool, "fingerprint", "chain_length", "ledger_seq" }
```

The record has the same format and limits as a collected one; `additive` is required and names the owner.
A record whose fingerprint equals the current one confirms it and adds nothing; any other record becomes the
next link of the artifact's hash chain and a `peering:integrity` ledger entry. Pushed records are never
marked missing by an integrity run. An invalid record raises `ValueError("INTEGRITY_<CODE>")`; outside a
request context the event bus returns `None` instead.

`served: false` declares that the artifact is not publicly fetchable: peers replicate the record and answer
`/hash?id=` for it, but do not try to download and observe it.

## peering_artifact:retract *(query)*

`{ "id": "<artifact>", "additive": "<owner>" }` → `{ "id", "retracted": bool }`. Marks a pushed or collected
artifact as missing and records `peering:integrity-missing` in the ledger. Only the Additive that provided
the current record can retract it; anything else answers `retracted: false`.

## peering_record *(query)*

Appends an entry to the host's signed ledger. Additives use it, typically through an outbox, for key
statements and signed actions.

```python
await events.request("peering_record", {
    "kind": "shop:order", "source": "shop", "body": { … },
    "subject": "a1.…", "ref": "unique-idempotency-key", "auth": { … }
})
# → { "seq": int, "hash": str, "verification": { … } } or { "seq", "hash", "duplicate": True }
```

`kind` must start with `source:`. A known `ref` returns the existing entry (`duplicate`). Bodies following
`wf-keylog-v1` or `wf-action-v1` are verified on append; the verdict is stored with the entry and replicated.
Errors raise `ValueError("LEDGER_<CODE>")`. Outside a request context the event bus returns `None` instead of
raising — callers keep their outbox entry and retry.

## peering_hash *(query)*

`{ "id": "shop_checkout" }` → the current record of one artifact with `chain_length`, `confirmed_at`,
`missing_since` and `ledger_seq`, or `None`.

## peering_status *(query)*

The same summary as `GET /peering/api/v1/status`.

## peering_alert *(internal signal)*

Triggered for every newly recorded conflict: `{ kind, severity, subject, summary }`. Severity is
`normal`, `high` or `critical`.

---

# API

All routes are `GET`, public, rate limited, answer JSON with `Access-Control-Allow-Origin: *` and
`Cache-Control: no-store`. The handlers and formats are those of `wf-peering`; this table only lists them.

| Route                                                             | Rate    |
|-------------------------------------------------------------------|---------|
| `/node`, `/status`                                                | 120/min |
| `/uptime`                                                         | 60/min  |
| `/ledger`, `/ledger/root`, `/ledger/proof`, `/ledger/consistency` | 120/min |
| `/ledger/head`                                                    | 240/min |
| `/journal`                                                        | 60/min  |
| `/accounts/{handle}`                                              | 120/min |
| `/integrity`                                                      | 120/min |
| `/hash?id=`                                                       | 240/min |
| `/integrity/history?id=`                                          | 60/min  |
| `/peers`                                                          | 120/min |
| `/peers/connections` *(host only)*                                | 60/min  |
| `/checkpoints`                                                    | 120/min |
| `/checkpoints/latest`                                             | 240/min |
| `/checkpoints/peers`, `/checkpoints/agreement`                    | 60/min  |
| `/trust`                                                          | 120/min |
| `/trust/history`, `/conflicts`                                    | 60/min  |

`GET /peering/api/health` answers `{ "status": "ok", "timestamp": … }`.

### GET /peering/api/v1/hash?id=shop_checkout

```json
{
  "id": "shop_checkout", "algorithm": "sha256", "hash": "…",
  "version": "v1", "served_version": "v1", "latest_version": "v1",
  "chain_length": 1, "confirmed_at": "…Z", "missing_since": null, "ledger_seq": 5,
  "record": { … }, "source": "providers"
}
```

`404 UNKNOWN_ARTIFACT` for an unknown id, `400 INVALID_ID` for a malformed one. On a peer the same route
answers from the replicated ledger (`"source": "host-ledger"`) and adds the peer's own `observation`.

---

# Peer socket

`WS /peering/ws/peer`

1. Host → `{ "type": "hello", "statement": { node, key, origin, challenge, protocol, schema, boot, ts }, "signature", "head" }`,
   signed with `wf-peer-hello-v1`.
2. Peer → `{ "type": "auth", "statement": { node, key, url, challenge, nonce, ts, protocol, schema }, "signature" }`,
   signed with `wf-peer-auth-v1`. The challenge must match, the timestamp be fresh, the node id derive from the key.
   The host then fetches `<url>/api/v1/node` itself and accepts the connection only when that address answers
   with a signed statement of the same node for the same `url` — a peer cannot list an address it does not
   serve, nor take over the row of another peer. A peer's public URL therefore has to be reachable from the
   host.
3. Host → `{ "type": "welcome", "statement": { nonce, node, host, ts }, "signature" }`, signed with `wf-peer-welcome-v1`.

Afterwards: the host pushes `{ "type": "entry" }` for every new ledger entry; the peer sends `heartbeat`
(with its head), `range` (`from`, `limit`) and `checkpoint` messages. Errors are `{ "type": "error", "code" }`
followed by a close: `INVALID_AUTH`, `STALE_AUTH`, `INVALID_SIGNATURE`, `PROTOCOL_MISMATCH`, `SELF_CONNECTION`,
`TOO_MANY_PEERS`, `REGISTRATION_RATE`, `URL_CLAIMED_BY_OTHER_NODE`, `INVALID_URL`, `URL_UNREACHABLE` (the
claimed address did not answer with a valid node statement in time), `URL_NOT_VERIFIED` (it answered for
another node), `TOO_MANY_FAILURES`, `AUTH_TIMEOUT`. Four missed heartbeats close the connection. Inbound messages above 64 KiB are ignored.
A peer that does not read its entries fast enough is disconnected (close code 1013, journal reason
`BACKPRESSURE`) as soon as 1000 entries are waiting for it, instead of silently missing them; it
reconnects and requests the gap with `range`.
