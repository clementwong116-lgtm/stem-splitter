"""StemSplit API client (server-side only). Docs: https://stemsplit.io/developers/docs"""
from __future__ import annotations

import json
import mimetypes
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

DEFAULT_BASE_URL = "https://stemsplit.io"
DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_POLL_TIMEOUT = 600.0


class StemSplitError(RuntimeError):
    def __init__(self, message: str, *, code: str | None = None, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.status = status


def _guess_content_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    mapping = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".flac": "audio/flac",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
        ".ogg": "audio/ogg",
        ".wma": "audio/x-ms-wma",
    }
    if ext in mapping:
        return mapping[ext]
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


class StemSplitClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 120.0,
        opener: Any | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise StemSplitError("STEMSPLIT_API_KEY is empty", code="MISSING_API_KEY")
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._opener = opener  # optional urllib opener / injectable for tests

    def _headers(self, *, json_body: bool = False) -> dict[str, str]:
        h = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        if json_body:
            h["Content-Type"] = "application/json"
        return h

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        data: bytes | None = None,
        expect_json: bool = True,
    ) -> Any:
        req = urllib.request.Request(url, data=data, method=method)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            if self._opener is not None:
                resp_ctx = self._opener.open(req, timeout=self.timeout)
            else:
                resp_ctx = urllib.request.urlopen(req, timeout=self.timeout)
            with resp_ctx as resp:
                body = resp.read()
                if not expect_json:
                    return body
                if not body:
                    return {}
                return json.loads(body.decode("utf-8"))
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace") if e.fp else ""
            code = None
            message = raw or e.reason
            try:
                parsed = json.loads(raw) if raw else {}
                err = parsed.get("error") or parsed
                if isinstance(err, dict):
                    code = err.get("code")
                    message = err.get("message") or message
            except Exception:
                pass
            raise StemSplitError(
                f"StemSplit HTTP {e.code}: {message}",
                code=code,
                status=e.code,
            ) from e
        except urllib.error.URLError as e:
            raise StemSplitError(f"StemSplit network error: {e.reason}") from e

    def create_upload(self, filename: str) -> dict[str, Any]:
        url = f"{self.base_url}/api/v1/upload"
        payload = json.dumps({"filename": filename}).encode("utf-8")
        return self._request(
            "POST", url, headers=self._headers(json_body=True), data=payload
        )

    def put_file(self, upload_url: str, path: Path, *, content_type: str | None = None) -> None:
        data = path.read_bytes()
        ctype = content_type or _guess_content_type(path.name)
        # Presigned PUT typically does not need Bearer; send Content-Type only.
        self._request(
            "PUT",
            upload_url,
            headers={"Content-Type": ctype},
            data=data,
            expect_json=False,
        )

    def create_job(
        self,
        *,
        upload_key: str | None = None,
        source_url: str | None = None,
        output_type: str = "BOTH",
        quality: str = "BALANCED",
        output_format: str = "WAV",
    ) -> dict[str, Any]:
        if not upload_key and not source_url:
            raise StemSplitError("uploadKey or sourceUrl required")
        body: dict[str, Any] = {
            "outputType": output_type,
            "quality": quality,
            "outputFormat": output_format,
        }
        if upload_key:
            body["uploadKey"] = upload_key
        if source_url:
            body["sourceUrl"] = source_url
        url = f"{self.base_url}/api/v1/jobs"
        return self._request(
            "POST",
            url,
            headers=self._headers(json_body=True),
            data=json.dumps(body).encode("utf-8"),
        )

    def get_job(self, job_id: str) -> dict[str, Any]:
        url = f"{self.base_url}/api/v1/jobs/{job_id}"
        return self._request("GET", url, headers=self._headers())

    def download_url(self, url: str, dest: Path) -> None:
        body = self._request("GET", url, headers={}, expect_json=False)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)

    def separate_file(
        self,
        input_path: Path,
        *,
        filename: str | None = None,
        out_vocals: Path | None = None,
        out_instrumental: Path | None = None,
        quality: str = "BALANCED",
        output_format: str = "WAV",
        output_type: str = "BOTH",
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        poll_timeout: float = DEFAULT_POLL_TIMEOUT,
        on_progress: Callable[[int, str], None] | None = None,
    ) -> dict[str, Any]:
        """Full flow: presign → PUT → create job → poll → download stems.

        output_type: BOTH | VOCALS | INSTRUMENTAL (StemSplit API).
        """
        name = filename or input_path.name
        ot = (output_type or "BOTH").upper()
        if ot not in ("BOTH", "VOCALS", "INSTRUMENTAL"):
            raise StemSplitError(f"invalid output_type: {output_type}")
        if ot in ("BOTH", "VOCALS") and out_vocals is None:
            raise StemSplitError("out_vocals required for this output_type")
        if ot in ("BOTH", "INSTRUMENTAL") and out_instrumental is None:
            raise StemSplitError("out_instrumental required for this output_type")

        def progress(pct: int, msg: str) -> None:
            if on_progress:
                on_progress(pct, msg)

        progress(5, "向 StemSplit 申請上傳網址…")
        upload = self.create_upload(name)
        upload_url = upload.get("uploadUrl")
        upload_key = upload.get("uploadKey")
        if not upload_url or not upload_key:
            raise StemSplitError(f"unexpected upload response: {upload}")

        progress(15, "上傳音訊至 StemSplit…")
        self.put_file(upload_url, input_path, content_type=_guess_content_type(name))

        progress(25, "建立 StemSplit 分離任務…")
        job = self.create_job(
            upload_key=upload_key,
            output_type=ot,
            quality=quality,
            output_format=output_format,
        )
        remote_id = job.get("id")
        if not remote_id:
            raise StemSplitError(f"unexpected job response: {job}")

        progress(30, f"StemSplit 處理中（任務 {remote_id}）…")
        deadline = time.monotonic() + poll_timeout
        last: dict[str, Any] = job
        while time.monotonic() < deadline:
            last = self.get_job(remote_id)
            status = str(last.get("status") or "").upper()
            remote_pct = last.get("progress")
            try:
                pct = int(remote_pct) if remote_pct is not None else None
            except (TypeError, ValueError):
                pct = None
            if pct is None:
                if status in ("PENDING", "QUEUED"):
                    pct = 35
                elif status in ("PROCESSING", "RUNNING"):
                    pct = 55
                else:
                    pct = 50
            # Map remote 0–100 into our mid-band until complete
            mapped = 30 + int(max(0, min(100, pct)) * 0.6)
            progress(mapped, f"StemSplit：{status or '處理中'}（{pct}%）")

            if status == "COMPLETED":
                break
            if status in ("FAILED", "ERROR", "CANCELLED"):
                err = last.get("errorMessage") or last.get("error") or status
                raise StemSplitError(f"StemSplit job failed: {err}", code=status)
            time.sleep(poll_interval)
        else:
            raise StemSplitError(
                f"StemSplit job timed out after {poll_timeout:.0f}s",
                code="TIMEOUT",
            )

        outputs = last.get("outputs") or {}
        vocals = outputs.get("vocals") or {}
        instrumental = outputs.get("instrumental") or {}
        v_url = vocals.get("url") if isinstance(vocals, dict) else None
        i_url = instrumental.get("url") if isinstance(instrumental, dict) else None

        need_v = ot in ("BOTH", "VOCALS")
        need_i = ot in ("BOTH", "INSTRUMENTAL")
        if need_v and not v_url:
            raise StemSplitError(f"StemSplit completed without vocals URL: {outputs}")
        if need_i and not i_url:
            raise StemSplitError(
                f"StemSplit completed without instrumental URL: {outputs}"
            )

        step = 92
        if v_url and out_vocals is not None:
            progress(step, "下載人聲…")
            self.download_url(v_url, out_vocals)
            step = 96
        if i_url and out_instrumental is not None:
            progress(step, "下載伴奏…")
            self.download_url(i_url, out_instrumental)
        progress(100, "完成")
        return last
