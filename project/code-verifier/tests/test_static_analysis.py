import json
import shutil
import subprocess
from pathlib import Path

import pytest

from verifier.static_analysis import run_bandit

SAMPLES = Path(__file__).parent / "samples"


@pytest.fixture
def bandit_available() -> bool:
    return shutil.which("bandit") is not None


def test_safe_hello_passes_bandit(bandit_available: bool) -> None:
    if not bandit_available:
        pytest.skip("bandit is not installed on PATH")

    result = run_bandit(SAMPLES / "safe_hello.py")
    assert result.ok is True
    assert result.failed_check is None


def test_os_system_rm_flagged_by_bandit(bandit_available: bool, tmp_path: Path) -> None:
    if not bandit_available:
        pytest.skip("bandit is not installed on PATH")

    malicious = tmp_path / "evil.py"
    malicious.write_text('import os\nos.system("rm -rf /")\n')

    proc = subprocess.run(
        ["bandit", "-r", str(malicious), "-f", "json", "--quiet"],
        capture_output=True,
        text=True,
    )
    data = json.loads(proc.stdout)
    issues = data.get("results", [])
    assert len(issues) > 0
    assert any("shell" in i.get("issue_text", "").lower() for i in issues)


def test_os_system_rm_blocked_at_medium_or_higher(bandit_available: bool, tmp_path: Path) -> None:
    if not bandit_available:
        pytest.skip("bandit is not installed on PATH")

    malicious = tmp_path / "evil.py"
    malicious.write_text(
        'import os\n'
        'import tarfile\n'
        'os.system("rm -rf /")\n'
        'tarfile.open("/tmp/evil.tar").extractall("/")\n'
    )

    result = run_bandit(malicious)
    assert result.ok is False
    assert result.failed_check == "bandit"
    assert result.reason is not None


def test_malicious_delete_sample_flagged(bandit_available: bool) -> None:
    if not bandit_available:
        pytest.skip("bandit is not installed on PATH")

    result = run_bandit(SAMPLES / "malicious_delete.py")
    assert result.ok is False
    assert result.failed_check == "bandit"
