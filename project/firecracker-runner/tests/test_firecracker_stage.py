import io
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path

from oblak.firecracker.audit import AuditLog, verify_hash_chain
from oblak.firecracker.bundle import BundleValidationError, validate_bundle, validate_entrypoint
from oblak.firecracker.config import FirecrackerConfig
from oblak.firecracker.executor import ExecutionRequest, FirecrackerExecutor, parse_guest_result
from oblak.firecracker.guest_runner import GuestRunnerError, safe_extract_tar


class FirecrackerStageTests(unittest.TestCase):
    def test_dry_run_prepares_payload_and_audit_chain(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle"
            bundle.mkdir()
            (bundle / "handler.py").write_text(
                "def handle(event, context):\n    return {'ok': True}\n",
                encoding="utf-8",
            )

            config = FirecrackerConfig(work_dir=root / "runs", audit_log=root / "audit.jsonl")
            request = ExecutionRequest(
                function_id="hello",
                request_id="req-12345678",
                bundle_dir=bundle,
                event={"name": "test"},
            )
            result = FirecrackerExecutor(config).run(request, dry_run=True)

            self.assertEqual(result.status, "DRY_RUN")
            self.assertEqual(result.request_id, "req-12345678")
            self.assertTrue((result.run_dir / "function-staging" / "code.tar").is_file())
            self.assertTrue((result.run_dir / "function-staging" / "manifest.json").is_file())
            self.assertTrue(verify_hash_chain(root / "audit.jsonl"))

    def test_bundle_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "handler.py").write_text("def handle(event, context): return None\n", encoding="utf-8")
            try:
                os.symlink("/etc/passwd", root / "passwd-link")
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlink is not available on this platform: {exc}")

            with self.assertRaises(BundleValidationError):
                validate_bundle(root, "handler.py:handle")

    def test_entrypoint_validation_rejects_unsafe_values(self):
        with self.assertRaises(BundleValidationError):
            validate_entrypoint("../handler.py:handle")
        with self.assertRaises(BundleValidationError):
            validate_entrypoint("handler.py:not-valid")
        with self.assertRaises(BundleValidationError):
            validate_entrypoint("handler:handle")

    def test_guest_safe_extract_rejects_tar_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tar_path = root / "evil.tar"
            with tarfile.open(tar_path, "w") as tar:
                data = b"print('escape')"
                info = tarfile.TarInfo("../evil.py")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))

            with self.assertRaises(GuestRunnerError):
                safe_extract_tar(tar_path, root / "dst")

    def test_parse_guest_result(self):
        parsed = parse_guest_result(
            "boot noise\n"
            "OBLAK_RESULT_BEGIN\n"
            '{"status": "ok", "return": {"answer": 42}}\n'
            "OBLAK_RESULT_END\n"
            "shutdown noise\n"
        )
        self.assertEqual(parsed["status"], "ok")
        self.assertEqual(parsed["return"]["answer"], 42)

    def test_audit_hash_chain_detects_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "audit.jsonl"
            audit = AuditLog(path)
            audit.record("one", value=1)
            audit.record("two", value=2)
            self.assertTrue(verify_hash_chain(path))

            events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            events[0]["value"] = 999
            path.write_text("\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n", encoding="utf-8")
            self.assertFalse(verify_hash_chain(path))


if __name__ == "__main__":
    unittest.main()

