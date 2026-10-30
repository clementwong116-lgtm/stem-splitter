"""Mocked StemSplit client + provider resolution (no real API key / network)."""
from __future__ import annotations

import io
import json
import sys
import tempfile
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stemsplit_client import StemSplitClient, StemSplitError  # noqa: E402


class FakeResponse:
    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_separate_file_happy_path(tmp_path: Path | None = None):
    base = Path(tempfile.mkdtemp()) if tmp_path is None else tmp_path
    src = base / "song.mp3"
    src.write_bytes(b"FAKEMP3DATA")
    out_v = base / "vocals.wav"
    out_i = base / "instrumental.wav"

    calls: list[tuple[str, str]] = []
    poll_n = {"n": 0}

    def fake_urlopen(req, timeout=None):
        method = getattr(req, "get_method", lambda: req.method)()
        url = req.full_url
        calls.append((method, url))
        data = req.data

        if method == "POST" and url.endswith("/api/v1/upload"):
            body = {
                "uploadUrl": "https://storage.example/presign",
                "uploadKey": "uploads/api_test/input.mp3",
                "expiresAt": "2099-01-01T00:00:00Z",
                "maxFileSizeMb": 500,
            }
            return FakeResponse(json.dumps(body).encode())

        if method == "PUT" and "storage.example" in url:
            assert data == b"FAKEMP3DATA"
            return FakeResponse(b"", status=200)

        if method == "POST" and url.endswith("/api/v1/jobs"):
            payload = json.loads(data.decode())
            assert payload["uploadKey"] == "uploads/api_test/input.mp3"
            assert payload["outputType"] == "BOTH"
            assert payload["outputFormat"] == "WAV"
            body = {
                "id": "job_mock_1",
                "status": "PENDING",
                "progress": 0,
            }
            return FakeResponse(json.dumps(body).encode())

        if method == "GET" and url.endswith("/api/v1/jobs/job_mock_1"):
            poll_n["n"] += 1
            if poll_n["n"] < 2:
                body = {"id": "job_mock_1", "status": "PROCESSING", "progress": 40}
            else:
                body = {
                    "id": "job_mock_1",
                    "status": "COMPLETED",
                    "progress": 100,
                    "outputs": {
                        "vocals": {
                            "url": "https://storage.example/vocals.wav",
                            "expiresAt": "2099-01-01T00:00:00Z",
                        },
                        "instrumental": {
                            "url": "https://storage.example/instrumental.wav",
                            "expiresAt": "2099-01-01T00:00:00Z",
                        },
                    },
                }
            return FakeResponse(json.dumps(body).encode())

        if method == "GET" and url.endswith("/vocals.wav"):
            return FakeResponse(b"VOCALS_WAV")
        if method == "GET" and url.endswith("/instrumental.wav"):
            return FakeResponse(b"INSTR_WAV")

        raise AssertionError(f"unexpected request {method} {url}")

    progress_log: list[tuple[int, str]] = []

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        client = StemSplitClient("sk_live_test_fake", base_url="https://stemsplit.io")
        result = client.separate_file(
            src,
            out_vocals=out_v,
            out_instrumental=out_i,
            poll_interval=0.01,
            on_progress=lambda p, m: progress_log.append((p, m)),
        )

    assert result["status"] == "COMPLETED"
    assert out_v.read_bytes() == b"VOCALS_WAV"
    assert out_i.read_bytes() == b"INSTR_WAV"
    assert any(p >= 90 for p, _ in progress_log)
    assert any("/api/v1/upload" in u for _, u in calls)
    assert any(m == "PUT" for m, _ in calls)
    print("test_separate_file_happy_path OK")


def test_http_error_parses_code():
    def boom(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url,
            402,
            "Payment Required",
            hdrs=None,
            fp=io.BytesIO(
                json.dumps(
                    {
                        "error": {
                            "code": "INSUFFICIENT_CREDITS",
                            "message": "Not enough credits",
                        }
                    }
                ).encode()
            ),
        )

    with mock.patch("urllib.request.urlopen", side_effect=boom):
        client = StemSplitClient("sk_live_test_fake")
        try:
            client.get_job("x")
            raise AssertionError("expected StemSplitError")
        except StemSplitError as e:
            assert e.code == "INSUFFICIENT_CREDITS"
            assert e.status == 402
    print("test_http_error_parses_code OK")


def test_provider_resolution():
    import importlib

    # Simulate no key → not stemsplit when auto
    with mock.patch.dict(
        "os.environ",
        {"STEMSPLIT_API_KEY": "", "STEM_PROVIDER": "auto"},
        clear=False,
    ):
        # Re-import is awkward; call helpers after patching module attrs
        import app as app_mod

        app_mod.STEMSPLIT_API_KEY = ""
        app_mod.STEM_PROVIDER = "auto"
        with mock.patch.object(app_mod, "_demucs_available", return_value=False):
            assert app_mod._resolve_provider() == "ffmpeg"
            assert app_mod._stemsplit_configured() is False

        app_mod.STEMSPLIT_API_KEY = "sk_live_x"
        app_mod.STEM_PROVIDER = "auto"
        assert app_mod._stemsplit_configured() is True
        assert app_mod._resolve_provider() == "stemsplit"

        app_mod.STEM_PROVIDER = "ffmpeg"
        assert app_mod._resolve_provider() == "ffmpeg"
    print("test_provider_resolution OK")



def test_separate_file_instrumental_only(tmp_path: Path | None = None):
    """Vocal remover path: outputType INSTRUMENTAL, only instrumental downloaded."""
    base = Path(tempfile.mkdtemp()) if tmp_path is None else tmp_path
    src = base / "song.mp3"
    src.write_bytes(b"FAKEMP3DATA")
    out_i = base / "instrumental.wav"

    def fake_urlopen(req, timeout=None):
        method = getattr(req, "get_method", lambda: req.method)()
        url = req.full_url
        data = req.data

        if method == "POST" and url.endswith("/api/v1/upload"):
            body = {
                "uploadUrl": "https://storage.example/presign",
                "uploadKey": "uploads/api_test/input.mp3",
            }
            return FakeResponse(json.dumps(body).encode())

        if method == "PUT" and "storage.example" in url:
            return FakeResponse(b"", status=200)

        if method == "POST" and url.endswith("/api/v1/jobs"):
            payload = json.loads(data.decode())
            assert payload["outputType"] == "INSTRUMENTAL"
            body = {"id": "job_instr_1", "status": "PENDING", "progress": 0}
            return FakeResponse(json.dumps(body).encode())

        if method == "GET" and url.endswith("/api/v1/jobs/job_instr_1"):
            body = {
                "id": "job_instr_1",
                "status": "COMPLETED",
                "progress": 100,
                "outputs": {
                    "instrumental": {
                        "url": "https://storage.example/instrumental.wav",
                        "expiresAt": "2099-01-01T00:00:00Z",
                    },
                },
            }
            return FakeResponse(json.dumps(body).encode())

        if method == "GET" and url.endswith("/instrumental.wav"):
            return FakeResponse(b"INSTR_ONLY")

        raise AssertionError(f"unexpected request {method} {url}")

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        client = StemSplitClient("sk_live_test_fake", base_url="https://stemsplit.io")
        result = client.separate_file(
            src,
            out_instrumental=out_i,
            out_vocals=None,
            output_type="INSTRUMENTAL",
            poll_interval=0.01,
        )

    assert result["status"] == "COMPLETED"
    assert out_i.read_bytes() == b"INSTR_ONLY"
    print("test_separate_file_instrumental_only OK")


def test_normalize_mode():
    import app as app_mod

    assert app_mod._normalize_mode("split") == "split"
    assert app_mod._normalize_mode("vocal_remover") == "vocal_remover"
    assert app_mod._normalize_mode("karaoke") == "vocal_remover"
    assert app_mod._normalize_mode(None) == "split"
    assert app_mod._normalize_mode("") == "split"
    print("test_normalize_mode OK")


if __name__ == "__main__":
    test_separate_file_happy_path()
    test_separate_file_instrumental_only()
    test_http_error_parses_code()
    test_provider_resolution()
    test_normalize_mode()
    print("ALL PASSED")
