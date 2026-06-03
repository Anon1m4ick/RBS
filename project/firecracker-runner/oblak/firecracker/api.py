"""Minimal Firecracker REST API client over a Unix domain socket."""

from __future__ import annotations

import http.client
import json
import socket
from pathlib import Path
from typing import Any


class FirecrackerAPIError(RuntimeError):
    def __init__(self, status: int, reason: str, body: str):
        super().__init__(f"Firecracker API failed with HTTP {status} {reason}: {body}")
        self.status = status
        self.reason = reason
        self.body = body


class UnixSocketHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str | Path, timeout: float = 5.0):
        super().__init__("localhost", timeout=timeout)
        self.socket_path = str(socket_path)

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self.socket_path)
        self.sock = sock


class FirecrackerAPI:
    """Small wrapper around the Firecracker control-plane API."""

    def __init__(self, socket_path: str | Path, timeout: float = 5.0):
        self.socket_path = Path(socket_path)
        self.timeout = timeout

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        payload = b""
        headers = {}
        if body is not None:
            payload = json.dumps(body, sort_keys=True).encode("utf-8")
            headers["Content-Type"] = "application/json"

        conn = UnixSocketHTTPConnection(self.socket_path, timeout=self.timeout)
        try:
            conn.request(method, path, body=payload, headers=headers)
            response = conn.getresponse()
            response_body = response.read().decode("utf-8", errors="replace")
        finally:
            conn.close()

        if response.status >= 300:
            raise FirecrackerAPIError(response.status, response.reason, response_body)
        if not response_body:
            return None
        return json.loads(response_body)

    def put_json(self, path: str, body: dict[str, Any]) -> Any:
        return self.request("PUT", path, body)

    def configure_logger(self, log_path: str | Path, level: str = "Info") -> None:
        self.put_json(
            "/logger",
            {
                "log_path": str(log_path),
                "level": level,
                "show_level": True,
                "show_log_origin": True,
            },
        )

    def configure_metrics(self, metrics_path: str | Path) -> None:
        self.put_json("/metrics", {"metrics_path": str(metrics_path)})

    def set_machine_config(
        self,
        *,
        vcpu_count: int,
        mem_size_mib: int,
        smt: bool = False,
        track_dirty_pages: bool = False,
    ) -> None:
        self.put_json(
            "/machine-config",
            {
                "vcpu_count": vcpu_count,
                "mem_size_mib": mem_size_mib,
                "smt": smt,
                "track_dirty_pages": track_dirty_pages,
            },
        )

    def set_boot_source(self, kernel_image_path: str | Path, boot_args: str) -> None:
        self.put_json(
            "/boot-source",
            {
                "kernel_image_path": str(kernel_image_path),
                "boot_args": boot_args,
            },
        )

    def attach_drive(
        self,
        drive_id: str,
        path_on_host: str | Path,
        *,
        is_root_device: bool,
        is_read_only: bool,
    ) -> None:
        self.put_json(
            f"/drives/{drive_id}",
            {
                "drive_id": drive_id,
                "path_on_host": str(path_on_host),
                "is_root_device": is_root_device,
                "is_read_only": is_read_only,
            },
        )

    def attach_network(self, *, iface_id: str, guest_mac: str, host_dev_name: str) -> None:
        self.put_json(
            f"/network-interfaces/{iface_id}",
            {
                "iface_id": iface_id,
                "guest_mac": guest_mac,
                "host_dev_name": host_dev_name,
            },
        )

    def start_instance(self) -> None:
        self.put_json("/actions", {"action_type": "InstanceStart"})

