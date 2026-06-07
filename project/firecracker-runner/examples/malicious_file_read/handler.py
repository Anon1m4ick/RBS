def handle(event, context):
    try:
        data = open("/etc/shadow", "r", encoding="utf-8").read(80)
        return {"unexpected_read": True, "sample": data}
    except Exception as exc:
        return {
            "unexpected_read": False,
            "blocked_by": type(exc).__name__,
            "message": str(exc),
        }

