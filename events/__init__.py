from webfluid.core.ext import events


def setup():
    from .. import additive
    from .contracts import provide, record, publish, retract, latest_hash, status

    events.query(additive.unique_name("integrity"), False)(provide)
    events.query(additive.unique_name("record"))(record)
    events.query(additive.unique_name("artifact"))(publish)
    events.query(additive.unique_name("artifact:retract"))(retract)
    events.query(additive.unique_name("hash"))(latest_hash)
    events.query(additive.unique_name("status"))(status)
    events.create_signal(additive.unique_name("alert"), internal=True)
