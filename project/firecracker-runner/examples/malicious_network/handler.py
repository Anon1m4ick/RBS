import socket


def handle(event, context):
    try:
        with socket.create_connection(("example.com", 80), timeout=1) as connection:
            connection.sendall(b"GET / HTTP/1.0\r\nHost: example.com\r\n\r\n")
            sample = connection.recv(32).decode("utf-8", errors="replace")
        return {"unexpected_network": True, "sample": sample}
    except Exception as exc:
        return {
            "unexpected_network": False,
            "blocked_by": type(exc).__name__,
            "message": str(exc),
        }

