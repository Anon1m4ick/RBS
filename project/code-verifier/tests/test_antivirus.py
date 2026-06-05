import shutil
from pathlib import Path

import pytest

from verifier.antivirus import run_clamav

SAMPLES = Path(__file__).parent / "samples"

# Standard EICAR test string — detected by ClamAV as a test signature, not real malware.
EICAR = (
    r"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
)


@pytest.fixture
def clamav_available() -> bool:
    return shutil.which("clamscan") is not None


def test_safe_file_passes_clamav(clamav_available: bool, tmp_path: Path) -> None:
    if not clamav_available:
        pytest.skip("clamscan is not installed on PATH")

    safe = tmp_path / "safe.py"
    safe.write_text("print('hello')\n")

    ok, reason = run_clamav(safe)
    assert ok is True
    assert reason == ""


def test_safe_hello_sample_passes_clamav(clamav_available: bool) -> None:
    if not clamav_available:
        pytest.skip("clamscan is not installed on PATH")

    ok, reason = run_clamav(SAMPLES / "safe_hello.py")
    assert ok is True
    assert reason == ""


def test_eicar_test_file_blocked_by_clamav(clamav_available: bool, tmp_path: Path) -> None:
    if not clamav_available:
        pytest.skip("clamscan is not installed on PATH")

    eicar = tmp_path / "eicar.com"
    eicar.write_text(EICAR)

    ok, reason = run_clamav(eicar)
    assert ok is False
    assert reason.startswith("virus found:")
