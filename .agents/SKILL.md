---
name: additive-peering
description: Use the `peering` Additive of a WebFluid project when served artifacts (browser scripts, release archives) or signed account changes must be observable by independent peers, or when your Additive must report what it serves. Load it before adding integrity checks, transparency logs, hash publication or peer registration, and before writing a `peering_integrity` handler.
---

# peering — agent guide

<!-- index -->
This file is short enough to read whole; the ranges are for coming back to one section. Every file
it points to opens with an index of the same shape — read those first 30 lines, then only the ranges
the task needs.

- `25-30` **Do not build what it already does**
- `31-44` **Rules**
- `45-58` **Recipes**
- `59-64` **Verify**
- `65-82` **Contract map**
<!-- /index -->

`peering` is the host side of the peering network. Independent peers (the WebFluid-Peer app) watch
the host: they fetch what it serves, compare it with what it reports, and keep a signed ledger of
key and account changes. The protocol, storage and node identity come from the `wf-peering`
extension; this Additive wires them into the host's event bus and API.

## Do not build what it already does

- A transparency ledger with checkpoints, signed by the node key.
- Integrity observation of served files by peers, with verdicts clients can query.
- Peer registration, health, rate limits and the peer socket.

## Rules

1. **Report what you serve through `peering_integrity`.** Register a non-singleton handler that
   answers your artifacts (`id`, `hash`, `url`, version, provenance); never push hashes elsewhere.
2. **Work without peering.** Every consumer must keep functioning when the Additive is not
   enabled — ask `events.has_query("peering_record")` (WebFluid `1.0.0rc1`) and skip, do not fail.
3. **Record, do not rewrite.** Ledger entries go in through `peering_record`; published release
   artifacts through `peering_artifact` and `peering_artifact:retract`.
4. **One origin.** Peers bind to the host's `BASE_URL`; a second spelling of the host breaks
   identity checks.
5. **Node keys are files, not config values.** `PEERING_KEY_FILE` points at the key; never commit it.
6. **Follow `wf-peering`.** Shared behaviour is changed in the extension, never copied here; every
   contract change in its `CHANGELOG.md` is adopted in this Additive in the same release.

## Recipes

**Report a script you serve**

```python
events.query("peering_integrity", False)(provide)

async def provide(data: dict) -> list[dict]:
    return [{"id": "myapp_widget", "hash": sha256_hex, "url": "/myapp/static/widget.js",
             "version": "v3", "served": True, "provenance": {"status": "unsigned"}}]
```

Only `id` and `hash` are required; ids are unique across all providers.

## Verify

- `GET /peering/api/health` answers when the Additive runs; clients use it to decide between the
  peering trust check and the fallback.
- `GET /peering/api/v1/ledger?kind=&subject=` shows the entries your Additive recorded.

## Contract map

<!-- index ../CONTRACT.md -->
Sections of `../CONTRACT.md`, as that file stands now:

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
