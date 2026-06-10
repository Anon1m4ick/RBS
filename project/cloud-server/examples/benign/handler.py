def handle(event):
    name = event.get("name", "world") if isinstance(event, dict) else "world"
    return {"message": f"hello {name}"}
