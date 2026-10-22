# Peering API — Documentation

`peering` makes an application a **host** of the peering network. It keeps the signed ledger in
which the application's Additives record what they serve and what their users' keys and actions
are, it accepts peers on its socket, and it serves the public, read-only API that peers and clients
read. The protocol, the storage and the node identity come from the `wf-peering` extension; this
Additive is the host's half of it and the contract through which the host's other Additives take
part.

This guide is for two readers: the person who runs a host, and the author of an Additive that wants
its data to be checked by peers. The concepts — ledger, checkpoints, trust score — are explained in
the documentation of `wf-peering`; the exact queries and routes are in [CONTRACT.md](CONTRACT.md).

---

## What a host does

- **Collects integrity records.** Every `PEERING_INTEGRITY_INTERVAL` seconds (900 by default) the
  host asks every Additive that registered on the `peering_integrity` collector which artifacts it
  serves, stores what changed as the next link of each artifact's hash chain, records artifacts that
  disappeared as missing — never deletes them — and appends every change to the ledger.
- **Keeps the ledger.** Integrity changes, account key statements and signed user actions that the
  host's Additives record are appended to a hash-chained ledger the host signs with its node key.
- **Serves peers.** Peers connect to `WS /peering/ws/peer`, prove their identity in a mutual signed
  handshake, receive new entries live and push their signed checkpoints back.
- **Publishes.** The public API under `/peering/api/v1` — node statement, ledger, proofs, integrity
  records, checkpoints, peers, trust, conflicts — and a status page at `/peering/`.
- **Checkpoints daily** at `PEERING_CHECKPOINT_TIME` (00:00 UTC by default) and signs the result
  into its own ledger.

The host also computes a trust score, but only as a self-assessment: without peers it can never be
green. The verdict that counts comes from the peers that watch it.

A peer is a separate WebFluid application built on `wf-peering`, which anyone can run against any
host; it needs nothing from this Additive except its public API and socket.

---

## Taking part as an Additive

An Additive takes part through three queries and never imports `peering`:

**Report what you serve** by registering a handler on the `peering_integrity` collector. It answers
a list of records, each with at least an `id` (unique across all Additives — prefix it with yours)
and a `hash`, and ideally the public `url`, a `version` and where the reference lives. Peers fetch
what is served and compare it; a record with `served: false` is kept and answered but not fetched.
A failing handler affects only its own group, and its artifacts are not marked missing because of
the failure.

**Push what changes at known moments** — a release published, an archive rewritten — with
`peering_artifact`, instead of reporting thousands of records on every run. Pushed records are
never marked missing by a run; only their owner retracts them with `peering_artifact:retract`.

**Record ledger entries** with `peering_record`: a `kind` prefixed with your id, a body, an optional
subject and an idempotency `ref`. Bodies in the key-log and signed-action formats are verified on
append. Outside a request the query answers `None` instead of raising, so keep entries in an outbox
and retry.

All three are optional for the Additive that uses them: check `events.has_query("peering_record")`
and skip when `peering` is not enabled. An Additive must work the same without it.

Conflicts the host records — a failed verification, a key change, an equivocation — are announced
on the internal `peering_alert` signal with a severity of `normal`, `high` or `critical`, for an
Additive that wants to notify someone.

---

## Installing and enabling

The Additive needs the `wf-peering` extension in the same environment. It is deliberately not a
manifest package, because `pip` would look for it on PyPI:

```bash
wf ocean install -a peering -e peering
```

```ini
[extensions]
EXT_SQLALCHEMY = 1
EXT_EVENTS = 1
EXT_SCHEDULING = 1
EXT_BABEL = 1

[features]
WF_ADDITIVES = 1

[additives]
peering = 1
```

Then run the migration cycle once: the `peering_*` tables reach `wf migrate` through
`additives.peering.models`. Without the extension the Additive refuses to enable and says what to
install.

---

## Configuration

| Key                              | Default         | What it changes                                                         |
|----------------------------------|-----------------|-------------------------------------------------------------------------|
| `PEERING_PUBLIC_URL`             | `BASE_URL`      | the host's public origin — keep it the one address browsers and apps use |
| `PEERING_KEY_FILE`               | `keys/node.key` | the node key, relative to this Additive; gitignored, mode `0600`        |
| `PEERING_PEERS`                  | `[]`            | peers the host checks even if they never connected                      |
| `PEERING_MAX_PEERS`              | `64`            | known and connected peers at most                                       |
| `PEERING_REGISTRATIONS_PER_HOUR` | `20`            | new peers accepted per hour                                             |
| `PEERING_PEER_INACTIVE_DAYS`     | `30`            | days without contact until a peer leaves the statistics; `0` keeps it   |
| `PEERING_CHECKPOINT_TIME`        | `(0, 0)`        | the daily checkpoint, UTC                                               |
| `PEERING_INTEGRITY_INTERVAL`     | `900`           | seconds between integrity collections                                   |
| `PEERING_SCHEDULE`               | `True`          | `False` turns every job off (tests, one-off scripts)                    |
| `PEERING_ALLOW_INSECURE`         | `False`         | `http` and local addresses — development only, implied by `wf run -d`   |
| `PEERING_MODELS_DB_BIND`         | —               | a bind key for the `peering_*` tables                                   |

The node key is the host's identity. Keep it out of version control and in your backups: a host
whose key changes is reported by every peer that watched the old one.

---

## Operating a host

- **One origin.** Peers watch the host under one address, clients check that a peer watches the
  address they visit, and account handles derive from it. Serving the host as `localhost` in the
  browser and as a LAN address on a phone makes peers report `URL_MISMATCH`. Locally, forward ports
  to a phone with `adb reverse` instead of switching addresses.
- **One process.** The scheduler and the peer links are in memory; run the host as one process.
- **Find peers.** A host without peers is honest but unverified. Ask people you do not control to
  run a peer against your origin, or list known peers in `PEERING_PEERS`.
- **Read the status page** at `/peering/`: connected peers, the latest checkpoints and whether peers
  agree, conflicts with their evidence, and the trust report with its basis.

---

## Troubleshooting

| You see                                         | Because                                                                              |
|-------------------------------------------------|--------------------------------------------------------------------------------------|
| The Additive refuses to enable                  | `wf-peering` is not installed in the environment                                     |
| Errors about missing `peering_*` tables         | The migration cycle has not run since the Additive was installed                     |
| Peers report `URL_MISMATCH`                     | The host is reached under more than one address                                      |
| Trust stays **unclear**                         | No independent peer watches the host yet                                             |
| A provider's group shows `failed` or `invalid`  | That Additive's `peering_integrity` handler raised or answered something malformed   |
| `peering_record` answers `None`                 | It was called outside a request; keep the entry and retry from a job                 |
| A key-change conflict right after a deploy      | The node key file was not carried over                                               |

---

## Further reading

- [CONTRACT.md](CONTRACT.md) — every query, record field, route and the peer socket
- [README.md](README.md) — what peers can and cannot establish
- `wf-peering`'s documentation — the protocol, the trust score and the network policy
