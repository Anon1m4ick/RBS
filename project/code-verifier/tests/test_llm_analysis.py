from pathlib import Path
from unittest.mock import MagicMock, patch

from verifier.llm_analysis import _parse_llm_json, run_llm

SAMPLES = Path(__file__).parent / "samples"


def _mock_gemini_response(text: str) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": text}],
                },
            },
        ],
    }
    return mock_resp


@patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
@patch("verifier.llm_analysis.requests.post")
def test_safe_response(mock_post: MagicMock) -> None:
    mock_post.return_value = _mock_gemini_response('{"safe": true}')

    result = run_llm(SAMPLES / "safe_hello.py")

    assert result.ok is True
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert call_kwargs.kwargs["params"] == {"key": "test-key"}


@patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
@patch("verifier.llm_analysis.requests.post")
def test_unsafe_response(mock_post: MagicMock) -> None:
    mock_post.return_value = _mock_gemini_response(
        '{"safe": false, "reason": "attempts to delete system files"}'
    )

    result = run_llm(SAMPLES / "malicious_delete.py")

    assert result.ok is False
    assert result.failed_check == "llm"
    assert "delete system files" in result.reason


@patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
@patch("verifier.llm_analysis.requests.post")
def test_malformed_json_treated_as_unsafe(mock_post: MagicMock) -> None:
    mock_post.return_value = _mock_gemini_response(
        "I think this code is unsafe because it uses os.system"
    )

    result = run_llm(SAMPLES / "safe_hello.py")

    assert result.ok is False
    assert result.failed_check == "llm"
    assert "could not parse LLM response" in result.reason


def test_parse_fenced_json_response() -> None:
    assert _parse_llm_json('```json\n{"safe": true}\n```') == {"safe": True}


def test_parse_json_with_surrounding_text() -> None:
    assert _parse_llm_json('Result:\n{"safe": false, "reason": "network"}') == {
        "safe": False,
        "reason": "network",
    }


@patch.dict("os.environ", {}, clear=True)
def test_missing_api_key_fails_closed() -> None:
    result = run_llm(SAMPLES / "safe_hello.py")

    assert result.ok is False
    assert result.failed_check == "llm"
    assert "GEMINI_API_KEY" in result.reason
