async def handle_request():
    from wf_peering import peering
    from .. import additive
    return await peering.render_status(f"{additive.prefix}/api/v1")
