"""A simple, safe serverless function handler."""


def handler(event: dict | None = None) -> dict:
    """Return a greeting based on the event payload."""
    name = "World"
    if event and isinstance(event, dict):
        name = event.get("name", name)
    return {"message": f"Hello, {name}!"}


if __name__ == "__main__":
    print(handler({"name": "Oblak"}))
