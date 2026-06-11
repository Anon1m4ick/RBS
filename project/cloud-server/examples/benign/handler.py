def handle(event, context=None):
    name = event.get("name", "world") if isinstance(event, dict) else "world"
    request_id = context.get("request_id") if isinstance(context, dict) else None
    return {"message": f"hello {name}", "request_id": request_id}
