# Peering API

> A WebFluid additive — the host side of the peering network.

A host cannot prove by itself that it serves what it claims. The peering network lets independent peers
replicate, verify and checkpoint what the host publishes about itself — its integrity records, the key
changes and signed actions of its users — so that a manipulation becomes visible and, where possible,
provable.

This Additive is **optional** and lives **only on the host**. It is the contract through which the host's
other Additives take part, and it serves the peers. The peer itself is a separate WebFluid app (the
`peering` repository) that runs without Additives. Both sides share their protocols, storage and
verification through the **`wf-peering`** extension.

```
host app: auth · users · … · peering (Additive)  ──┐
                                                   ├── wf-peering (extension)
peer:     peering (app, no Additives)  ────────────┘
```

---

## What it provides

- **The integrity contract** — any Additive can register a provider on the `peering_integrity` collector
  and have its artifacts (scripts, source trees, manifests) collected, versioned and published, without the
  peering code knowing the artifact type. Artifacts that change at known moments and are too many to
  collect — package releases, for instance — are pushed with `peering_artifact` instead. See the
  [contract](CONTRACT.md).
- **The signed ledger** — every integrity change, every key statement and every signed user action the
  host's Additives record through `peering_record` lands in an append-only, hash-chained ledger the host
  signs with its node key. Peers replicate it and check every entry themselves.
- **The peer endpoint** — `WS /peering/ws/peer`: a mutual, signed handshake, then live replication of new
  entries, heartbeats and range requests. Peers push their signed checkpoints back over the same socket.
- **The host API** — the public, read-only peering API under `/peering/api/v1` (`/hash?id=<artifact>`,
  ledger, proofs, checkpoints, peers, trust, conflicts), plus `GET /peers/connections`.
- **A status page** at `/peering/` that reads only the public API, rendered in the request's locale
  (English and German, from `wf-peering`).

The host's daily checkpoint (00:00 UTC by default) is signed and recorded in its own ledger. The host's trust
score is a *self-assessment* and never green on its own: the verdict that matters comes from the peers.

---

## Installation

The Additive needs the `wf-peering` extension in the same environment:

```bash
wf ocean install -a peering -e peering      # or, from a checkout: pip install -e extensions/peering
```

`wf-peering` is deliberately not listed under the manifest's `packages`, which `pip` would resolve against
PyPI. Without it the Additive refuses to enable with a message that says what to install.

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

Run the migration cycle once: the tables (`peering_*`) are exposed to `wf migrate` through
`additives.peering.models`.

---

## Configuration

The host-relevant keys, with defaults in `config.py`; the extension's README lists them all.

| Key                              | Default         | Meaning                                                                 |
|----------------------------------|-----------------|-------------------------------------------------------------------------|
| `PEERING_PUBLIC_URL`             | `BASE_URL`      | The host's public origin. Keep it the address browsers and apps use.    |
| `PEERING_KEY_FILE`               | `keys/node.key` | The host's node key, relative to this Additive (gitignored, mode 0600). |
| `PEERING_NODE_KEY`               | env             | The key itself instead of a file.                                       |
| `PEERING_PEERS`                  | `[]`            | Peers the host checks even if they never connected.                     |
| `PEERING_MAX_PEERS`              | `64`            | Connected and known peers at most.                                      |
| `PEERING_PEER_INACTIVE_DAYS`     | `30`            | Days without contact until a peer leaves the statistics; `0` keeps it.  |
| `PEERING_REGISTRATIONS_PER_HOUR` | `20`            | New peers accepted per hour.                                            |
| `PEERING_CHECKPOINT_TIME`        | `(0, 0)`        | The daily checkpoint, UTC.                                              |
| `PEERING_INTEGRITY_INTERVAL`     | `900`           | Seconds between integrity collections.                                  |
| `PEERING_SCHEDULE`               | `True`          | Turns the jobs off.                                                     |
| `PEERING_ALLOW_INSECURE`         | `False`         | `http` and local addresses, for development only. Implied by `wf run -d`. |

`PEERING_ROLE` no longer exists: the Additive is always the host and ignores the key with a warning.

The host has exactly one origin. Peers watch it under that address, clients check that a peer watches
the address they visit, and account handles in the ledger are derived from it. A host reached under
several addresses — `localhost` in the browser, a LAN address on a phone — makes peers report
`URL_MISMATCH` and clients count them as unconfirmed. Locally, keep one address for everything (forward
ports to a phone with `adb reverse`).

In debug mode (`wf run -d`) the host and its peers can run on `http://localhost`: plain HTTP and local
addresses are allowed, the HTTPS signals stay out of the trust score, and every signed trust report says
`debug: true`.

---

## What peers can and cannot establish

Peers verify every signature, every hash chain and every account's key log and actions independently,
observe the scripts the host actually serves, and compare checkpoints among each other. A host that
rewrites, truncates or forks its history, serves a script that differs from its own claim, or changes a
user's keys without the user's proof is caught and recorded with the signed evidence.

They cannot see what the host's server does internally, and a host that lies the same way to everyone
from the start can only be caught by an independent reference (such as the published integrity
repository of the users Additive). A clean result means agreement, not a guarantee.

---

## Tests

```bash
cd additives/peering && pytest tests
```

They build a temporary host app with this Additive and run against the installed `wf-peering`. The
tests of `auth` and `users` include this Additive too and talk to it only through its event contracts and
its public API.

---

## License

This Additive has no license file yet. The shared code it runs on, `wf-peering`, is licensed under the
[GNU General Public License v3.0](LICENSE).
